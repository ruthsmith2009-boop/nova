"""
Availability — works out which appointment times are genuinely open.

WHY IT IS BUILT THIS WAY (read before changing it)

NOVA's own database is the system of record for bookings. Google Calendar is a
mirror that we read into a local cache every ~90 seconds. Two reasons:

  * Speed. During a live phone call the budget for answering "what's open Tuesday?"
    is about 200ms. A SQLite query is single-digit milliseconds. A Google API call
    is 300-800ms and occasionally 3+ seconds. That gap is dead air, and callers
    talk over it or hang up.

  * Safety. If Google is unreachable we must NOT conclude "the calendar is empty".
    The older get_upcoming_events() in calendar_agent.py swallows every error and
    returns [], which reads as a wide-open calendar — one outage would book three
    customers into the same slot. Here, a failed refresh leaves the previous cache
    untouched and records the error. If the cache goes stale we refuse to offer
    times at all (degraded=True) rather than guess. Fail closed, never double-book.

TIME HANDLING

Everything in the database is naive UTC, matching the rest of the app. Business
hours are the single exception: they are local wall-clock strings ("09:00") in
BusinessProfile.timezone. All conversion happens in this file and nowhere else,
which is what stops the classic "booked at the wrong hour" bug.
"""
from datetime import datetime, timedelta, date as date_cls, time as time_cls, timezone
from zoneinfo import ZoneInfo

from config import settings
from database import (
    SessionLocal, BusinessProfile, BusinessHours, ServiceType,
    Appointment, CalendarBusy,
)
from agents.calendar_agent import get_calendar_service

# If the Google busy cache hasn't refreshed successfully in this long, stop
# trusting it. Better to take a message than to double-book a real customer.
STALE_AFTER_MINUTES = 10

# How often the background loop refreshes the cache.
REFRESH_INTERVAL_SECONDS = 90


# ── small helpers ─────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    """Naive UTC, to match how every DateTime column in this app is stored."""
    return datetime.utcnow()


def get_profile(db) -> BusinessProfile:
    """The single settings row. Created on demand so nothing crashes on a fresh db."""
    profile = db.query(BusinessProfile).first()
    if not profile:
        profile = BusinessProfile(id=1)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def get_timezone(profile: BusinessProfile) -> ZoneInfo:
    try:
        return ZoneInfo(profile.timezone or "America/Los_Angeles")
    except Exception:
        # A typo in the timezone must not take down booking entirely.
        return ZoneInfo("America/Los_Angeles")


def _parse_hhmm(value: str, fallback: time_cls) -> time_cls:
    try:
        hours, _, minutes = (value or "").partition(":")
        return time_cls(int(hours), int(minutes))
    except Exception:
        return fallback


def local_to_utc(local_dt: datetime, tz: ZoneInfo) -> datetime:
    """Local wall clock -> naive UTC, the way everything is stored."""
    return local_dt.replace(tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local(utc_dt: datetime, tz: ZoneInfo) -> datetime:
    """Naive UTC -> local wall clock, for anything a human or caller will hear."""
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz)


def speak_time(local_dt: datetime) -> str:
    """How the AI should say a time out loud. Callers cannot see a screen."""
    hour = local_dt.hour % 12 or 12
    minute = f":{local_dt.minute:02d}" if local_dt.minute else ""
    meridiem = "AM" if local_dt.hour < 12 else "PM"
    return f"{local_dt.strftime('%A')} at {hour}{minute} {meridiem}"


def get_business_hours(db, weekday: int) -> BusinessHours | None:
    """Hours for one weekday. 0 = Monday … 6 = Sunday (Python's date.weekday())."""
    return db.query(BusinessHours).filter(BusinessHours.weekday == weekday).first()


# ── the Google busy cache ─────────────────────────────────────────────────────

def _record_cache_error(db, message: str) -> None:
    """Write why the last refresh failed, so a stale cache is never a mystery.

    Runs after a possible rollback, so it opens its own clean transaction and
    swallows its own errors — failing to log a failure must not raise a second one.
    """
    try:
        db.rollback()
        profile = get_profile(db)
        profile.busy_cache_error = (message or "")[:500]
        db.commit()
    except Exception as e:
        print(f"⚠️  Could not record calendar cache error: {e}")


def refresh_busy_cache(db=None) -> dict:
    """Pull busy blocks from Google into CalendarBusy. Safe to call on a loop.

    Uses the freebusy API, which returns only blocked time ranges — no event
    titles, no attendees, no customer names. Less data over the wire and nothing
    private cached locally.

    On ANY failure the existing cache is left exactly as it was and the error is
    recorded on BusinessProfile. Wiping the cache on failure would look like a
    free calendar, which is the one outcome we cannot allow.
    """
    owns_session = db is None
    db = db or SessionLocal()
    try:
        profile = get_profile(db)

        # get_calendar_service() does file I/O and can hit the network to refresh
        # an expired token, so it raises on its own. That IS an outage and has to
        # be recorded like one — an unexplained stale cache is impossible to debug.
        try:
            service = get_calendar_service()
        except Exception as e:
            _record_cache_error(db, f"google_auth_error: {e}")
            print(f"⚠️  Calendar auth failed (cache kept): {e}")
            return {"ok": False, "reason": "google_auth_error", "error": str(e), "blocks": 0}

        if not service:
            _record_cache_error(db, "google_not_configured")
            return {"ok": False, "reason": "google_not_configured", "blocks": 0}

        now = datetime.now(timezone.utc)
        window_end = now + timedelta(days=(profile.max_days_out or 30))

        try:
            response = service.freebusy().query(body={
                "timeMin": now.isoformat(),
                "timeMax": window_end.isoformat(),
                "items": [{"id": settings.google_calendar_id}],
            }).execute()
        except Exception as e:
            _record_cache_error(db, f"google_error: {e}")
            print(f"⚠️  Calendar busy refresh failed (cache kept): {e}")
            return {"ok": False, "reason": "google_error", "error": str(e), "blocks": 0}

        calendar_data = (response.get("calendars") or {}).get(
            settings.google_calendar_id, {}
        )
        # Google reports per-calendar problems in-band with a 200 response.
        # Treating that as "no busy times" is exactly the bug we are avoiding.
        if calendar_data.get("errors"):
            detail = str(calendar_data["errors"])[:400]
            _record_cache_error(db, f"calendar_error: {detail}")
            print(f"⚠️  Calendar busy refresh returned errors (cache kept): {detail}")
            return {"ok": False, "reason": "calendar_error", "error": detail, "blocks": 0}

        blocks = []
        for entry in calendar_data.get("busy", []):
            try:
                start = datetime.fromisoformat(entry["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(entry["end"].replace("Z", "+00:00"))
            except Exception:
                continue
            blocks.append((
                start.astimezone(timezone.utc).replace(tzinfo=None),
                end.astimezone(timezone.utc).replace(tzinfo=None),
            ))

        # Swap the cache only now that we have a good result in hand.
        fetched_at = _utcnow()
        db.query(CalendarBusy).filter(CalendarBusy.source == "google").delete()
        for start, end in blocks:
            db.add(CalendarBusy(
                start_time=start, end_time=end,
                source="google", fetched_at=fetched_at,
            ))

        profile.busy_cache_synced_at = fetched_at
        profile.busy_cache_error = ""
        db.commit()
        return {"ok": True, "blocks": len(blocks), "synced_at": fetched_at.isoformat()}

    except Exception as e:
        db.rollback()
        _record_cache_error(db, f"exception: {e}")
        print(f"⚠️  Calendar busy refresh crashed (cache kept): {e}")
        return {"ok": False, "reason": "exception", "error": str(e), "blocks": 0}
    finally:
        if owns_session:
            db.close()


def cache_status(db) -> dict:
    """Is the busy cache fresh enough to book against?"""
    profile = get_profile(db)
    synced_at = profile.busy_cache_synced_at
    if not synced_at:
        return {
            "fresh": False, "reason": "never_synced",
            "synced_at": None, "age_seconds": None,
            "error": profile.busy_cache_error or "",
        }
    age = (_utcnow() - synced_at).total_seconds()
    return {
        "fresh": age <= STALE_AFTER_MINUTES * 60,
        "reason": "ok" if age <= STALE_AFTER_MINUTES * 60 else "stale",
        "synced_at": synced_at.isoformat(),
        "age_seconds": int(age),
        "error": profile.busy_cache_error or "",
    }


# ── finding open slots ────────────────────────────────────────────────────────

def _busy_ranges(db, window_start: datetime, window_end: datetime) -> list[tuple]:
    """Every blocked range in the window: Google's cache plus NOVA's own bookings.

    Held rows count as busy only until they expire, so a caller who hangs up
    mid-booking releases the time automatically with no cleanup job required.
    """
    now = _utcnow()
    ranges = []

    cached = (db.query(CalendarBusy)
              .filter(CalendarBusy.end_time > window_start)
              .filter(CalendarBusy.start_time < window_end)
              .all())
    ranges += [(b.start_time, b.end_time) for b in cached]

    booked = (db.query(Appointment)
              .filter(Appointment.status.in_(["held", "booked"]))
              .filter(Appointment.end_time > window_start)
              .filter(Appointment.start_time < window_end)
              .all())
    for appt in booked:
        if appt.status == "held":
            if not appt.hold_expires_at or appt.hold_expires_at <= now:
                continue  # expired hold — the time is free again
        ranges.append((appt.start_time, appt.end_time))

    return ranges


def _overlaps(start: datetime, end: datetime, ranges: list[tuple]) -> bool:
    return any(start < busy_end and end > busy_start for busy_start, busy_end in ranges)


def find_open_slots(db, day, service_id: int | None = None, limit: int = 3) -> dict:
    """Open start times on one local calendar day.

    `day` is a date (or "YYYY-MM-DD") in the BUSINESS's local timezone, because
    that is what a caller means by "Tuesday".

    Returns at most `limit` times — three is the practical ceiling for a phone
    call, since a caller cannot hold more options than that in their head.

    Always returns a dict. Check `degraded` before reading `slots`: when it is
    True the calendar could not be trusted and the AI must take a message
    instead of confirming anything.
    """
    profile = get_profile(db)
    tz = get_timezone(profile)

    if isinstance(day, str):
        try:
            day = date_cls.fromisoformat(day)
        except ValueError:
            return {"ok": False, "degraded": True, "reason": "bad_date",
                    "message": "Date must look like 2026-07-28.", "slots": []}
    elif isinstance(day, datetime):
        day = day.date()

    # Refuse to trust a stale calendar rather than risk a double-booking.
    status = cache_status(db)
    if not status["fresh"]:
        return {
            "ok": False, "degraded": True, "reason": status["reason"],
            "message": "Calendar is not in sync right now, so times can't be confirmed.",
            "slots": [], "cache": status,
        }

    service = None
    if service_id:
        service = db.query(ServiceType).filter(ServiceType.id == service_id).first()
        if not service:
            return {"ok": False, "degraded": False, "reason": "unknown_service",
                    "message": "That service doesn't exist.", "slots": []}
    else:
        service = (db.query(ServiceType)
                   .filter(ServiceType.active.is_(True))
                   .order_by(ServiceType.sort, ServiceType.id)
                   .first())
    if not service:
        return {"ok": False, "degraded": False, "reason": "no_services",
                "message": "No services are set up yet.", "slots": []}

    duration = timedelta(minutes=service.duration_minutes or 60)

    # How far ahead is this day? Refuse dates outside the booking window.
    today_local = utc_to_local(_utcnow(), tz).date()
    if day < today_local:
        return {"ok": False, "degraded": False, "reason": "in_the_past",
                "message": "That day has already passed.", "slots": []}
    if (day - today_local).days > (profile.max_days_out or 30):
        return {"ok": False, "degraded": False, "reason": "too_far_out",
                "message": f"Bookings only go {profile.max_days_out} days ahead.",
                "slots": []}

    hours = get_business_hours(db, day.weekday())
    if not hours or hours.closed:
        return {"ok": True, "degraded": False, "reason": "closed",
                "message": f"Closed on {day.strftime('%A')}.",
                "slots": [], "service": {"id": service.id, "name": service.name}}

    open_local = datetime.combine(day, _parse_hhmm(hours.open_time, time_cls(9, 0)))
    close_local = datetime.combine(day, _parse_hhmm(hours.close_time, time_cls(17, 0)))
    if close_local <= open_local:
        return {"ok": False, "degraded": False, "reason": "bad_hours",
                "message": "Opening and closing times for this day don't make sense.",
                "slots": []}

    window_start = local_to_utc(open_local, tz)
    window_end = local_to_utc(close_local, tz)
    busy = _busy_ranges(db, window_start, window_end)

    earliest = _utcnow() + timedelta(minutes=profile.booking_lead_time_minutes or 0)
    step = timedelta(minutes=profile.slot_granularity_minutes or 15)

    slots = []
    cursor = window_start
    while cursor + duration <= window_end:
        slot_end = cursor + duration
        if cursor >= earliest and not _overlaps(cursor, slot_end, busy):
            local_start = utc_to_local(cursor, tz)
            slots.append({
                "start_utc": cursor.isoformat(),
                "end_utc": slot_end.isoformat(),
                "start_local": local_start.isoformat(),
                "spoken": speak_time(local_start),
            })
            if len(slots) >= limit:
                break
        cursor += step

    return {
        "ok": True,
        "degraded": False,
        "reason": "ok" if slots else "fully_booked",
        "message": "" if slots else f"Nothing open on {day.strftime('%A')}.",
        "date": day.isoformat(),
        "timezone": profile.timezone,
        "service": {
            "id": service.id,
            "name": service.name,
            "duration_minutes": service.duration_minutes,
        },
        "slots": slots,
        "cache": status,
    }


def slot_is_bookable(db, start_utc: datetime, service: ServiceType) -> dict:
    """Can this exact start time still be booked?

    Called just before writing a booking. Everything here is also enforced by
    find_open_slots(), but a caller can name a time that was never offered — and
    a voice assistant can be talked into trying one. Never trust the requested
    time just because it came back through the AI.

    This is the last soft check. The genuinely authoritative guard against two
    callers taking the same slot is the unique index in the database.
    """
    profile = get_profile(db)
    tz = get_timezone(profile)

    status = cache_status(db)
    if not status["fresh"]:
        return {"ok": False, "degraded": True, "reason": status["reason"],
                "message": "Calendar is not in sync, so nothing can be confirmed."}

    duration = timedelta(minutes=service.duration_minutes or 60)
    end_utc = start_utc + duration
    local_start = utc_to_local(start_utc, tz)

    earliest = _utcnow() + timedelta(minutes=profile.booking_lead_time_minutes or 0)
    if start_utc < earliest:
        return {"ok": False, "degraded": False, "reason": "too_soon",
                "message": "That's too soon to book."}

    if (local_start.date() - utc_to_local(_utcnow(), tz).date()).days > (profile.max_days_out or 30):
        return {"ok": False, "degraded": False, "reason": "too_far_out",
                "message": f"Bookings only go {profile.max_days_out} days ahead."}

    hours = get_business_hours(db, local_start.weekday())
    if not hours or hours.closed:
        return {"ok": False, "degraded": False, "reason": "closed",
                "message": f"Closed on {local_start.strftime('%A')}."}

    day = local_start.date()
    open_utc = local_to_utc(
        datetime.combine(day, _parse_hhmm(hours.open_time, time_cls(9, 0))), tz)
    close_utc = local_to_utc(
        datetime.combine(day, _parse_hhmm(hours.close_time, time_cls(17, 0))), tz)
    if start_utc < open_utc or end_utc > close_utc:
        return {"ok": False, "degraded": False, "reason": "outside_hours",
                "message": f"That's outside {hours.open_time}-{hours.close_time}."}

    if _overlaps(start_utc, end_utc, _busy_ranges(db, open_utc, close_utc)):
        return {"ok": False, "degraded": False, "reason": "just_taken",
                "message": "That time is no longer available."}

    return {"ok": True, "degraded": False, "reason": "ok",
            "start_utc": start_utc, "end_utc": end_utc,
            "spoken": speak_time(local_start)}


def find_next_open_slots(db, service_id: int | None = None,
                         limit: int = 3, search_days: int = 14) -> dict:
    """The soonest open times, looking forward day by day.

    This is what the AI reaches for when a caller says "whenever you have
    something" or when their first choice is already taken.
    """
    profile = get_profile(db)
    tz = get_timezone(profile)
    start_day = utc_to_local(_utcnow(), tz).date()

    collected = []
    for offset in range(min(search_days, (profile.max_days_out or 30) + 1)):
        result = find_open_slots(db, start_day + timedelta(days=offset),
                                 service_id=service_id, limit=limit)
        if result.get("degraded"):
            return result  # calendar untrustworthy — stop, don't guess
        collected += result.get("slots", [])
        if len(collected) >= limit:
            break

    return {
        "ok": True, "degraded": False,
        "reason": "ok" if collected else "nothing_open",
        "slots": collected[:limit],
        "timezone": profile.timezone,
    }
