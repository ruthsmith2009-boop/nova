"""
AI Calling router — campaign control, single calls, and the Vapi webhook.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database import get_db, Campaign, CallRecord, Lead
from agents.calling import (
    build_assistant_script, place_call, process_call_result,
    is_duplicate_number, normalize_phone, DISPOSITIONS,
)
from config import settings

router = APIRouter(prefix="/calling", tags=["calling"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class CampaignCreate(BaseModel):
    name: str
    goal: str
    offer: str
    qualifying_questions: list[str] = []
    lead_ids: list[int] = []
    industry: str = "small business"
    call_window_start: str = "09:00"
    call_window_end: str = "18:00"
    max_attempts: int = 3
    notify_email: Optional[str] = None


class SingleCallRequest(BaseModel):
    lead_id: Optional[int] = None
    phone: Optional[str] = None
    goal: str = "Qualify the prospect and book a quick intro call"
    offer: str = "A free, no-pressure consultation"


# ── Campaign CRUD + control ───────────────────────────────────────────────────
@router.post("/campaigns")
async def create_campaign(req: CampaignCreate, db: Session = Depends(get_db)):
    script = await build_assistant_script(req.goal, req.offer,
                                          req.qualifying_questions, req.industry)
    camp = Campaign(
        name=req.name, goal=req.goal, script=str(script),
        status="draft", lead_ids=req.lead_ids,
        call_window_start=req.call_window_start, call_window_end=req.call_window_end,
        max_attempts=req.max_attempts, notify_email=req.notify_email,
        total_leads=len(req.lead_ids),
    )
    db.add(camp)
    db.commit()
    db.refresh(camp)
    return {**_serialize_campaign(camp), "generated_script": script}


@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db)):
    return [_serialize_campaign(c) for c in
            db.query(Campaign).order_by(Campaign.created_at.desc()).all()]


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    camp = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not camp:
        raise HTTPException(404, "Campaign not found")
    records = db.query(CallRecord).filter(CallRecord.campaign_id == campaign_id).all()
    return {**_serialize_campaign(camp), "call_records": [_serialize_call(r) for r in records]}


@router.post("/campaigns/{campaign_id}/{action}")
async def control_campaign(campaign_id: int, action: str,
                           background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """action: start | pause | stop"""
    camp = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not camp:
        raise HTTPException(404, "Campaign not found")
    if action not in ("start", "pause", "stop"):
        raise HTTPException(400, "action must be start, pause, or stop")

    if action == "start":
        camp.status = "running"
        db.commit()
        background_tasks.add_task(run_campaign_batch, campaign_id)
        return {"status": "running", "message": "Campaign started — calls are being placed."}
    elif action == "pause":
        camp.status = "paused"
        db.commit()
        return {"status": "paused"}
    else:
        camp.status = "stopped"
        db.commit()
        return {"status": "stopped"}


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(campaign_id: int, db: Session = Depends(get_db)):
    """Permanently delete a campaign and its call records."""
    camp = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not camp:
        raise HTTPException(404, "Campaign not found")
    db.query(CallRecord).filter(CallRecord.campaign_id == campaign_id).delete()
    db.delete(camp)
    db.commit()
    return {"status": "deleted", "id": campaign_id}


# ── Campaign runner ───────────────────────────────────────────────────────────
def _within_window(start: str, end: str) -> bool:
    now = datetime.now().strftime("%H:%M")
    return start <= now <= end


async def run_campaign_batch(campaign_id: int):
    """Place calls for all enrolled leads, respecting duplicates, attempts, and window."""
    from database import SessionLocal
    import ast
    db = SessionLocal()
    try:
        camp = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not camp or camp.status != "running":
            return
        if not _within_window(camp.call_window_start, camp.call_window_end):
            return  # outside calling hours; a scheduler can retry later

        try:
            script = ast.literal_eval(camp.script) if camp.script else {}
        except Exception:
            script = {}

        for lead_id in (camp.lead_ids or []):
            db.refresh(camp)
            if camp.status != "running":
                break  # paused or stopped mid-batch

            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead or not lead.phone:
                continue

            # Duplicate check — skip if already called in this campaign
            if is_duplicate_number(db, lead.phone, campaign_id):
                continue

            normalized = normalize_phone(lead.phone)
            record = CallRecord(
                campaign_id=campaign_id, lead_id=lead_id,
                phone_number=normalized, provider="vapi",
                status="queued", attempt_number=1, started_at=datetime.utcnow(),
            )
            db.add(record)
            db.commit()
            db.refresh(record)

            result = await place_call(
                lead.phone, script,
                {"first_name": lead.first_name, "last_name": lead.last_name,
                 "address": lead.address, "city": lead.city},
            )
            record.provider_call_id = result.get("provider_call_id")
            record.status = "in_progress" if result.get("status") == "queued" else result.get("status", "failed")
            camp.calls_placed = (camp.calls_placed or 0) + 1
            db.commit()
    finally:
        db.close()


# ── Single call (manual click-to-call) ────────────────────────────────────────
@router.post("/call")
async def single_call(req: SingleCallRequest, db: Session = Depends(get_db)):
    phone = req.phone
    lead = None
    if req.lead_id:
        lead = db.query(Lead).filter(Lead.id == req.lead_id).first()
        if lead:
            phone = phone or lead.phone
    if not phone:
        raise HTTPException(400, "No phone number provided")

    script = await build_assistant_script(req.goal, req.offer, [], "small business")
    record = CallRecord(lead_id=req.lead_id, phone_number=normalize_phone(phone),
                        provider="vapi", status="queued", started_at=datetime.utcnow())
    db.add(record)
    db.commit()
    db.refresh(record)

    ctx = {"first_name": lead.first_name} if lead else {}
    result = await place_call(phone, script, ctx)
    record.provider_call_id = result.get("provider_call_id")
    record.status = "in_progress" if result.get("status") == "queued" else result.get("status", "failed")
    db.commit()
    return {"call_record_id": record.id, **result}


# ── Missed-call detection (for the SMS text-back) ─────────────────────────────
# Vapi end reasons that mean the caller never got a real conversation.
MISSED_END_REASONS = {
    "no-answer", "busy", "customer-busy", "customer-did-not-answer",
    "twilio-failed-to-connect-call", "silence-timed-out",
    "assistant-did-not-receive-customer-audio",
}
# A customer-ended-call under this many seconds = they hung up right away.
SHORT_CALL_SECONDS = 10


def _is_missed_inbound(msg: dict, call: dict, duration) -> bool:
    """True when an INBOUND call ended without a meaningful conversation —
    caller hung up immediately, line was busy, or the call never connected."""
    if "inbound" not in str(call.get("type") or "").lower():
        return False  # outbound campaign calls never get a text-back
    reason = str(msg.get("endedReason") or call.get("endedReason") or "").lower()
    if reason in MISSED_END_REASONS:
        return True
    try:
        seconds = float(duration or 0)
    except (TypeError, ValueError):
        seconds = 0.0
    return reason == "customer-ended-call" and seconds < SHORT_CALL_SECONDS


# ── Webhook (Vapi posts call events here) ──────────────────────────────────────
@router.post("/webhook")
async def vapi_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive end-of-call reports from Vapi and process them into the CRM.

    Secured by VAPI_WEBHOOK_SECRET when set: Vapi must send it in the
    x-vapi-secret header (Vapi's "Server URL Secret") or as ?token=.
    If the secret is unset the webhook stays open (backward compatible).
    """
    secret = settings.vapi_webhook_secret
    if secret:
        given = (request.headers.get("x-vapi-secret")
                 or request.query_params.get("token") or "")
        if not secrets.compare_digest(given, secret):
            raise HTTPException(401, "Invalid webhook secret")
    else:
        print("⚠️  /calling/webhook is unauthenticated — set VAPI_WEBHOOK_SECRET "
              "(and the matching Server URL Secret in Vapi) to secure it.")
    payload = await request.json()
    msg = payload.get("message", payload)
    event = msg.get("type", "")

    # Only finalize on the terminal event. Vapi also emits many interim
    # "status-update" events per call (ringing, in-progress, ended...); counting
    # each of those tallied one real call as several "connected". Finalize once.
    if event in ("end-of-call-report", "call.ended"):
        call = msg.get("call", {})
        provider_call_id = call.get("id") or msg.get("callId")
        duration = msg.get("durationSeconds") or call.get("duration")

        # Missed-call text-back: an inbound caller hung up / never connected.
        # handle_missed_call is a no-op unless SMS_TEXTBACK_ENABLED=true (the
        # feature stays off until the A2P 10DLC campaign is approved), and it
        # dedupes (1 text per number per 24h), respects STOP opt-outs, and logs
        # a touchpoint on the lead (creating one with source "missed-call").
        textback = None
        if settings.sms_textback_enabled and _is_missed_inbound(msg, call, duration):
            caller = ((call.get("customer") or {}).get("number")
                      or (msg.get("customer") or {}).get("number"))
            if caller:
                from agents.sms import handle_missed_call
                try:
                    textback = await handle_missed_call(db, caller)
                except Exception as e:
                    textback = {"status": "error", "error": str(e)}

        record = db.query(CallRecord).filter(
            CallRecord.provider_call_id == provider_call_id).first()
        if not record:
            # Normal for inbound calls Vapi answered directly (no outbound record).
            resp = {"status": "no_matching_record"}
            if textback:
                resp["textback"] = textback
            return resp
        # Idempotency: if this call was already finalized, don't count it twice.
        if record.status == "completed":
            return {"status": "already_processed"}

        transcript = msg.get("transcript", "") or msg.get("artifact", {}).get("transcript", "")
        summary = msg.get("summary", "") or msg.get("analysis", {}).get("summary", "")
        recording = msg.get("recordingUrl") or msg.get("artifact", {}).get("recordingUrl")

        result = await process_call_result(db, record.id, transcript, summary,
                                           duration, recording)
        if textback:
            result["textback"] = textback
        return {"status": "processed", **result}

    return {"status": "ignored", "event": event}


# ── Call records / inbox ──────────────────────────────────────────────────────
@router.get("/records")
def list_records(disposition: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(CallRecord).order_by(CallRecord.created_at.desc())
    if disposition:
        q = q.filter(CallRecord.disposition == disposition)
    return [_serialize_call(r) for r in q.limit(200).all()]


@router.get("/status")
def calling_status():
    return {
        "vapi_configured": bool(settings.vapi_api_key and settings.vapi_phone_number_id),
        "twilio_configured": bool(settings.twilio_account_sid and settings.twilio_phone_number),
        "webhook_url": f"{settings.public_base_url}/calling/webhook" if settings.public_base_url else None,
        "dispositions": DISPOSITIONS,
    }


# ── Serializers ───────────────────────────────────────────────────────────────
def _serialize_campaign(c: Campaign) -> dict:
    return {
        "id": c.id, "name": c.name, "goal": c.goal, "status": c.status,
        "total_leads": c.total_leads, "calls_placed": c.calls_placed,
        "calls_connected": c.calls_connected, "interested_count": c.interested_count,
        "appointments_set": c.appointments_set,
        "call_window_start": c.call_window_start, "call_window_end": c.call_window_end,
        "max_attempts": c.max_attempts, "notify_email": c.notify_email,
        "lead_ids": c.lead_ids, "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _serialize_call(r: CallRecord) -> dict:
    return {
        "id": r.id, "campaign_id": r.campaign_id, "lead_id": r.lead_id,
        "phone_number": r.phone_number, "status": r.status, "disposition": r.disposition,
        "duration_seconds": r.duration_seconds, "summary": r.summary,
        "decision_maker_name": r.decision_maker_name,
        "best_callback_time": r.best_callback_time, "captured_email": r.captured_email,
        "business_name": r.business_name, "recording_url": r.recording_url,
        "follow_up_at": r.follow_up_at.isoformat() if r.follow_up_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
