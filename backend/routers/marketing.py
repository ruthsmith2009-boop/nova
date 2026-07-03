from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from database import get_db, Lead, EmailLog
from agents.marketing import write_weekly_newsletter, write_email_sequence
from agents.email_agent import queue_email_for_approval, approve_and_send_email, send_email
from agents.research import get_market_snapshot

router = APIRouter(prefix="/marketing", tags=["marketing"])


class EmailRequest(BaseModel):
    lead_id: Optional[int] = None
    to_email: str
    subject: str
    body: str
    auto_send: bool = False


class SequenceRequest(BaseModel):
    lead_id: int
    sequence_type: str = "new_lead"


@router.post("/email")
def send_or_queue_email(req: EmailRequest, db: Session = Depends(get_db)):
    if req.auto_send:
        result = send_email(req.to_email, req.subject, req.body, req.lead_id)
        return result
    else:
        email_id = queue_email_for_approval(req.to_email, req.subject, req.body, req.lead_id)
        return {"status": "queued_for_approval", "email_id": email_id}


@router.post("/email/{email_id}/approve")
def approve_email(email_id: int):
    return approve_and_send_email(email_id)


@router.get("/email/pending")
def get_pending_emails(db: Session = Depends(get_db)):
    emails = db.query(EmailLog).filter(EmailLog.status == "pending_approval").all()
    return [{"id": e.id, "to": e.to_email, "subject": e.subject,
             "body_preview": e.body_preview, "created_at": e.created_at.isoformat()} for e in emails]


@router.post("/sequence")
async def generate_sequence(req: SequenceRequest, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == req.lead_id).first()
    if not lead:
        return {"error": "Lead not found"}
    lead_dict = {
        "first_name": lead.first_name, "last_name": lead.last_name,
        "address": lead.address, "city": lead.city,
        "life_event": lead.life_event, "score": lead.score
    }
    sequence = await write_email_sequence(lead_dict, req.sequence_type)
    return {"lead_id": req.lead_id, "sequence_type": req.sequence_type, "emails": sequence}


@router.get("/newsletter/{area}")
async def generate_newsletter(area: str):
    market_data = await get_market_snapshot(area)
    newsletter = await write_weekly_newsletter(area, market_data)
    return {"area": area, "newsletter": newsletter, "market_data": market_data}
