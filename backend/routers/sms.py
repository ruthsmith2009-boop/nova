"""
SMS router — Twilio inbound-SMS webhook (replies to the missed-call text-back).

POST /sms/incoming receives Twilio's form-encoded message webhook (From/Body)
and answers with TwiML. Point the Twilio number's Messaging webhook here once
the A2P 10DLC campaign is approved — activation steps in docs/CLONE_CHECKLIST.md.

Secured (optionally) by SMS_WEBHOOK_TOKEN: if set, Twilio must call
/sms/incoming?token=<value> or the webhook returns 401 — same pattern as
/calling/webhook and /leadgen/inbound.
"""
import secrets
from datetime import datetime
from html import escape

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db, SmsLog, Touchpoint
from agents.calling import normalize_phone
from agents.sms import (
    clear_opt_out, find_or_create_lead_by_phone, mark_opted_out,
)
from config import settings

router = APIRouter(prefix="/sms", tags=["sms"])

# Standard carrier keywords (Twilio also enforces these at the carrier level).
STOP_WORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
START_WORDS = {"START", "UNSTOP", "SUBSCRIBE"}
HELP_WORDS = {"HELP", "INFO"}
BOOK_WORDS = {"BOOK", "CALL"}


def _twiml(message: str = "") -> Response:
    """A valid TwiML response — empty <Response/> or a single <Message> reply."""
    if message:
        xml = ('<?xml version="1.0" encoding="UTF-8"?>'
               f"<Response><Message>{escape(message)}</Message></Response>")
    else:
        xml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return Response(content=xml, media_type="application/xml")


def _contact_line() -> str:
    phone = settings.business_phone_number or settings.agent_phone
    return (f"{settings.business_name}: reply with what you need, call us at "
            f"{phone}, or email {settings.agent_email}. Reply STOP to opt out.")


@router.post("/incoming")
async def incoming_sms(request: Request,
                       From: str = Form(""),
                       Body: str = Form(""),
                       db: Session = Depends(get_db)):
    """Handle a text sent to the business number (STOP / HELP / BOOK / anything)."""
    expected = settings.sms_webhook_token
    if expected:
        given = request.query_params.get("token") or ""
        if not secrets.compare_digest(given, expected):
            raise HTTPException(401, "Invalid webhook token")
    else:
        print("⚠️  /sms/incoming is unauthenticated — set SMS_WEBHOOK_TOKEN "
              "(and add ?token=... to the Twilio webhook URL) to secure it.")

    phone = normalize_phone(From)
    if not phone:
        return _twiml()
    body = (Body or "").strip()
    keyword = body.upper()

    # STOP → opt out, no reply (Twilio sends the carrier-mandated confirmation).
    if keyword in STOP_WORDS:
        mark_opted_out(db, phone)
        db.add(SmsLog(phone=phone, direction="inbound", kind="opt_out",
                      body=body, status="received"))
        db.commit()
        return _twiml()

    # START → allow texting again.
    if keyword in START_WORDS:
        clear_opt_out(db, phone)
        db.add(SmsLog(phone=phone, direction="inbound", kind="opt_in",
                      body=body, status="received"))
        db.commit()
        return _twiml()

    # HELP → business contact line.
    if keyword in HELP_WORDS:
        db.add(SmsLog(phone=phone, direction="inbound", kind="help",
                      body=body, status="received"))
        db.commit()
        return _twiml(_contact_line())

    # Everything below touches the CRM — find (or create) the lead by phone.
    lead = find_or_create_lead_by_phone(db, phone, source="missed-call")

    # BOOK / CALL → hot lead + follow-up due now, so it lands on today's dashboard.
    if keyword in BOOK_WORDS:
        db.add(SmsLog(lead_id=lead.id, phone=phone, direction="inbound",
                      kind="book", body=body, status="received"))
        db.add(Touchpoint(lead_id=lead.id, type="text", direction="inbound",
                          summary=f'Texted "{body}" — wants to book a consultation.',
                          outcome="appointment_requested"))
        lead.temperature = "hot"
        lead.next_follow_up = datetime.utcnow()   # shows in "follow-ups due" today
        lead.last_contact = datetime.utcnow()
        db.commit()
        phone_line = settings.business_phone_number or settings.agent_phone
        return _twiml(f"Great — someone from {settings.business_name} will reach "
                      f"out shortly to get you scheduled. If it's urgent, call us "
                      f"at {phone_line}.")

    # Anything else → log it on the lead as an inbound note.
    db.add(SmsLog(lead_id=lead.id, phone=phone, direction="inbound",
                  kind="inbound", body=body, status="received"))
    db.add(Touchpoint(lead_id=lead.id, type="text", direction="inbound",
                      summary=body or "(empty text)", outcome="received"))
    lead.last_contact = datetime.utcnow()
    if not lead.next_follow_up or lead.next_follow_up > datetime.utcnow():
        lead.next_follow_up = datetime.utcnow()   # surface the reply for action
    db.commit()
    return _twiml()
