"""
SMS Engine — missed-call text-back + inbound SMS helpers (Twilio REST API).

The `twilio` SDK isn't in requirements, so this posts straight to the Twilio
REST API with httpx basic auth — same pattern agents/calling.py uses for Vapi.

IMPORTANT: the text-back feature ships DISABLED (SMS_TEXTBACK_ENABLED=false)
until the A2P 10DLC campaign clears carrier vetting. Sending before approval
gets messages filtered by carriers and can hurt the number's reputation.
Every send path here also respects the STOP opt-out list.
"""
import httpx
from datetime import datetime, timedelta
from typing import Optional

from config import settings
from agents.calling import normalize_phone

TWILIO_API = "https://api.twilio.com/2010-04-01"

# One text-back per number per this many hours (dedupe window).
TEXTBACK_DEDUPE_HOURS = 24


# ── Message body ──────────────────────────────────────────────────────────────
def default_textback_message() -> str:
    return (f"Hi, this is the AI assistant for {settings.business_name} — sorry we "
            "missed your call! How can we help? Reply with what you need, or reply "
            "BOOK to schedule a consultation. Reply STOP to opt out.")


def textback_message() -> str:
    """The configured SMS_TEXTBACK_MESSAGE, or the default built from business_name."""
    return (settings.sms_textback_message or "").strip() or default_textback_message()


# ── Opt-out list (belt-and-suspenders on top of Twilio's carrier-level STOP) ──
def is_opted_out(db, phone: str) -> bool:
    from database import SmsOptOut
    normalized = normalize_phone(phone)
    if not normalized:
        return False
    return db.query(db.query(SmsOptOut)
                    .filter(SmsOptOut.phone == normalized).exists()).scalar()


def mark_opted_out(db, phone: str) -> None:
    from database import SmsOptOut
    normalized = normalize_phone(phone)
    if normalized and not is_opted_out(db, normalized):
        db.add(SmsOptOut(phone=normalized))
        db.commit()


def clear_opt_out(db, phone: str) -> None:
    """Caller texted START/UNSTOP — allow texting again."""
    from database import SmsOptOut
    normalized = normalize_phone(phone)
    if normalized:
        db.query(SmsOptOut).filter(SmsOptOut.phone == normalized).delete()
        db.commit()


# ── Sending ───────────────────────────────────────────────────────────────────
async def send_sms(db, to: str, body: str, lead_id: Optional[int] = None,
                   kind: str = "reply") -> dict:
    """Send one SMS via the Twilio REST API. Respects the opt-out list and logs
    every attempt to sms_logs."""
    from database import SmsLog

    if not (settings.twilio_account_sid and settings.twilio_auth_token
            and settings.twilio_phone_number):
        return {"status": "not_configured",
                "message": "Twilio credentials not set. Add TWILIO_ACCOUNT_SID, "
                           "TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER to .env."}

    normalized = normalize_phone(to)
    if not normalized:
        return {"status": "error", "error": f"Invalid phone number: {to}"}
    if is_opted_out(db, normalized):
        return {"status": "skipped", "reason": "opted_out"}

    async with httpx.AsyncClient(
        timeout=30,
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
    ) as client:
        resp = await client.post(
            f"{TWILIO_API}/Accounts/{settings.twilio_account_sid}/Messages.json",
            data={"From": settings.twilio_phone_number,
                  "To": normalized, "Body": body},
        )

    ok = resp.status_code in (200, 201)
    db.add(SmsLog(lead_id=lead_id, phone=normalized, direction="outbound",
                  kind=kind, body=body, status="sent" if ok else "failed"))
    db.commit()

    if ok:
        try:
            sid = resp.json().get("sid")
        except Exception:
            sid = None
        return {"status": "sent", "sid": sid, "to": normalized}
    try:
        err = resp.json().get("message", f"HTTP {resp.status_code}")
    except Exception:
        err = f"HTTP {resp.status_code}"
    return {"status": "failed", "error": err}


# ── Missed-call text-back ─────────────────────────────────────────────────────
def was_texted_back_recently(db, phone: str,
                             hours: int = TEXTBACK_DEDUPE_HOURS) -> bool:
    from database import SmsLog
    normalized = normalize_phone(phone)
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return db.query(
        db.query(SmsLog)
        .filter(SmsLog.phone == normalized,
                SmsLog.kind == "textback",
                SmsLog.status == "sent",
                SmsLog.created_at >= cutoff).exists()
    ).scalar()


def find_lead_by_phone(db, phone: str):
    """Match a lead by phone, tolerant of formatting ((408) 555-0133 vs +14085550133)."""
    from database import Lead
    normalized = normalize_phone(phone)
    if not normalized:
        return None
    lead = (db.query(Lead).filter(Lead.phone == normalized)
            .filter(Lead.is_deleted.isnot(True)).first())
    if lead:
        return lead
    for candidate in (db.query(Lead).filter(Lead.phone.isnot(None))
                      .filter(Lead.is_deleted.isnot(True)).all()):
        if normalize_phone(candidate.phone) == normalized:
            return candidate
    return None


def find_or_create_lead_by_phone(db, phone: str, source: str = "missed-call"):
    """Find the lead for this number, or create one (mirrors leadgen ingestion)."""
    from database import Lead
    lead = find_lead_by_phone(db, phone)
    if lead:
        return lead
    lead = Lead(
        first_name="", last_name="", phone=normalize_phone(phone),
        source=source, stage="new", temperature="warm",
        property_type="Business Prospect",
        notes=f"Called {settings.business_phone_number or 'the business line'} "
              "and hung up before the AI receptionist could help.",
        score_reasons=["Inbound caller — created automatically from a missed call"],
    )
    db.add(lead)
    db.flush()
    db.commit()
    return lead


async def handle_missed_call(db, caller_phone: str) -> dict:
    """Text back a caller who hung up before a real conversation.

    No-op unless SMS_TEXTBACK_ENABLED=true (gated on A2P 10DLC approval).
    Skips opted-out numbers and numbers already texted in the last 24 hours.
    Logs a Touchpoint on the matching lead (created with source 'missed-call'
    if none exists)."""
    from database import Touchpoint

    if not settings.sms_textback_enabled:
        return {"status": "disabled",
                "message": "SMS_TEXTBACK_ENABLED is false (waiting on A2P approval)."}

    normalized = normalize_phone(caller_phone)
    if not normalized:
        return {"status": "error", "error": f"Invalid caller number: {caller_phone}"}
    if is_opted_out(db, normalized):
        return {"status": "skipped", "reason": "opted_out"}
    if was_texted_back_recently(db, normalized):
        return {"status": "skipped", "reason": "already_texted_24h"}

    lead = find_or_create_lead_by_phone(db, normalized)
    result = await send_sms(db, normalized, textback_message(),
                            lead_id=lead.id, kind="textback")
    if result.get("status") == "sent":
        db.add(Touchpoint(lead_id=lead.id, type="text", direction="outbound",
                          summary="Missed call — automatic text-back sent.",
                          outcome="texted"))
        lead.last_contact = datetime.utcnow()
        db.commit()
    return {**result, "lead_id": lead.id}
