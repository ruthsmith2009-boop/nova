"""
Calendar Agent — Google Calendar integration for scheduling and follow-ups.
"""
import os
import json
from datetime import datetime, timedelta
from typing import Optional

from config import settings

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_calendar_service():
    """Get authenticated Google Calendar service."""
    if not GOOGLE_AVAILABLE:
        return None

    creds = None
    token_file = settings.google_calendar_token_file
    creds_file = settings.google_calendar_credentials_file

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif os.path.exists(creds_file):
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_file, "w") as f:
                f.write(creds.to_json())
        else:
            return None

    return build("calendar", "v3", credentials=creds)


def create_event(title: str, start_time: datetime, end_time: datetime,
                 location: str = "", description: str = "",
                 attendee_emails: list[str] = None) -> dict:
    """Create a Google Calendar event."""
    service = get_calendar_service()
    if not service:
        return {
            "status": "google_not_configured",
            "message": "Google Calendar not set up. Add credentials.json to enable.",
            "event": {
                "title": title, "start": start_time.isoformat(),
                "end": end_time.isoformat(), "location": location
            }
        }

    event = {
        "summary": title,
        "location": location,
        "description": description,
        "start": {"dateTime": start_time.isoformat(), "timeZone": "America/Los_Angeles"},
        "end": {"dateTime": end_time.isoformat(), "timeZone": "America/Los_Angeles"},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 60},
                {"method": "popup", "minutes": 15},
            ]
        }
    }

    if attendee_emails:
        event["attendees"] = [{"email": e} for e in attendee_emails]
        event["sendUpdates"] = "all"

    try:
        created = service.events().insert(
            calendarId=settings.google_calendar_id, body=event
        ).execute()
        return {"status": "created", "event_id": created.get("id"), "link": created.get("htmlLink")}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def schedule_listing_appointment(lead: dict, appointment_dt: datetime) -> dict:
    """Schedule a listing appointment with the seller."""
    end_time = appointment_dt + timedelta(hours=1, minutes=30)
    title = f"Listing Appointment — {lead.get('first_name','')} {lead.get('last_name','')} | {lead.get('address','')}"
    description = (
        f"Listing presentation for {lead.get('address','')}, {lead.get('city','')}.\n"
        f"Contact: {lead.get('phone','')} | {lead.get('email','')}\n"
        f"Lead score: {lead.get('score', 'N/A')}/100\n"
        f"Situation: {lead.get('life_event','')}"
    )
    attendees = [lead.get("email")] if lead.get("email") else []
    if settings.agent_email:
        attendees.append(settings.agent_email)

    return create_event(title, appointment_dt, end_time,
                        location=lead.get("address",""), description=description,
                        attendee_emails=attendees)


def schedule_follow_up(lead: dict, follow_up_dt: datetime, note: str = "") -> dict:
    """Schedule a follow-up reminder."""
    end_time = follow_up_dt + timedelta(minutes=30)
    title = f"Follow-up — {lead.get('first_name','')} {lead.get('last_name','')} | {lead.get('address','')}"
    return create_event(title, follow_up_dt, end_time, description=note or f"Follow up on {lead.get('address','')}")


def schedule_open_house(listing: dict, open_house_dt: datetime, duration_hours: float = 2) -> dict:
    """Schedule an open house."""
    end_time = open_house_dt + timedelta(hours=duration_hours)
    title = f"Open House — {listing.get('address','')}, {listing.get('city','')}"
    return create_event(
        title, open_house_dt, end_time,
        location=listing.get("address",""),
        description=f"List price: ${listing.get('list_price',0):,.0f}\nBeds: {listing.get('bedrooms','')}, Baths: {listing.get('bathrooms','')}"
    )


def get_upcoming_events(days: int = 7) -> list[dict]:
    """Get upcoming calendar events."""
    service = get_calendar_service()
    if not service:
        return []

    try:
        now = datetime.utcnow().isoformat() + "Z"
        future = (datetime.utcnow() + timedelta(days=days)).isoformat() + "Z"
        events_result = service.events().list(
            calendarId=settings.google_calendar_id,
            timeMin=now, timeMax=future,
            maxResults=50, singleEvents=True, orderBy="startTime"
        ).execute()
        return events_result.get("items", [])
    except Exception:
        return []
