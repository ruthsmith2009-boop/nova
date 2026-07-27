from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from database import (
    get_db, Lead, CalendarEvent, ServiceType, BusinessHours, Appointment,
)
from agents.calendar_agent import schedule_listing_appointment, schedule_follow_up, get_upcoming_events
from agents.availability import (
    find_open_slots, find_next_open_slots, refresh_busy_cache,
    cache_status, get_profile, get_timezone, utc_to_local,
)
from agents import booking as booking_agent

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
        title=f"Consultation — {lead.first_name} {lead.last_name}",
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


# ── Availability (what the AI receptionist will ask, mid-call) ────────────────
# These sit behind the normal login wall. The public, Vapi-facing versions come
# later in their own router with their own shared-secret check.

@router.get("/availability")
def availability(date: Optional[str] = None, service_id: Optional[int] = None,
                 limit: int = 3, db: Session = Depends(get_db)):
    """Open times. Pass ?date=2026-07-28 for one day, or leave it off for the
    soonest openings. `degraded: true` means the calendar could not be trusted
    and nothing should be booked."""
    if date:
        return find_open_slots(db, date, service_id=service_id, limit=limit)
    return find_next_open_slots(db, service_id=service_id, limit=limit)


@router.get("/services")
def list_services(db: Session = Depends(get_db)):
    """What a caller can book, and how long each takes."""
    services = (db.query(ServiceType)
                .order_by(ServiceType.sort, ServiceType.id).all())
    return {"services": [
        {"id": s.id, "name": s.name, "duration_minutes": s.duration_minutes,
         "spoken_description": s.spoken_description, "active": s.active}
        for s in services
    ]}


@router.get("/hours")
def list_hours(db: Session = Depends(get_db)):
    """Open hours, in the business's local time. 0 = Monday."""
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday"]
    hours = db.query(BusinessHours).order_by(BusinessHours.weekday).all()
    profile = get_profile(db)
    return {
        "timezone": profile.timezone,
        "hours": [
            {"weekday": h.weekday, "day": names[h.weekday],
             "open": h.open_time, "close": h.close_time, "closed": h.closed}
            for h in hours
        ],
    }


@router.get("/cache-status")
def calendar_cache_status(db: Session = Depends(get_db)):
    """Is the Google busy-time cache fresh enough to book against?"""
    return cache_status(db)


@router.post("/refresh-cache")
def refresh_cache(db: Session = Depends(get_db)):
    """Pull busy times from Google right now instead of waiting for the loop."""
    return refresh_busy_cache(db)


# ── Booking ──────────────────────────────────────────────────────────────────

class HoldRequest(BaseModel):
    start_time: str                    # ISO, e.g. "2026-07-28T14:00:00" (UTC)
    service_id: Optional[int] = None
    resource: str = "default"
    customer_phone: str = ""


class ConfirmRequest(BaseModel):
    appointment_id: int
    customer_name: str = ""
    customer_phone: str = ""
    customer_email: str = ""
    notes: str = ""
    call_record_id: Optional[int] = None


class BookRequest(BaseModel):
    start_time: str
    customer_name: str = ""
    customer_phone: str = ""
    customer_email: str = ""
    notes: str = ""
    service_id: Optional[int] = None
    resource: str = "default"


@router.post("/hold")
def hold(req: HoldRequest, db: Session = Depends(get_db)):
    """Reserve a time for a few minutes while a caller decides."""
    return booking_agent.hold_slot(
        db, req.start_time, service_id=req.service_id,
        resource=req.resource, customer_phone=req.customer_phone,
    )


@router.post("/confirm")
def confirm(req: ConfirmRequest, background: BackgroundTasks,
            db: Session = Depends(get_db)):
    """Turn a hold into a real booking. Google sync runs after this responds."""
    result = booking_agent.confirm_booking(
        db, req.appointment_id, customer_name=req.customer_name,
        customer_phone=req.customer_phone, customer_email=req.customer_email,
        notes=req.notes, call_record_id=req.call_record_id,
    )
    if result.get("ok") and not result.get("already_confirmed"):
        background.add_task(booking_agent.push_to_google, result["appointment_id"])
    return result


@router.post("/book")
def book(req: BookRequest, background: BackgroundTasks,
         db: Session = Depends(get_db)):
    """Hold and confirm in one step — for booking from the dashboard or a form."""
    result = booking_agent.book(
        db, req.start_time, customer_name=req.customer_name,
        customer_phone=req.customer_phone, customer_email=req.customer_email,
        notes=req.notes, service_id=req.service_id, resource=req.resource,
    )
    if result.get("ok") and not result.get("already_confirmed"):
        background.add_task(booking_agent.push_to_google, result["appointment_id"])
    return result


@router.post("/cancel/{appointment_id}")
def cancel(appointment_id: int, reason: str = "", db: Session = Depends(get_db)):
    """Cancel a booking and free the slot."""
    return booking_agent.cancel_appointment(db, appointment_id, reason=reason)


@router.get("/appointments")
def list_appointments(days: int = 14, status: Optional[str] = None,
                      db: Session = Depends(get_db)):
    """Booked appointments, soonest first — the 'what's on today' view."""
    profile = get_profile(db)
    tz = get_timezone(profile)
    now = datetime.utcnow()

    query = (db.query(Appointment)
             .filter(Appointment.start_time >= now)
             .filter(Appointment.start_time <= now + timedelta(days=days)))
    query = (query.filter(Appointment.status == status) if status
             else query.filter(Appointment.status.in_(["held", "booked"])))

    services = {s.id: s.name for s in db.query(ServiceType).all()}
    rows = query.order_by(Appointment.start_time).all()
    return {
        "timezone": profile.timezone,
        "appointments": [{
            "id": a.id,
            "service": services.get(a.service_id, "Appointment"),
            "when": utc_to_local(a.start_time, tz).strftime("%a %b %d, %-I:%M %p"),
            "start_utc": a.start_time.isoformat(),
            "status": a.status,
            "customer_name": a.customer_name,
            "customer_phone": a.customer_phone,
            "lead_id": a.lead_id,
            "on_google": bool(a.google_event_id),
            "sync_status": a.sync_status,
        } for a in rows],
    }
