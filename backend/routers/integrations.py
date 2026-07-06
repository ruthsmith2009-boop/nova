"""
Integrations hub — one place to see every external connector and whether it's set up.

Each connector reports connected=true once its API key/token/consent is present.
Wiring the live API calls happens when the user connects their account (OAuth consent);
this gives the UI + config foundation so turning one on later is just completing sign-in.
"""
from fastapi import APIRouter
from config import settings

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _c(value) -> bool:
    return bool(value)


@router.get("/")
def list_integrations():
    s = settings
    google_ready = _c(s.google_oauth_client_id) or _c(s.gmail_connected)
    gmail = _c(s.gmail_connected) or _c(s.sendgrid_api_key)
    cal = _c(s.gmail_connected) or _c(s.google_oauth_client_id)
    return {
        "google": [
            {"key": "gmail", "name": "Gmail", "icon": "📧",
             "connected": gmail, "account": s.google_account_email,
             "note": f"Send + read email as {s.google_account_email}. Powers NOVA's outreach & follow-ups.",
             "env": "GOOGLE_OAUTH_CLIENT_ID"},
            {"key": "gcal", "name": "Google Calendar", "icon": "📅",
             "connected": cal, "account": s.google_account_email,
             "note": "Booked chats land on your calendar with a Google Meet link auto-attached.",
             "env": "GOOGLE_OAUTH_CLIENT_ID"},
            {"key": "gcontacts", "name": "Google Contacts", "icon": "👥",
             "connected": _c(s.google_contacts_connected) or cal, "account": s.google_account_email,
             "note": "Sync leads two ways so every new client is in your phone.",
             "env": "GOOGLE_OAUTH_CLIENT_ID"},
            {"key": "gdrive", "name": "Google Drive", "icon": "📂",
             "connected": _c(s.google_drive_connected) or cal, "account": s.google_account_email,
             "note": "Store proposals, contracts, and call recordings.",
             "env": "GOOGLE_OAUTH_CLIENT_ID"},
            {"key": "gmeet", "name": "Google Meet", "icon": "🎥",
             "connected": cal, "account": s.google_account_email,
             "note": "Auto-generate a video link for every booked demo.",
             "env": "GOOGLE_OAUTH_CLIENT_ID"},
        ],
        "microsoft": [
            {"key": "outlook", "name": "Outlook / Microsoft 365 Email", "icon": "📨",
             "connected": _c(s.microsoft_client_id), "account": s.microsoft_account_email or "not connected",
             "note": "Optional — connect a Microsoft 365 / Outlook mailbox instead of (or alongside) Gmail.",
             "env": "MICROSOFT_CLIENT_ID"},
            {"key": "ms_calendar", "name": "Outlook Calendar", "icon": "🗓️",
             "connected": _c(s.microsoft_client_id), "account": s.microsoft_account_email or "not connected",
             "note": "Optional — book chats on a Microsoft 365 calendar.",
             "env": "MICROSOFT_CLIENT_ID"},
            {"key": "copilot", "name": "Microsoft Copilot", "icon": "🤖",
             "connected": _c(s.microsoft_copilot_enabled), "account": s.microsoft_account_email or "not connected",
             "note": "Optional — let NOVA hand tasks to Microsoft Copilot in your Microsoft 365 apps.",
             "env": "MICROSOFT_COPILOT_ENABLED"},
        ],
        "ai_brain": [
            {"key": "anthropic", "name": "Claude (AI brain)", "icon": "🧠",
             "connected": _c(s.anthropic_api_key), "note": "Powers NOVA's intelligence.",
             "env": "ANTHROPIC_API_KEY"},
            {"key": "tavily", "name": "Tavily (web research)", "icon": "🔎",
             "connected": _c(s.tavily_api_key), "note": "Live web + business research.",
             "env": "TAVILY_API_KEY"},
        ],
        "phone_calling": [
            {"key": "vapi", "name": "Vapi (AI calling)", "icon": "🤖",
             "connected": _c(s.vapi_api_key), "note": "AI voice calls — inbound answering & outbound follow-up.",
             "env": "VAPI_API_KEY"},
            {"key": "twilio", "name": "Twilio (phone line)", "icon": "📞",
             "connected": _c(s.twilio_account_sid), "note": "The business phone number NOVA calls & texts from.",
             "env": "TWILIO_ACCOUNT_SID"},
        ],
        "automation": [
            {"key": "zapier", "name": "Zapier", "icon": "⚡",
             "connected": _c(s.zapier_webhook_url),
             "note": "Send new leads, booked jobs & missed calls to 7,000+ apps. Paste your Zap's webhook URL to connect.",
             "env": "ZAPIER_WEBHOOK_URL"},
            {"key": "make", "name": "Make (Integromat)", "icon": "🔧",
             "connected": _c(s.make_webhook_url),
             "note": "Build visual multi-step automations. Paste your Make scenario webhook URL to connect.",
             "env": "MAKE_WEBHOOK_URL"},
            {"key": "n8n", "name": "n8n", "icon": "🔗",
             "connected": _c(s.n8n_webhook_url),
             "note": "Self-hosted, no per-task fees. Paste your n8n Webhook node URL to connect.",
             "env": "N8N_WEBHOOK_URL"},
        ],
    }
