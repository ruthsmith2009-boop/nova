from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database import get_db, Lead, CalendarEvent
from agents.calendar_agent import schedule_listing_appointment, schedule_follow_up, get_upcoming_events

router = APIRouter(prefix="/calendar", tags=["calendar"])


class AppointmentRequest(BaseModel):
    lead_id: int
    datetime_iso: str  # e.g. "2025-06-10T15:00:00"


class FollowUpRequest(BaseModel):
    lead_id: int
    datetime_iso: str
    note: Optional[str] = ""


@router.post("/listing-appointment")
async def book_listing_appointment(req: AppointmentRequest, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == req.lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")

    dt = datetime.fromisoformat(req.datetime_iso)
    lead_dict = {
        "first_name": lead.first_name, "last_name": lead.last_name,
        "address": lead.address, "city": lead.city,
        "phone": lead.phone, "email": lead.email,
        "life_event": lead.life_event, "score": lead.score
    }
    result = schedule_listing_appointment(lead_dict, dt)

    # Save to DB
    event = CalendarEvent(
        lead_id=req.lead_id,
        google_event_id=result.get("event_id"),
        title=f"Listing Appointment — {lead.first_name} {lead.last_name}",
        event_type="listing_appointment",
        start_time=dt,
        end_time=datetime.fromisoformat(req.datetime_iso.replace("T", " ").split(" ")[0] + "T" +
                  f"{dt.hour+1:02d}:{dt.minute:02d}:00"),
        location=lead.address or ""
    )
    db.add(event)
    lead.next_follow_up = dt
    db.commit()
    return result


@router.post("/follow-up")
async def book_follow_up(req: FollowUpRequest, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == req.lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    dt = datetime.fromisoformat(req.datetime_iso)
    lead_dict = {"first_name": lead.first_name, "last_name": lead.last_name,
                 "address": lead.address}
    result = schedule_follow_up(lead_dict, dt, req.note)
    lead.next_follow_up = dt
    db.commit()
    return result


@router.get("/upcoming")
def upcoming_events():
    events = get_upcoming_events(days=14)
    return {"events": events}
