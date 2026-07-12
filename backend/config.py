from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    tavily_api_key: str = ""
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "owner@example.com"
    sendgrid_from_name: str = "Your Business"

    # ── Google Workspace (one OAuth connects Gmail, Calendar, Drive, Contacts, Meet) ──
    google_account_email: str = "owner@example.com"   # the Google account NOVA connects to
    google_oauth_client_id: Optional[str] = None
    google_oauth_client_secret: Optional[str] = None
    google_calendar_credentials_file: str = "credentials.json"
    google_calendar_token_file: str = "token.json"
    google_calendar_id: str = "primary"
    gmail_connected: bool = False       # flips true after the OAuth consent is completed
    google_drive_connected: bool = False
    google_contacts_connected: bool = False

    # ── Microsoft 365 (optional — Outlook email + Copilot) ──
    microsoft_account_email: Optional[str] = None
    microsoft_client_id: Optional[str] = None
    microsoft_client_secret: Optional[str] = None
    microsoft_copilot_enabled: bool = False

    app_secret_key: str = "change-me"
    database_url: str = "sqlite:///./nova.db"

    # ── Identity / branding (set these in .env — defaults are neutral placeholders) ──
    business_name: str = "NOVA"          # the app/brand name shown to the client
    agent_name: str = "Your Name"        # owner / primary user
    agent_license: str = ""
    broker_name: str = "Your Business"
    agent_phone: str = "(555) 555-0100"
    agent_email: str = "owner@example.com"

    primary_market: str = "United States (any industry)"
    openai_api_key: Optional[str] = None

    # Facebook / Instagram (Meta Graph API)
    facebook_page_access_token: Optional[str] = None
    facebook_page_id: Optional[str] = None
    instagram_account_id: Optional[str] = None   # Instagram Business Account ID

    # Twitter / X (API v2)
    twitter_api_key: Optional[str] = None
    twitter_api_secret: Optional[str] = None
    twitter_access_token: Optional[str] = None
    twitter_access_token_secret: Optional[str] = None

    # LinkedIn
    linkedin_access_token: Optional[str] = None
    linkedin_person_urn: Optional[str] = None    # e.g. "urn:li:person:ABC123"

    # ── AI Calling (Vapi + Twilio) ──
    vapi_api_key: Optional[str] = None
    vapi_phone_number_id: Optional[str] = None    # Vapi-managed phone number ID
    vapi_assistant_id: Optional[str] = None       # optional pre-built assistant
    # Voice per client. For provider "vapi" this is a Vapi voice name (Clara, Godfrey,
    # Elliot, Savannah, Nico, Kai, Emma, Sagar, Neil, Layla, Sid, Gustavo, Kylie, Rohan,
    # Lily, Hana, Neha, Cole, Harry, Paige, Spencer, Naina, Leah, Tara, Jess, Leo, Dan,
    # Mia, Zac, Zoe). For provider "11labs" it is an ElevenLabs voice ID (e.g. a voice
    # cloned for the client). VAPI_DEFAULT_VOICE is accepted as a legacy env name.
    vapi_voice: str = Field("Savannah",
                            validation_alias=AliasChoices("VAPI_VOICE", "VAPI_DEFAULT_VOICE"))
    vapi_voice_provider: str = "vapi"             # "vapi" (stock) or "11labs" (cloned voices)

    # The client-facing business phone number (the Twilio number imported into Vapi),
    # E.164 e.g. +14085550100 — shown in emails/UI; distinct from TWILIO_PHONE_NUMBER creds.
    business_phone_number: str = Field("", validation_alias=AliasChoices(
        "NOVA_PHONE_NUMBER", "BUSINESS_PHONE_NUMBER"))

    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None     # your purchased number, E.164 e.g. +14085550100

    # Public base URL for receiving call webhooks (e.g. ngrok or deployed domain)
    public_base_url: Optional[str] = None

    # ── Paid lead-data providers (optional — for verified business contacts w/ emails & phones) ──
    apollo_api_key: Optional[str] = None

    # Shared secret for the inbound lead webhook (Zapier). If set, callers must pass ?token=
    leadgen_webhook_token: Optional[str] = None

    # Shared secret for the Vapi call webhook. If set, Vapi must send it in the
    # x-vapi-secret header (or ?token= query param) or the webhook returns 401.
    # If unset, the webhook stays open (backward compatible) and logs a warning.
    vapi_webhook_secret: str = ""

    # ── Automation platforms (no-code) ──
    # NOVA pushes events (new lead, booked job, missed call) to these webhook URLs so a
    # scenario/workflow can fan them out to any of 1000s of apps. Leave blank to show "Connect".
    zapier_webhook_url: Optional[str] = None
    make_webhook_url: Optional[str] = None       # Make.com (formerly Integromat)
    n8n_webhook_url: Optional[str] = None

    # Login wall for the deployed app. If both set, the dashboard + API require these.
    # Leave blank for local development (no login prompt).
    # Reads APP_USERNAME / APP_PASSWORD, falling back to the legacy
    # ARIA_USERNAME / ARIA_PASSWORD vars still set on existing deployments.
    app_username: Optional[str] = None
    app_password: Optional[str] = None

    # External storage connectors (optional — connect later with the user's accounts):
    dropbox_access_token: Optional[str] = None

    def model_post_init(self, __context) -> None:
        import os
        # Legacy login vars: existing deployments set ARIA_USERNAME/ARIA_PASSWORD.
        # Prefer the new APP_USERNAME/APP_PASSWORD, but fall back so nothing breaks.
        if not self.app_username:
            self.app_username = os.environ.get("ARIA_USERNAME") or None
        if not self.app_password:
            self.app_password = os.environ.get("ARIA_PASSWORD") or None
        # On Railway the public URL is provided automatically as
        # RAILWAY_PUBLIC_DOMAIN (e.g. "aria-re-production.up.railway.app").
        # If public_base_url wasn't set explicitly, derive it from that so the
        # AI-calling result webhook and lead-alert links work in production with
        # no manual config. Locally (no Railway vars) it stays None, and you set
        # PUBLIC_BASE_URL to an ngrok URL only when testing calls on your Mac.
        if not self.public_base_url:
            import os
            domain = (os.environ.get("RAILWAY_PUBLIC_DOMAIN")
                      or os.environ.get("RAILWAY_STATIC_URL"))
            if domain:
                if not domain.startswith("http"):
                    domain = f"https://{domain}"
                self.public_base_url = domain.rstrip("/")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
