"""
Booking — actually reserves a time, and stops two callers taking the same one.

HOW THE RACE IS WON

Two people phone at the same second and both want Tuesday at 2. Checking
"is it free?" and then writing the booking is two steps, and the other caller
can slip in between them. No amount of checking first fixes that.

So the database decides, not the code. `appointments` carries a unique index on
(start_time, resource) limited to held and booked rows. Both inserts race; SQLite
lets exactly one through and raises IntegrityError on the other. We catch it and
turn it into "sorry, that just went — I have 3:30?". One winner, always, with no
locks and nothing to tune.

TWO STEPS, ON PURPOSE

  hold_slot()      reserves the time for a few minutes while the caller is still
                   talking ("perfect, let me just grab your name")
  confirm_booking() turns the hold into a real booking

A hold that is never confirmed expires by itself. A caller who hangs up halfway
through cannot block a time forever, and no cleanup job is required for that to
be true.

WHAT HAPPENS AFTER THE CALLER HEARS "YOU'RE BOOKED"

Nothing slow happens before that. Writing to Google Calendar and sending the
confirmation text both run in the background AFTER the response is sent, because
either one can take seconds and the caller is on the phone waiting. The booking
in NOVA is the real one; Google is a copy that catches up.
"""
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from config import settings
from database import (
    SessionLocal, Appointment, ServiceType, Touchpoint, Lead, BusinessProfile,
)
from agents.availability import (
    get_profile, get_timezone, slot_is_bookable, find_next_open_slots,
    utc_to_local, speak_time,
)
from agents.calling import normalize_phone

# A single caller cannot hold the whole day hostage. This is the cheap guard
# against someone (or a caller talking the AI into it) booking slot after slot.
MAX_ACTIVE_PER_PHONE = 3


def _utcnow() -> datetime:
    return datetime.utcnow()


def _release_expired_holds(db, start_time=None, resource: str = None) -> int:
    """Retire held rows whose timer ran out.

    This matters more than it looks. find_open_slots() already ignores expired
    holds, so the time is offered to the next caller — but the unique index only
    looks at status, so the dead row would still block the INSERT and the second
    caller would be wrongly told the slot was taken. Offered but unbookable is
    the worst of both worlds, so expired holds get moved out of the index.
    """
    query = (db.query(Appointment)
             .filter(Appointment.status == "held")
             .filter(Appointment.hold_expires_at.isnot(None))
             .filter(Appointment.hold_expires_at <= _utcnow()))
    if start_time is not None:
        query = query.filter(Appointment.start_time == start_time)
    if resource is not None:
        query = query.filter(Appointment.resource == resource)

    expired = query.all()
    for appointment in expired:
        appointment.status = "expired"
    if expired:
        db.commit()
    return len(expired)


def sweep_expired_holds() -> dict:
    """Housekeeping for the background loop — clears expired holds everywhere."""
    db = SessionLocal()
    try:
        return {"released": _release_expired_holds(db)}
    except Exception as e:
        db.rollback()
        print(f"⚠️  Hold sweep failed: {e}")
        return {"released": 0, "error": str(e)}
    finally:
        db.close()


def _resolve_service(db, service_id=None) -> ServiceType | None:
    if service_id:
        return db.query(ServiceType).filter(ServiceType.id == service_id).first()
    return (db.query(ServiceType)
            .filter(ServiceType.active.is_(True))
            .order_by(ServiceType.sort, ServiceType.id)
            .first())


def _parse_start(value) -> datetime | None:
    """Accept a datetime or an ISO string; always return naive UTC."""
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is not None:
        from datetime import timezone as _tz
        dt = dt.astimezone(_tz.utc).replace(tzinfo=None)
    return dt


def _alternatives(db, service_id, limit: int = 2) -> list[dict]:
    """Other times to offer when the requested one is gone."""
    try:
        return find_next_open_slots(db, service_id=service_id, limit=limit).get("slots", [])
    except Exception:
        return []


def hold_slot(db, start_time, service_id: int | None = None,
              resource: str = "default", customer_phone: str = "") -> dict:
    """Reserve a time for a few minutes. Returns the appointment id on success."""
    profile = get_profile(db)

    start_utc = _parse_start(start_time)
    if not start_utc:
        return {"ok": False, "reason": "bad_time",
                "message": "That time didn't make sense."}

    service = _resolve_service(db, service_id)
    if not service:
        return {"ok": False, "reason": "no_services",
                "message": "No services are set up yet."}

    # Expired holds on this exact slot would block the insert even though the
    # time is genuinely free. Clear them before checking anything else.
    _release_expired_holds(db, start_time=start_utc, resource=resource)

    check = slot_is_bookable(db, start_utc, service)
    if not check["ok"]:
        return {
            "ok": False, "reason": check["reason"], "message": check["message"],
            "degraded": check.get("degraded", False),
            "alternatives": [] if check.get("degraded") else _alternatives(db, service.id),
        }

    phone = normalize_phone(customer_phone) if customer_phone else ""
    if phone:
        active = (db.query(Appointment)
                  .filter(Appointment.customer_phone == phone)
                  .filter(Appointment.status.in_(["held", "booked"]))
                  .filter(Appointment.start_time >= _utcnow())
                  .count())
        if active >= MAX_ACTIVE_PER_PHONE:
            return {"ok": False, "reason": "too_many_bookings",
                    "message": "That number already has several appointments booked.",
                    "alternatives": []}

    appointment = Appointment(
        service_id=service.id,
        start_time=start_utc,
        end_time=start_utc + timedelta(minutes=service.duration_minutes or 60),
        resource=resource,
        status="held",
        hold_expires_at=_utcnow() + timedelta(minutes=profile.hold_minutes or 3),
        customer_phone=phone,
    )
    db.add(appointment)

    try:
        db.commit()
    except IntegrityError:
        # Someone else got this slot in the microseconds since the check above.
        # This is the race being won by the other caller — the expected path,
        # not an error worth alarming about.
        db.rollback()
        return {
            "ok": False, "reason": "just_taken",
            "message": "That time was just booked by someone else.",
            "alternatives": _alternatives(db, service.id),
        }

    db.refresh(appointment)
    tz = get_timezone(profile)
    return {
        "ok": True,
        "appointment_id": appointment.id,
        "start_utc": start_utc.isoformat(),
        "spoken": speak_time(utc_to_local(start_utc, tz)),
        "hold_expires_at": appointment.hold_expires_at.isoformat(),
        "service": {"id": service.id, "name": service.name,
                    "duration_minutes": service.duration_minutes},
    }


def confirm_booking(db, appointment_id: int, customer_name: str = "",
                    customer_phone: str = "", customer_email: str = "",
                    notes: str = "", call_record_id: int | None = None) -> dict:
    """Turn a hold into a real booking and attach it to a CRM lead.

    Returns fast on purpose. Google Calendar and the confirmation message are
    handled separately, after the caller has already been told they're booked.
    """
    appointment = (db.query(Appointment)
                   .filter(Appointment.id == appointment_id).first())
    if not appointment:
        return {"ok": False, "reason": "not_found",
                "message": "That booking doesn't exist."}

    if appointment.status == "booked":
        # Vapi retries tool calls. Confirming twice must not create a second
        # appointment or a second confirmation text.
        return {"ok": True, "already_confirmed": True,
                "appointment_id": appointment.id}

    if appointment.status != "held":
        return {"ok": False, "reason": f"status_{appointment.status}",
                "message": "That time is no longer being held."}

    if appointment.hold_expires_at and appointment.hold_expires_at <= _utcnow():
        appointment.status = "expired"
        db.commit()
        return {"ok": False, "reason": "hold_expired",
                "message": "That hold ran out.",
                "alternatives": _alternatives(db, appointment.service_id)}

    phone = normalize_phone(customer_phone) if customer_phone else (appointment.customer_phone or "")
    appointment.customer_name = (customer_name or "").strip()[:200]
    appointment.customer_phone = phone
    appointment.customer_email = (customer_email or "").strip()[:200]
    appointment.notes = (notes or "")[:2000]
    appointment.status = "booked"
    appointment.hold_expires_at = None
    if call_record_id:
        appointment.call_record_id = call_record_id

    lead = _link_lead(db, appointment)
    if lead:
        appointment.lead_id = lead.id

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"ok": False, "reason": "just_taken",
                "message": "That time was just booked by someone else.",
                "alternatives": _alternatives(db, appointment.service_id)}

    db.refresh(appointment)
    profile = get_profile(db)
    tz = get_timezone(profile)
    service = _resolve_service(db, appointment.service_id)

    return {
        "ok": True,
        "appointment_id": appointment.id,
        "lead_id": appointment.lead_id,
        "start_utc": appointment.start_time.isoformat(),
        "start_local": utc_to_local(appointment.start_time, tz).isoformat(),
        "spoken": speak_time(utc_to_local(appointment.start_time, tz)),
        "service": service.name if service else "Appointment",
        "customer_name": appointment.customer_name,
    }


def _link_lead(db, appointment: Appointment) -> Lead | None:
    """Attach the booking to a CRM lead, creating one for a new caller.

    Deliberately not reusing sms.find_or_create_lead_by_phone(): that one stamps
    every new lead with a missed-call note, which would be plainly wrong on the
    record of someone who just booked an appointment.
    """
    if not appointment.customer_phone:
        return None
    try:
        from agents.sms import find_lead_by_phone
        lead = find_lead_by_phone(db, appointment.customer_phone)

        if not lead:
            first, _, last = (appointment.customer_name or "").partition(" ")
            lead = Lead(
                first_name=first, last_name=last,
                phone=appointment.customer_phone,
                email=appointment.customer_email or "",
                source="phone-booking", stage="appointment_set",
                temperature="hot", property_type="Business Prospect",
                notes="Called the business line and booked an appointment.",
                score_reasons=["Inbound caller — booked an appointment by phone"],
            )
            db.add(lead)
            db.flush()
        else:
            lead.stage = "appointment_set"
            lead.temperature = "hot"
            if appointment.customer_email and not lead.email:
                lead.email = appointment.customer_email
            if appointment.customer_name and not (lead.first_name or lead.last_name):
                first, _, last = appointment.customer_name.partition(" ")
                lead.first_name, lead.last_name = first, last

        lead.last_contact = _utcnow()
        lead.next_follow_up = appointment.start_time

        db.add(Touchpoint(
            lead_id=lead.id, type="call", direction="inbound",
            summary=f"Booked an appointment for {appointment.start_time.isoformat()} UTC.",
            outcome="appointment_set",
        ))
        return lead
    except Exception as e:
        # A CRM hiccup must never lose a real appointment.
        print(f"⚠️  Could not link booking {appointment.id} to a lead: {e}")
        return None


def push_to_google(appointment_id: int) -> dict:
    """Copy a confirmed booking onto Google Calendar. Runs AFTER the response.

    Opens its own database session because it runs outside the request.
    """
    from agents.calendar_agent import create_event

    db = SessionLocal()
    try:
        appointment = (db.query(Appointment)
                       .filter(Appointment.id == appointment_id).first())
        if not appointment or appointment.status != "booked":
            return {"ok": False, "reason": "not_bookable"}
        if appointment.google_event_id:
            return {"ok": True, "reason": "already_synced"}

        profile = get_profile(db)
        tz = get_timezone(profile)
        service = _resolve_service(db, appointment.service_id)

        # create_event() stamps a hardcoded America/Los_Angeles timezone and
        # sends whatever datetime it is given. Our columns are naive UTC, so
        # handing them over directly would book every appointment 7-8 hours out.
        # Convert to the business's local time as an AWARE datetime: the offset
        # then rides along in the ISO string and Google honours that.
        local_start = utc_to_local(appointment.start_time, tz)
        local_end = utc_to_local(appointment.end_time, tz)

        who = appointment.customer_name or "Customer"
        title = f"{service.name if service else 'Appointment'} — {who}"
        description = (
            f"Booked by phone through {settings.business_name}.\n"
            f"Name: {who}\n"
            f"Phone: {appointment.customer_phone or 'not given'}\n"
            f"Email: {appointment.customer_email or 'not given'}\n"
            f"Notes: {appointment.notes or '—'}"
        )
        attendees = [appointment.customer_email] if appointment.customer_email else []

        result = create_event(title, local_start, local_end,
                              description=description, attendee_emails=attendees)

        if result.get("status") == "created":
            appointment.google_event_id = result.get("event_id")
            appointment.sync_status = "synced"
        else:
            appointment.sync_status = "failed"
            print(f"⚠️  Google sync failed for appointment {appointment_id}: "
                  f"{result.get('status')} {result.get('error', '')}")
        db.commit()
        return {"ok": appointment.sync_status == "synced",
                "sync_status": appointment.sync_status,
                "google_event_id": appointment.google_event_id}

    except Exception as e:
        db.rollback()
        try:
            appointment = (db.query(Appointment)
                           .filter(Appointment.id == appointment_id).first())
            if appointment:
                appointment.sync_status = "failed"
                db.commit()
        except Exception:
            pass
        print(f"⚠️  Google sync crashed for appointment {appointment_id}: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        db.close()


def retry_failed_google_syncs(limit: int = 20) -> dict:
    """Re-push bookings that never reached Google. Runs on the background loop,
    so a Google outage during a call heals itself instead of needing a human."""
    db = SessionLocal()
    try:
        pending = (db.query(Appointment)
                   .filter(Appointment.status == "booked")
                   .filter(Appointment.google_event_id.is_(None))
                   .filter(Appointment.sync_status.in_(["pending", "failed"]))
                   .filter(Appointment.start_time >= _utcnow())
                   .limit(limit).all())
        ids = [a.id for a in pending]
    except Exception as e:
        print(f"⚠️  Could not list failed syncs: {e}")
        ids = []
    finally:
        db.close()

    synced = sum(1 for appointment_id in ids if push_to_google(appointment_id).get("ok"))
    return {"attempted": len(ids), "synced": synced}


def book(db, start_time, customer_name: str = "", customer_phone: str = "",
         customer_email: str = "", notes: str = "", service_id: int | None = None,
         resource: str = "default", call_record_id: int | None = None) -> dict:
    """Hold and confirm in one go — for booking from the dashboard or a form,
    where there is no live conversation to hold a slot during."""
    held = hold_slot(db, start_time, service_id=service_id, resource=resource,
                     customer_phone=customer_phone)
    if not held["ok"]:
        return held
    return confirm_booking(db, held["appointment_id"],
                           customer_name=customer_name, customer_phone=customer_phone,
                           customer_email=customer_email, notes=notes,
                           call_record_id=call_record_id)


def cancel_appointment(db, appointment_id: int, reason: str = "") -> dict:
    """Cancel a booking and free the slot. Google cleanup is best-effort."""
    appointment = (db.query(Appointment)
                   .filter(Appointment.id == appointment_id).first())
    if not appointment:
        return {"ok": False, "reason": "not_found"}

    appointment.status = "cancelled"
    if reason:
        appointment.notes = f"{appointment.notes}\nCancelled: {reason}".strip()
    db.commit()

    if appointment.google_event_id:
        try:
            from agents.calendar_agent import get_calendar_service
            service = get_calendar_service()
            if service:
                service.events().delete(
                    calendarId=settings.google_calendar_id,
                    eventId=appointment.google_event_id,
                ).execute()
        except Exception as e:
            print(f"⚠️  Could not remove Google event for {appointment_id}: {e}")

    return {"ok": True, "appointment_id": appointment_id, "status": "cancelled"}
