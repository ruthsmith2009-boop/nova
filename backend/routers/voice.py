"""
Voice tools — the endpoints Vapi calls WHILE a customer is on the phone.

This is the live path. Everything here runs with a caller waiting in silence, so
two rules override normal habits:

  SPEED. Budget is ~200ms, hard cap 800ms. Vapi already spends 200-400ms on the
  round trip before we run. Never call Google, Anthropic, or Twilio from these
  handlers — availability and booking read only local SQLite. Slow work happens
  after the response is sent.

  SAY LESS. Whatever comes back gets read out loud by the assistant and stored in
  Vapi's transcript. Return the one sentence the AI needs to say. Never return
  lead notes, email addresses, or another customer's name — a caller asking
  "who's your 2pm?" must not be able to get an answer.

SECURITY — DIFFERENT FROM /calling/webhook ON PURPOSE

/calling/webhook stays open when no secret is set, for backward compatibility.
These endpoints will not. They WRITE to the calendar, so with no secret
configured they refuse to run in production. An unsecured booking endpoint is a
stranger filling the business's calendar with fake appointments.

THE DEPLOY TRAP (read before renaming anything)

main.py's login wall matches PUBLIC_PATHS with startswith(). "/voice/" is listed
there. If these routes ever move off that prefix they will work perfectly on a
Mac — where no login is configured — and return 401 to Vapi in production, so
every call fails silently with the assistant going quiet mid-sentence. Test
against the deployed URL, not just localhost.
"""
import secrets as _secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Request, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from agents import booking as booking_agent
from agents.availability import (
    find_open_slots, find_next_open_slots, get_profile, get_timezone,
    utc_to_local, speak_time,
)

router = APIRouter(prefix="/voice", tags=["voice"])

# How many times to offer out loud. More than three and callers lose track.
MAX_SPOKEN_SLOTS = 3


# ── security ─────────────────────────────────────────────────────────────────

def _is_deployed() -> bool:
    """Are we on the public internet? Imported lazily — main.py imports this
    router, so importing main at module level would be a circular import."""
    import main
    return main.IS_DEPLOYED


def require_vapi_secret(request: Request) -> None:
    """Reject anything that isn't Vapi. Fails closed in production."""
    secret = settings.vapi_webhook_secret
    if not secret:
        if _is_deployed():
            # Deployed with no secret: refuse. These endpoints book real
            # appointments, so "open by default" is not an acceptable fallback.
            raise HTTPException(
                503,
                "Voice booking is disabled: VAPI_WEBHOOK_SECRET is not set. "
                "Set it in the hosting environment and in Vapi (Assistant → "
                "Server URL Secret), then redeploy.",
            )
        print("⚠️  /voice/* is unauthenticated (local only). Set VAPI_WEBHOOK_SECRET "
              "before deploying.")
        return

    given = (request.headers.get("x-vapi-secret")
             or request.query_params.get("token") or "")
    if not _secrets.compare_digest(given, secret):
        raise HTTPException(401, "Invalid webhook secret")


# ── turning results into something sayable ───────────────────────────────────

def _spoken_list(slots: list[dict]) -> str:
    """['9 AM','11 AM','1 PM'] -> '9 AM, 11 AM, or 1 PM'."""
    times = [s["spoken"].split(" at ")[-1] for s in slots]
    if not times:
        return ""
    if len(times) == 1:
        return times[0]
    return f"{', '.join(times[:-1])}, or {times[-1]}"


# ── the three tools ──────────────────────────────────────────────────────────

def _check_availability(db, args: dict) -> dict:
    """What's open. `date` is optional — without it, the soonest openings."""
    date = (args.get("date") or "").strip() or None
    service_id = args.get("service_id")
    limit = min(int(args.get("limit") or MAX_SPOKEN_SLOTS), MAX_SPOKEN_SLOTS)

    result = (find_open_slots(db, date, service_id=service_id, limit=limit)
              if date else
              find_next_open_slots(db, service_id=service_id, limit=limit))

    slots = result.get("slots", [])
    if result.get("degraded"):
        say = ("I can't get into the calendar this second. Let me take your number "
               "and someone will call you straight back to lock in a time.")
    elif not slots:
        say = (result.get("message") or "I don't have anything open then.") + \
              " Would another day work?"
    else:
        when = slots[0]["spoken"].split(" at ")[0]  # e.g. "Tuesday"
        say = f"{when} I have {_spoken_list(slots)}."

    return {
        "say": say,
        "degraded": bool(result.get("degraded")),
        "slots": [{"start_utc": s["start_utc"], "spoken": s["spoken"]} for s in slots],
    }


def _book_appointment(db, args: dict, background: BackgroundTasks) -> dict:
    """Hold and confirm in one call, because the caller is right there."""
    start_time = args.get("start_time") or args.get("start_utc")
    if not start_time:
        return {"say": "Which time would you like?", "booked": False}

    name = (args.get("customer_name") or args.get("name") or "").strip()
    phone = (args.get("customer_phone") or args.get("phone") or "").strip()
    email = (args.get("customer_email") or args.get("email") or "").strip()
    notes = (args.get("notes") or args.get("reason") or "").strip()

    result = booking_agent.book(
        db, start_time, customer_name=name, customer_phone=phone,
        customer_email=email, notes=notes, service_id=args.get("service_id"),
    )

    if result.get("ok"):
        background.add_task(booking_agent.push_to_google, result["appointment_id"])
        who = f", {name.split()[0]}" if name else ""
        return {
            "say": f"You're all set for {result['spoken']}{who}.",
            "booked": True,
            "appointment_id": result["appointment_id"],
        }

    # Couldn't book. Say why in a way that keeps the call moving.
    reason = result.get("reason")
    alternatives = result.get("alternatives", [])[:MAX_SPOKEN_SLOTS]
    profile = get_profile(db)

    if result.get("degraded"):
        say = ("I can't confirm that in the system right now. Let me take your "
               "number and we'll call you straight back.")
    elif reason == "just_taken":
        if alternatives and profile.double_booked_policy == "offer_next":
            say = (f"Someone just took that one, sorry. I do have "
                   f"{_spoken_list(alternatives)}.")
        else:
            say = ("Someone just took that one, sorry. Let me take your number and "
                   "we'll call you back with some options.")
    elif reason == "too_many_bookings":
        say = "It looks like that number already has appointments booked with us."
    elif alternatives:
        detail = result.get("message") or "That time won't work."
        say = f"{detail} I have {_spoken_list(alternatives)}."
    else:
        say = result.get("message") or "I couldn't book that time."

    return {
        "say": say, "booked": False, "reason": reason,
        "alternatives": [{"start_utc": s["start_utc"], "spoken": s["spoken"]}
                         for s in alternatives],
    }


def _lookup_caller(db, args: dict) -> dict:
    """Is this a returning customer, and do they have something booked?

    Returns a first name and their own upcoming appointment, nothing else. No
    email, no notes, no other customers — this text is read aloud and logged.
    """
    from agents.calling import normalize_phone
    from agents.sms import find_lead_by_phone
    from database import Appointment

    phone = normalize_phone(args.get("phone") or args.get("customer_phone") or "")
    if not phone:
        return {"say": "", "known": False}

    lead = find_lead_by_phone(db, phone)
    upcoming = (db.query(Appointment)
                .filter(Appointment.customer_phone == phone)
                .filter(Appointment.status == "booked")
                .filter(Appointment.start_time >= datetime.utcnow())
                .order_by(Appointment.start_time).first())

    if not lead and not upcoming:
        return {"say": "", "known": False}

    profile = get_profile(db)
    tz = get_timezone(profile)
    first_name = (lead.first_name or "").strip() if lead else ""

    if upcoming:
        when = speak_time(utc_to_local(upcoming.start_time, tz))
        return {
            "say": f"They already have an appointment {when}.",
            "known": True, "first_name": first_name,
            "has_appointment": True,
            "appointment_id": upcoming.id,
        }
    return {"say": "They're an existing customer.", "known": True,
            "first_name": first_name, "has_appointment": False}


TOOLS = {
    "check_availability": lambda db, args, bg: _check_availability(db, args),
    "book_appointment": lambda db, args, bg: _book_appointment(db, args, bg),
    "lookup_caller": lambda db, args, bg: _lookup_caller(db, args),
}


# ── Vapi's tool-call format ──────────────────────────────────────────────────

def _extract_tool_calls(payload: dict) -> list[dict]:
    """Pull out (id, name, arguments) from whatever shape Vapi sends.

    Vapi has shipped several shapes for this and older assistants still use the
    old ones, so accept them all rather than break on a platform change:
      message.toolCallList[]        {id, name, arguments}
      message.toolCalls[]           {id, function: {name, arguments}}
      message.functionCall          {name, parameters}   (legacy)
    """
    import json

    message = payload.get("message", payload) or {}
    found = []

    for entry in (message.get("toolCallList") or message.get("toolCalls") or []):
        function = entry.get("function") or {}
        name = entry.get("name") or function.get("name")
        raw_args = (entry.get("arguments") if entry.get("arguments") is not None
                    else function.get("arguments"))
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args or "{}")
            except Exception:
                raw_args = {}
        found.append({"id": entry.get("id") or entry.get("toolCallId") or "",
                      "name": name, "arguments": raw_args or {}})

    if not found and message.get("functionCall"):
        legacy = message["functionCall"]
        found.append({"id": message.get("id", ""), "name": legacy.get("name"),
                      "arguments": legacy.get("parameters") or {}})

    return [f for f in found if f.get("name")]


@router.post("/tools")
async def vapi_tools(request: Request, background: BackgroundTasks,
                     db: Session = Depends(get_db)):
    """The single URL Vapi hits mid-call for every tool.

    The reply shape matters. Vapi expects {"results": [{"toolCallId", "result"}]}.
    Anything else and the assistant gets nothing back, goes quiet, and waits until
    it times out — with the caller listening to silence.
    """
    require_vapi_secret(request)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Body must be JSON")

    calls = _extract_tool_calls(payload)
    if not calls:
        # Vapi also posts status updates here; acknowledge without pretending
        # to have run a tool.
        return {"results": []}

    results = []
    for call in calls:
        handler = TOOLS.get(call["name"])
        if not handler:
            results.append({"toolCallId": call["id"],
                            "result": "Sorry, I can't do that part."})
            continue
        try:
            outcome = handler(db, call["arguments"], background)
            results.append({"toolCallId": call["id"],
                            "result": outcome.get("say", "")})
        except Exception as e:
            # Never leak a stack trace into a phone call.
            print(f"⚠️  Voice tool '{call['name']}' failed: {e}")
            db.rollback()
            results.append({
                "toolCallId": call["id"],
                "result": ("Something went wrong on my end. Let me take your "
                           "number and have someone call you right back."),
            })

    return {"results": results}


# ── plain REST versions (easier to test with curl) ───────────────────────────

@router.post("/check-availability")
async def check_availability(request: Request, background: BackgroundTasks,
                             db: Session = Depends(get_db)):
    require_vapi_secret(request)
    try:
        args = await request.json()
    except Exception:
        args = {}
    return _check_availability(db, args or {})


@router.post("/book-appointment")
async def book_appointment(request: Request, background: BackgroundTasks,
                           db: Session = Depends(get_db)):
    require_vapi_secret(request)
    try:
        args = await request.json()
    except Exception:
        args = {}
    return _book_appointment(db, args or {}, background)


@router.post("/lookup-caller")
async def lookup_caller(request: Request, db: Session = Depends(get_db)):
    require_vapi_secret(request)
    try:
        args = await request.json()
    except Exception:
        args = {}
    return _lookup_caller(db, args or {})


@router.get("/status")
def voice_status(db: Session = Depends(get_db)):
    """Is the phone-booking path actually ready? Behind the login wall."""
    from agents.availability import cache_status
    profile = get_profile(db)
    deployed = _is_deployed()
    return {
        "secret_configured": bool(settings.vapi_webhook_secret),
        "deployed": deployed,
        "blocked_in_production": deployed and not settings.vapi_webhook_secret,
        "public_base_url": settings.public_base_url,
        "tools_url": f"{(settings.public_base_url or '').rstrip('/')}/voice/tools",
        "timezone": profile.timezone,
        "double_booked_policy": profile.double_booked_policy,
        "calendar": cache_status(db),
    }
