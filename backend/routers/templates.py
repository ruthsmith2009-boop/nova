"""
Message Templates — reusable email/text outreach with merge fields.

Built-in starter templates (read-only) + the user's own (editable/deletable). `/templates/render`
fills the merge fields ({first_name}, {company}, {your_name}, ...) from a lead + business settings,
so she can paste a personalized message in seconds. NOVA does not send — it prepares the text.
"""
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from database import get_db, MessageTemplate, Lead
from config import settings

router = APIRouter(prefix="/templates", tags=["templates"])

BUILTIN_TEMPLATES = [
    {"key": "intro_email", "name": "New Lead Intro", "channel": "email",
     "subject": "Quick hello from {company_name}",
     "body": "Hi {first_name},\n\nThis is {your_name} with {company_name}. I work with businesses "
             "and people in {city} and wanted to introduce myself. If it's ever helpful, I'd be glad "
             "to put together a no-pressure look at how I could help — no obligation at all.\n\n"
             "Best,\n{your_name}\n{your_phone}"},
    {"key": "follow_up_text", "name": "Follow-up Text", "channel": "text",
     "body": "Hi {first_name}, it's {your_name}. Just checking in — still happy to answer any "
             "questions whenever you're ready. No rush at all. {your_phone}"},
    {"key": "quick_win_text", "name": "Quick Win Text", "channel": "text",
     "body": "Hi {first_name}! I had an idea that could save you some time. Want me to send a few "
             "details before we hop on a quick call? — {your_name}"},
    {"key": "value_offer_email", "name": "No-Pressure Offer", "channel": "email",
     "subject": "A quick idea for {company}",
     "body": "Hi {first_name},\n\nI put together a couple of ideas that might help {company}. "
             "If you'd like a current, no-obligation walkthrough, just reply and I'll send it over.\n\n"
             "{your_name}\n{your_phone}"},
]

MERGE_HELP = ["{first_name}", "{last_name}", "{full_name}", "{company}", "{city}", "{state}",
              "{zip}", "{email}", "{phone}", "{your_name}", "{your_phone}", "{your_email}",
              "{company_name}"]


class TemplateCreate(BaseModel):
    name: str
    channel: Optional[str] = "email"
    subject: Optional[str] = ""
    body: str


class RenderRequest(BaseModel):
    subject: Optional[str] = ""
    body: str
    lead_id: int


def _serialize(t: MessageTemplate) -> dict:
    return {"id": t.id, "name": t.name, "channel": t.channel, "subject": t.subject,
            "body": t.body, "deletable": True,
            "created_at": t.created_at.isoformat() if t.created_at else None}


def _merge_map(lead: Lead) -> dict:
    g = lambda a: getattr(lead, a, "") or ""
    # A lead's company/org lives in different places depending on the source — do a best-effort pull.
    lead_company = g("company") or g("address") or ""
    return {
        "first_name": g("first_name"), "last_name": g("last_name"),
        "full_name": f"{g('first_name')} {g('last_name')}".strip(),
        "company": lead_company, "address": g("address"),
        "city": g("city"), "state": g("state") or "CA",
        "zip": g("zip_code"), "email": g("email"), "phone": g("phone"),
        # The user's own business identity (kept backward-compatible with old {agent_*}/{broker} fields):
        "your_name": settings.agent_name, "your_phone": settings.agent_phone,
        "your_email": settings.agent_email, "company_name": settings.broker_name,
        "agent_name": settings.agent_name, "agent_phone": settings.agent_phone,
        "agent_email": settings.agent_email, "broker": settings.broker_name,
    }


def _fill(text: str, m: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda mt: str(m.get(mt.group(1), mt.group(0))), text or "")


@router.get("/")
def list_templates(db: Session = Depends(get_db)):
    builtin = [{**t, "id": f"builtin:{t['key']}", "deletable": False} for t in BUILTIN_TEMPLATES]
    custom = [_serialize(t) for t in
              db.query(MessageTemplate).order_by(MessageTemplate.created_at.desc()).all()]
    return {"builtin": builtin, "custom": custom, "merge_fields": MERGE_HELP}


@router.post("/")
def create_template(req: TemplateCreate, db: Session = Depends(get_db)):
    if not req.name.strip() or not req.body.strip():
        raise HTTPException(400, "Name and body are required")
    t = MessageTemplate(name=req.name.strip(), channel=(req.channel or "email"),
                        subject=(req.subject or "").strip(), body=req.body)
    db.add(t)
    db.commit()
    db.refresh(t)
    return _serialize(t)


@router.delete("/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    t = db.query(MessageTemplate).filter(MessageTemplate.id == template_id).first()
    if not t:
        raise HTTPException(404, "Template not found (built-ins can't be deleted)")
    db.delete(t)
    db.commit()
    return {"id": template_id, "status": "deleted"}


@router.post("/render")
def render_template(req: RenderRequest, db: Session = Depends(get_db)):
    """Fill a template's merge fields from a lead. Returns ready-to-send subject + body."""
    lead = db.query(Lead).filter(Lead.id == req.lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    m = _merge_map(lead)
    return {"subject": _fill(req.subject, m), "body": _fill(req.body, m)}
