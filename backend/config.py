from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    tavily_api_key: str = ""
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "ruth@example.com"
    sendgrid_from_name: str = "Ruth Smith | AI With Ruth"

    # ── Google Workspace (one OAuth connects Gmail, Calendar, Drive, Contacts, Meet) ──
    google_account_email: str = "airuthsmith@gmail.com"   # the Google account NOVA connects to
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

    agent_name: str = "Ruth Smith"
    agent_license: str = ""
    broker_name: str = "AI With Ruth"
    agent_phone: str = "(408) 555-0100"
    agent_email: str = "airuthsmith@gmail.com"

    primary_market: str = "San Jose & Santa Clara County, CA — Bay Area (serves all US markets)"
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
    vapi_default_voice: str = "Savannah"          # Vapi voice name (must be a valid Vapi voice: Clara, Godfrey, Elliot, Savannah, Nico, Kai, Emma, Sagar, Neil, Layla, Sid, Gustavo, Kylie, Rohan, Lily, Hana, Neha, Cole, Harry, Paige, Spencer, Naina, Leah, Tara, Jess, Leo, Dan, Mia, Zac, Zoe)

    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None     # your purchased number, E.164 e.g. +14085550100

    # Public base URL for receiving call webhooks (e.g. ngrok or deployed domain)
    public_base_url: Optional[str] = None

    # ── Paid lead-data providers (optional — for verified leads w/ phone numbers) ──
    redx_api_key: Optional[str] = None
    batchleads_api_key: Optional[str] = None
    propstream_api_key: Optional[str] = None

    # Shared secret for the inbound lead webhook (Zapier). If set, callers must pass ?token=
    leadgen_webhook_token: Optional[str] = None

    # Login wall for the deployed app. If both set, the dashboard + API require these.
    # Leave blank for local development (no login prompt).
    aria_username: Optional[str] = None
    aria_password: Optional[str] = None

    # ── Document storage (3-year broker compliance) ──
    # Where uploaded compliance docs are stored. On Railway set DOCUMENTS_DIR=/data/documents
    # (the persistent volume). Blank → auto: /data/documents if /data exists, else ./data/documents.
    documents_dir: Optional[str] = None
    # External storage connectors (optional — connect later with the user's accounts):
    dropbox_access_token: Optional[str] = None
    skyslope_api_key: Optional[str] = None
    glide_api_key: Optional[str] = None

    # ── Transaction / e-sign / MLS integrations (scaffolding — connect later) ──
    docusign_api_key: Optional[str] = None
    mls_api_key: Optional[str] = None          # e.g. RESO Web API / Bridge / SimplyRETS
    zipforms_api_key: Optional[str] = None
    disclosures_api_key: Optional[str] = None  # Glide / Disclosures.io

    def model_post_init(self, __context) -> None:
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
