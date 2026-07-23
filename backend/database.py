from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Text,
    Boolean, JSON, ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum

from config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class LeadStage(str, enum.Enum):
    new = "new"
    contacted = "contacted"
    appointment_set = "appointment_set"
    under_contract = "under_contract"
    closed = "closed"
    dead = "dead"


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(200))
    phone = Column(String(50))
    address = Column(String(300))
    city = Column(String(100))
    state = Column(String(20), nullable=True)
    zip_code = Column(String(20))
    property_type = Column(String(50))

    # Lead scoring fields
    score = Column(Float, default=0.0)
    score_reasons = Column(JSON, default=list)
    equity_estimate = Column(Float, nullable=True)
    years_owned = Column(Integer, nullable=True)
    is_absentee = Column(Boolean, default=False)
    has_expired_listing = Column(Boolean, default=False)
    days_on_market = Column(Integer, nullable=True)
    price_reductions = Column(Integer, default=0)
    life_event = Column(String(100), nullable=True)  # divorce, probate, job_change

    # CRM fields
    # Stored as a plain string (not a DB enum) so legacy stage values in existing
    # databases (e.g. the retired "listing_active") load without crashing.
    stage = Column(String(30), default=LeadStage.new.value)
    temperature = Column(String(20), default="cold")  # hot | warm | cold | not_ready
    follow_up_cadence = Column(String(30), nullable=True)  # weekly, biweekly, monthly, 90_day, quarterly, 6_month, yearly, 1_2_year, not_ready_7day
    source = Column(String(100))
    notes = Column(Text, default="")
    last_contact = Column(DateTime, nullable=True)
    next_follow_up = Column(DateTime, nullable=True)
    assigned_script = Column(String(100), nullable=True)

    # Soft delete — deleted leads are hidden from the CRM but recoverable.
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)

    # Team assignment (multi-user foundation) — which team member owns this lead.
    assigned_to = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    touchpoints = relationship("Touchpoint", back_populates="lead", cascade="all, delete-orphan")


class Touchpoint(Base):
    __tablename__ = "touchpoints"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    type = Column(String(50))  # call, email, text, meeting, note
    direction = Column(String(20))  # inbound, outbound
    summary = Column(Text)
    outcome = Column(String(100))  # no_answer, left_vm, connected, appointment_set
    duration_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    lead = relationship("Lead", back_populates="touchpoints")


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    area = Column(String(200))
    snapshot_date = Column(DateTime, default=datetime.utcnow)
    median_price = Column(Float, nullable=True)
    avg_dom = Column(Float, nullable=True)
    active_listings = Column(Integer, nullable=True)
    sold_last_30 = Column(Integer, nullable=True)
    absorption_rate = Column(Float, nullable=True)
    list_to_sale_ratio = Column(Float, nullable=True)
    raw_data = Column(JSON, default=dict)


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    to_email = Column(String(200))
    subject = Column(String(500))
    body_preview = Column(Text)
    status = Column(String(50))  # sent, failed, pending_approval
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SyncedEmail(Base):
    """One row per email seen in the Zoho mailbox — the dedupe ledger for zoho_sync.

    message_id is the RFC Message-ID header, unique so a re-run never double-logs.
    """
    __tablename__ = "synced_emails"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(500), unique=True, index=True)
    direction = Column(String(20))  # inbound, outbound
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    address = Column(String(200))   # the other party's email address
    subject = Column(String(500))
    email_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    google_event_id = Column(String(200), nullable=True)
    title = Column(String(300))
    event_type = Column(String(100))  # listing_appointment, follow_up, open_house, inspection
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    location = Column(String(300), nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class SocialPost(Base):
    __tablename__ = "social_posts"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, nullable=True)  # legacy reference (listings table removed)
    content_type = Column(String(100))   # listing, market_update, just_sold, open_house, tip, custom
    subject = Column(String(500))
    platforms = Column(JSON, default=list)
    generated_content = Column(JSON, default=dict)  # all platform content stored here
    image_url = Column(String(500), nullable=True)
    status = Column(String(50), default="pending_approval")  # pending_approval, approved, published, rejected
    publish_results = Column(JSON, default=dict)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    scheduled_for = Column(DateTime, nullable=True)


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200))
    goal = Column(String(300))  # e.g. "Book listing appointments", "Qualify sellers"
    script = Column(Text)        # the AI calling script / first message + prompt
    voice_id = Column(String(100), nullable=True)   # Vapi voice
    status = Column(String(50), default="draft")  # draft, running, paused, stopped, completed
    lead_ids = Column(JSON, default=list)          # leads enrolled in this campaign
    call_window_start = Column(String(10), default="09:00")  # local time HH:MM
    call_window_end = Column(String(10), default="18:00")
    max_attempts = Column(Integer, default=3)
    notify_email = Column(String(200), nullable=True)

    # Stats
    total_leads = Column(Integer, default=0)
    calls_placed = Column(Integer, default=0)
    calls_connected = Column(Integer, default=0)
    interested_count = Column(Integer, default=0)
    appointments_set = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CallRecord(Base):
    __tablename__ = "call_records"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    phone_number = Column(String(50))

    provider = Column(String(50), default="vapi")  # vapi, bland, twilio
    provider_call_id = Column(String(200), nullable=True)

    status = Column(String(50), default="queued")  # queued, ringing, in_progress, completed, failed, no_answer, voicemail
    disposition = Column(String(100), nullable=True)  # maps to pipeline: interested, not_interested, follow_up, etc.
    attempt_number = Column(Integer, default=1)

    duration_seconds = Column(Integer, nullable=True)
    recording_url = Column(String(500), nullable=True)
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)

    # Captured during call
    decision_maker_name = Column(String(200), nullable=True)
    decision_maker_available = Column(Boolean, nullable=True)
    best_callback_time = Column(String(200), nullable=True)
    captured_email = Column(String(200), nullable=True)
    business_name = Column(String(200), nullable=True)
    custom_notes = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    follow_up_at = Column(DateTime, nullable=True)


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, default=datetime.utcnow)
    amount = Column(Float)
    vendor = Column(String(200))
    description = Column(String(500), default="")
    category = Column(String(100))          # e.g. "AI APIs", "Marketing", "Software & SaaS"
    segment = Column(String(30), default="business")  # business | ai_tech | shared
    recurrence = Column(String(20), default="one_time")  # one_time | monthly | yearly
    is_tax_deductible = Column(Boolean, default=True)
    payment_method = Column(String(100), nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class ScheduledHunt(Base):
    """A saved lead hunt that NOVA runs automatically on a cadence (hands-off auto-leads)."""
    __tablename__ = "scheduled_hunts"

    id = Column(Integer, primary_key=True, index=True)
    hunt_type = Column(String(40))            # ideal_clients | local_businesses | referral_partners
    city = Column(String(120), default="")
    state = Column(String(20), default="")
    neighborhood = Column(String(120), default="")
    niche = Column(String(120), default="")
    provider = Column(String(40), default="tavily")
    frequency = Column(String(20), default="daily")   # hourly | daily | weekly
    enabled = Column(Boolean, default=True)

    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    last_found = Column(Integer, default=0)
    last_saved = Column(Integer, default=0)
    total_saved = Column(Integer, default=0)
    last_status = Column(String(300), default="")

    created_at = Column(DateTime, default=datetime.utcnow)


class TeamMember(Base):
    """A member of the brokerage team (multi-user foundation). The app still has one shared
    login for now; this powers lead assignment and a manager roster/overview."""
    __tablename__ = "team_members"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150))
    email = Column(String(200), default="")
    phone = Column(String(50), default="")
    role = Column(String(40), default="agent")     # agent | manager | admin | transaction_coordinator
    active = Column(Boolean, default=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Script(Base):
    """A custom call/objection script Ruth uploads (on top of the built-in SCRIPT_LIBRARY)."""
    __tablename__ = "scripts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))
    category = Column(String(80), default="Custom")   # Custom, Cold Outreach, Follow-Up, Objection, Closing, etc.
    author = Column(String(120), default="")          # e.g. Tom Ferry (optional)
    content = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class ChecklistItem(Base):
    """A transaction milestone for a listing (listing → close). Tracks compliance/deal steps."""
    __tablename__ = "checklist_items"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, nullable=True)  # legacy reference (listings table removed)
    label = Column(String(300))
    done = Column(Boolean, default=False)
    sort = Column(Integer, default=0)
    done_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MessageTemplate(Base):
    """A reusable email/text outreach template with merge fields like {first_name}."""
    __tablename__ = "message_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200))
    channel = Column(String(20), default="email")   # email | text
    subject = Column(String(300), default="")        # used for email
    body = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class SmsOptOut(Base):
    """A phone number that replied STOP — never text it again. Twilio also blocks
    STOP'd numbers at the carrier level; this is belt-and-suspenders on our side."""
    __tablename__ = "sms_opt_outs"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(50), unique=True, index=True)   # E.164
    created_at = Column(DateTime, default=datetime.utcnow)


class SmsLog(Base):
    """Every SMS in/out. Outbound kind='textback' rows double as the missed-call
    dedupe: a number never gets more than one text-back per 24 hours."""
    __tablename__ = "sms_logs"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    phone = Column(String(50), index=True)                 # E.164
    direction = Column(String(20))                         # inbound | outbound
    kind = Column(String(40), default="")                  # textback | reply | inbound | opt_out
    body = Column(Text, default="")
    status = Column(String(50), default="")                # sent | failed | received | skipped
    created_at = Column(DateTime, default=datetime.utcnow)


class Document(Base):
    """A stored compliance/transaction document. CA brokers must retain records 3 years."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(300))                     # stored filename on disk
    original_name = Column(String(300))                # name as uploaded
    content_type = Column(String(120), default="")
    size_bytes = Column(Integer, default=0)
    category = Column(String(80), default="Other")     # RLA, TDS, Disclosure, Contract, ID, Other
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    listing_id = Column(Integer, nullable=True)  # legacy reference (listings table removed)
    notes = Column(Text, default="")
    storage = Column(String(40), default="local")      # local | dropbox | skyslope | glide
    external_url = Column(String(500), nullable=True)  # set when synced to an external provider
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    retain_until = Column(DateTime, nullable=True)     # uploaded_at + 3 years (compliance)


def create_tables():
    Base.metadata.create_all(bind=engine)
    migrate()


def migrate():
    """Idempotent lightweight migration — add columns introduced after the initial deploy.
    SQLAlchemy create_all() only creates missing TABLES, not new COLUMNS on existing tables."""
    from sqlalchemy import text
    statements = [
        "ALTER TABLE leads ADD COLUMN temperature VARCHAR(20) DEFAULT 'cold'",
        "ALTER TABLE leads ADD COLUMN follow_up_cadence VARCHAR(30)",
        "ALTER TABLE leads ADD COLUMN state VARCHAR(20)",
        "ALTER TABLE leads ADD COLUMN is_deleted BOOLEAN DEFAULT 0",
        "ALTER TABLE leads ADD COLUMN deleted_at DATETIME",
        "ALTER TABLE leads ADD COLUMN assigned_to INTEGER",
    ]
    with engine.connect() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception as e:
                # "duplicate column" just means the migration already ran — ignore.
                # Anything else (locked db, syntax, disk) is a real problem — log it.
                msg = str(e).lower()
                if "duplicate column" not in msg and "already exists" not in msg:
                    print(f"⚠️  Migration failed: {stmt} → {e}")
