"""
AI Calling Engine — outbound voice calls via Vapi AI (voice brain) + Twilio (phone line).

Vapi handles the live AI conversation; Twilio provides the phone number. This module:
- Builds a calling assistant from a script
- Places outbound calls
- Checks for duplicate numbers before dialing
- Processes call results (webhooks) back into the CRM
- Maps call outcomes to pipeline stages and follow-up logic
- Fires email alerts when a lead is interested / needs the decision maker
"""
import re
import json
import httpx
from datetime import datetime, timedelta
from typing import Optional

from config import settings
from agents.brain import think_structured, SANTA_CLARA_KNOWLEDGE

VAPI_BASE = "https://api.vapi.ai"


# ── Pipeline disposition mapping (matches the campaign pipeline stages) ────────
DISPOSITIONS = [
    "new_lead", "called", "interested", "not_interested",
    "follow_up_required", "management_contact_required", "management_not_available",
    "custom_plan_requested", "appointment_callback_needed", "closed_completed",
    "no_answer", "voicemail", "wrong_number", "do_not_call",
]

# Which dispositions should trigger an immediate email alert to the agent
ALERT_DISPOSITIONS = {
    "interested", "custom_plan_requested", "management_contact_required",
    "appointment_callback_needed",
}

# Which dispositions auto-schedule a follow-up
FOLLOWUP_DISPOSITIONS = {
    "follow_up_required", "management_not_available", "no_answer",
    "voicemail", "appointment_callback_needed",
}


def normalize_phone(phone: str) -> str:
    """Normalize a phone number to E.164 (US default)."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d+]", "", str(phone))
    if digits.startswith("+"):
        return digits
    digits = re.sub(r"\D", "", digits)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}" if digits else ""


def is_duplicate_number(db, phone: str, campaign_id: int = None) -> bool:
    """Check whether this number has already been called (optionally within a campaign)."""
    from database import CallRecord
    normalized = normalize_phone(phone)
    if not normalized:
        return False
    q = db.query(CallRecord).filter(CallRecord.phone_number == normalized)
    if campaign_id is not None:
        q = q.filter(CallRecord.campaign_id == campaign_id)
    return db.query(q.exists()).scalar()


async def build_assistant_script(goal: str, offer: str, qualifying_questions: list[str],
                                 industry: str = "real estate") -> dict:
    """Use Claude to turn a plain-English goal into a structured AI calling assistant config."""
    result = await think_structured(
        f"""Design an AI outbound calling assistant for a {industry} business.

Goal of the calls: {goal}
Offer / service to introduce: {offer}
Qualifying questions to ask: {json.dumps(qualifying_questions)}

{SANTA_CLARA_KNOWLEDGE if industry == "real estate" else ""}

Return JSON for a natural, professional phone assistant:
{{
  "first_message": "The exact opening line the AI says when the call connects (warm, human, under 2 sentences)",
  "system_prompt": "Full instructions for the AI agent: persona, goal, how to introduce the offer, how to ask qualifying questions, how to identify interest, how to ask for the decision maker if the person isn't it, how to handle simple objections, when to offer a callback, how to end professionally. Write it as direct instructions to the voice agent.",
  "decision_maker_handling": "What to say when the person who answers is NOT the decision maker — ask who the right person is, if they're available, best callback time, name/number, and offer to send info by email.",
  "objection_responses": {{
    "not_interested": "response",
    "no_time": "response",
    "send_email_instead": "response",
    "already_have_someone": "response"
  }},
  "end_call_phrases": ["Thanks so much for your time", "Have a great day"],
  "voicemail_message": "Short voicemail to leave if no one answers"
}}""",
    )
    try:
        return json.loads(result)
    except Exception:
        return {
            "first_message": f"Hi, this is calling about {offer}. Do you have a quick minute?",
            "system_prompt": f"You are a friendly assistant calling about {offer}. Goal: {goal}.",
            "error": "AI script generation fell back to default",
        }


def _vapi_headers() -> dict:
    return {"Authorization": f"Bearer {settings.vapi_api_key}",
            "Content-Type": "application/json"}


async def place_call(phone: str, assistant_config: dict, lead_context: dict = None) -> dict:
    """Place a single outbound call via Vapi."""
    if not settings.vapi_api_key:
        return {"status": "not_configured",
                "message": "Vapi API key not set. Add VAPI_API_KEY to .env to enable live calling."}
    if not settings.vapi_phone_number_id:
        return {"status": "not_configured",
                "message": "Vapi phone number not set. Add VAPI_PHONE_NUMBER_ID to .env."}

    normalized = normalize_phone(phone)
    if not normalized:
        return {"status": "error", "error": f"Invalid phone number: {phone}"}

    # Personalize the first message with lead context
    first_message = assistant_config.get("first_message", "Hi, do you have a quick minute?")
    if lead_context and lead_context.get("first_name"):
        first_message = first_message.replace("[First Name]", lead_context["first_name"])

    payload = {
        "phoneNumberId": settings.vapi_phone_number_id,
        "customer": {"number": normalized},
        "assistant": {
            "firstMessage": first_message,
            "model": {
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "messages": [{"role": "system",
                              "content": assistant_config.get("system_prompt", "")}],
            },
            "voice": {"provider": "vapi",
                      "voiceId": assistant_config.get("voice_id", settings.vapi_default_voice)},
            "endCallPhrases": assistant_config.get("end_call_phrases", ["goodbye"]),
        },
    }
    if settings.public_base_url:
        payload["assistant"]["serverUrl"] = f"{settings.public_base_url}/calling/webhook"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{VAPI_BASE}/call", headers=_vapi_headers(), json=payload)
        data = resp.json()
        if resp.status_code in (200, 201) and data.get("id"):
            return {"status": "queued", "provider_call_id": data["id"],
                    "phone_number": normalized}
        return {"status": "error", "error": data.get("message", str(data))}


async def analyze_call_outcome(transcript: str, summary: str = "") -> dict:
    """Use Claude to extract structured outcome data from a completed call transcript."""
    result = await think_structured(
        f"""Analyze this outbound sales call transcript and extract the outcome.

Transcript:
{transcript[:4000]}

Provider summary: {summary[:500]}

Return JSON:
{{
  "disposition": "one of: interested, not_interested, follow_up_required, management_contact_required, management_not_available, custom_plan_requested, appointment_callback_needed, closed_completed, no_answer, voicemail, wrong_number, do_not_call",
  "interest_level": "hot/warm/cold/none",
  "decision_maker_name": "name if mentioned, else null",
  "decision_maker_available": true,
  "best_callback_time": "if mentioned, else null",
  "captured_email": "email if given, else null",
  "business_name": "if mentioned, else null",
  "custom_notes": "1-2 sentence summary of what the lead said and any commitments",
  "next_action": "what should happen next",
  "follow_up_in_days": 2
}}""",
        use_haiku=True,
    )
    try:
        return json.loads(result)
    except Exception:
        return {"disposition": "called", "interest_level": "none",
                "custom_notes": summary or "Call completed"}


def disposition_to_stage(disposition: str) -> Optional[str]:
    """Map a call disposition to a CRM lead stage."""
    mapping = {
        "interested": "contacted",
        "appointment_callback_needed": "appointment_set",
        "custom_plan_requested": "contacted",
        "management_contact_required": "contacted",
        "management_not_available": "contacted",
        "follow_up_required": "contacted",
        "not_interested": "dead",
        "do_not_call": "dead",
        "closed_completed": "closed",
    }
    return mapping.get(disposition)


async def process_call_result(db, call_record_id: int, transcript: str,
                              summary: str, duration: int = None,
                              recording_url: str = None) -> dict:
    """Process a completed call: analyze, update CRM, schedule follow-up, alert agent."""
    from database import CallRecord, Lead, Campaign
    from agents.email_agent import send_email

    record = db.query(CallRecord).filter(CallRecord.id == call_record_id).first()
    if not record:
        return {"error": "Call record not found"}

    outcome = await analyze_call_outcome(transcript, summary)
    disposition = outcome.get("disposition", "called")

    # Update call record
    record.status = "completed"
    record.disposition = disposition
    record.transcript = transcript
    record.summary = outcome.get("custom_notes", summary)
    record.duration_seconds = duration
    record.recording_url = recording_url
    record.decision_maker_name = outcome.get("decision_maker_name")
    record.decision_maker_available = outcome.get("decision_maker_available")
    record.best_callback_time = outcome.get("best_callback_time")
    record.captured_email = outcome.get("captured_email")
    record.business_name = outcome.get("business_name")
    record.custom_notes = outcome.get("custom_notes")
    record.ended_at = datetime.utcnow()

    # Follow-up scheduling
    if disposition in FOLLOWUP_DISPOSITIONS:
        days = outcome.get("follow_up_in_days", 2) or 2
        record.follow_up_at = datetime.utcnow() + timedelta(days=days)

    # Update the linked lead
    lead = None
    if record.lead_id:
        lead = db.query(Lead).filter(Lead.id == record.lead_id).first()
        if lead:
            lead.last_contact = datetime.utcnow()
            new_stage = disposition_to_stage(disposition)
            if new_stage:
                lead.stage = new_stage
            if record.follow_up_at:
                lead.next_follow_up = record.follow_up_at
            if outcome.get("captured_email") and not lead.email:
                lead.email = outcome["captured_email"]

    # Campaign stats
    if record.campaign_id:
        camp = db.query(Campaign).filter(Campaign.id == record.campaign_id).first()
        if camp:
            camp.calls_connected = (camp.calls_connected or 0) + 1
            if disposition == "interested":
                camp.interested_count = (camp.interested_count or 0) + 1
            if disposition == "appointment_callback_needed":
                camp.appointments_set = (camp.appointments_set or 0) + 1

    db.commit()

    # Email alert for hot dispositions
    alert_sent = False
    if disposition in ALERT_DISPOSITIONS:
        notify = None
        if record.campaign_id:
            camp = db.query(Campaign).filter(Campaign.id == record.campaign_id).first()
            notify = camp.notify_email if camp else None
        notify = notify or settings.agent_email
        if notify:
            _send_lead_alert(notify, lead, record, outcome)
            alert_sent = True

    return {"disposition": disposition, "alert_sent": alert_sent,
            "follow_up_at": record.follow_up_at.isoformat() if record.follow_up_at else None,
            "outcome": outcome}


def _send_lead_alert(to_email: str, lead, record, outcome: dict):
    """Send the formatted hot-lead email notification."""
    from agents.email_agent import send_email

    name = f"{lead.first_name} {lead.last_name}".strip() if lead else "Unknown"
    disp = (record.disposition or "").replace("_", " ").title()
    record_link = f"{settings.public_base_url or 'http://localhost:8000'}/#lead-{record.lead_id}"

    subject = f"🔥 New {disp} Lead — {name}"
    body = f"""<h2>New {disp} Lead from AI Call</h2>
<table style="font-family:sans-serif;font-size:14px;line-height:1.8">
<tr><td><b>Lead Name:</b></td><td>{name}</td></tr>
<tr><td><b>Phone Number:</b></td><td>{record.phone_number}</td></tr>
<tr><td><b>Business Name:</b></td><td>{record.business_name or '—'}</td></tr>
<tr><td><b>Email Address:</b></td><td>{record.captured_email or (lead.email if lead else '—')}</td></tr>
<tr><td><b>Call Status:</b></td><td>{disp}</td></tr>
<tr><td><b>Interest Level:</b></td><td>{outcome.get('interest_level','—')}</td></tr>
<tr><td><b>Decision Maker:</b></td><td>{record.decision_maker_name or '—'}</td></tr>
<tr><td><b>Best Follow-up Time:</b></td><td>{record.best_callback_time or '—'}</td></tr>
<tr><td><b>Next Action:</b></td><td>{outcome.get('next_action','—')}</td></tr>
</table>
<p><b>Call Summary:</b><br>{record.custom_notes or '—'}</p>
<p><a href="{record_link}">→ Open Lead Record in ARIA</a></p>
<hr><p style="color:#888;font-size:12px">Sent automatically by ARIA AI Calling</p>"""

    try:
        send_email(to_email, subject, body, record.lead_id)
    except Exception:
        pass
