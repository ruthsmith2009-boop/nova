from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from database import get_db, Lead, Touchpoint, LeadStage, CalendarEvent
from agents.lead_scorer import (
    score_lead, generate_daily_call_list, process_csv_upload,
    suggest_temperature, compute_next_followup, CADENCE_LABELS,
    default_cadence_for_temperature,
)
from agents.scripts import handle_objection, get_call_script

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    property_type: Optional[str] = "Business Prospect"
    source: Optional[str] = None
    years_owned: Optional[int] = None
    is_absentee: Optional[bool] = False
    has_expired_listing: Optional[bool] = False
    days_on_market: Optional[int] = None
    price_reductions: Optional[int] = 0
    life_event: Optional[str] = None
    equity_estimate: Optional[float] = None


class TouchpointCreate(BaseModel):
    type: str  # call, email, text, meeting, note
    direction: str = "outbound"
    summary: str
    outcome: Optional[str] = None
    duration_seconds: Optional[int] = None
    schedule_next: bool = True          # auto-set the next follow-up after a real contact
    next_cadence: Optional[str] = None  # override the cadence for the next follow-up


class ObjectionRequest(BaseModel):
    objection: str
    lead_id: Optional[int] = None


@router.get("/")
def list_leads(stage: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Lead).filter(Lead.is_deleted.isnot(True))
    if stage:
        query = query.filter(Lead.stage == stage)
    leads = query.order_by(Lead.score.desc()).all()
    return [_serialize_lead(l) for l in leads]


@router.post("/")
async def create_lead(lead_data: LeadCreate, db: Session = Depends(get_db)):
    lead = Lead(**lead_data.dict())
    db.add(lead)
    db.flush()

    # Auto-score the lead
    score_result = await score_lead(lead_data.dict())
    lead.score = score_result.get("final_score", 0)
    lead.score_reasons = score_result.get("final_reasons", [])
    lead.temperature = suggest_temperature(lead.score)

    db.commit()
    db.refresh(lead)
    return {**_serialize_lead(lead), "score_details": score_result}


@router.put("/{lead_id}/cadence")
def set_cadence(lead_id: int, cadence: str, db: Session = Depends(get_db)):
    """Assign a follow-up cadence and auto-set the next follow-up date."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.follow_up_cadence = cadence
    lead.next_follow_up = compute_next_followup(cadence)
    db.commit()
    return {"lead_id": lead_id, "cadence": cadence,
            "cadence_label": CADENCE_LABELS.get(cadence, cadence),
            "next_follow_up": lead.next_follow_up.isoformat() if lead.next_follow_up else None}


@router.put("/{lead_id}/temperature")
def set_temperature(lead_id: int, temperature: str, db: Session = Depends(get_db)):
    """Manually set a lead's temperature (hot/warm/cold/not_ready)."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.temperature = temperature
    # not_ready leads auto-get a 7-day check-in cadence
    if temperature == "not_ready" and not lead.follow_up_cadence:
        lead.follow_up_cadence = "not_ready_7day"
        lead.next_follow_up = compute_next_followup("not_ready_7day")
    db.commit()
    return {"lead_id": lead_id, "temperature": temperature}


@router.get("/cadences")
def list_cadences():
    return CADENCE_LABELS


@router.get("/followups")
def followups_overview(days: int = 14, db: Session = Depends(get_db)):
    """Follow-up automation queue: overdue + upcoming touches, soonest first."""
    now = datetime.utcnow()
    horizon = now + timedelta(days=days)
    base = (db.query(Lead).filter(Lead.is_deleted.isnot(True))
            .filter(Lead.next_follow_up.isnot(None)))
    overdue = base.filter(Lead.next_follow_up < now).order_by(Lead.next_follow_up.asc()).all()
    upcoming = (base.filter(Lead.next_follow_up >= now, Lead.next_follow_up <= horizon)
                .order_by(Lead.next_follow_up.asc()).all())
    return {
        "as_of": now.isoformat(),
        "counts": {"overdue": len(overdue), "upcoming": len(upcoming)},
        "overdue": [_serialize_lead(l) for l in overdue],
        "upcoming": [_serialize_lead(l) for l in upcoming],
    }


# ── Demo data (for showcasing ARIA) — reversible via DELETE /leads/demo ─────────
DEMO_SOURCE = "demo"
_DEMO_LEADS = [
    # (first, last, business, city, zip, phone, email, score, temp, stage, need, next_days, last_days)
    ("Maria", "Delgado", "Bright Smile Dental", "San Jose", "95129", "408-555-0142", "maria@brightsmile.example", 88, "hot", "appointment_set", "Missing calls / losing new patients", 0, 1),
    ("Tony", "Ricci", "Ricci Plumbing & Rooter", "Campbell", "95008", "408-555-0177", "tony@ricciplumb.example", 82, "hot", "contacted", "Wants missed-call text-back + AI answering", -1, 2),
    ("Sandra", "Kim", "Glow Med Spa", "Los Gatos", "95030", "408-555-0198", "sandra@glowmedspa.example", 90, "hot", "appointment_set", "Wants automated booking + follow-up", 0, 1),
    ("Marcus", "Bell", "Bell Auto Repair", "Sunnyvale", "94086", "408-555-0110", "marcus@bellauto.example", 64, "warm", "new", "Follow-up falling through the cracks", 3, None),
    ("Priya", "Nair", "Nair Family Law", "San Jose", "95126", "408-555-0165", "priya@nairlaw.example", 68, "warm", "contacted", "Wants AI answering after hours", -2, 3),
    ("Derek", "Olsen", "Olsen HVAC & Air", "Santa Clara", "95050", "408-555-0133", "derek@olsenhvac.example", 55, "warm", "new", "Full automation package", 5, None),
    ("Grace", "Tan", "Tan Accounting Services", "Cupertino", "95014", "408-555-0121", "grace@tancpa.example", 38, "cold", "new", "Not sure yet", 20, None),
    ("Luis", "Romero", "Romero Landscaping", "Mountain View", "94040", "408-555-0154", "luis@romerolandscape.example", 44, "not_ready", "new", "Just exploring", 7, None),
]


@router.post("/seed-demo")
def seed_demo(db: Session = Depends(get_db)):
    """Add a set of realistic sample leads so the app looks alive in a demo."""
    existing = db.query(Lead).filter(Lead.source == DEMO_SOURCE).count()
    if existing:
        return {"added": 0, "note": f"{existing} demo leads already present"}
    now = datetime.utcnow()
    added = 0
    for (fn, ln, addr, city, zc, phone, email, score, temp, stage,
         life_event, next_days, last_days) in _DEMO_LEADS:
        lead = Lead(
            first_name=fn, last_name=ln, address=addr, city=city, state="CA",
            zip_code=zc, phone=phone, email=email, property_type="Single Family",
            source=DEMO_SOURCE, score=float(score), temperature=temp,
            stage=LeadStage(stage), life_event=life_event,
            follow_up_cadence=default_cadence_for_temperature(temp),
            next_follow_up=now + timedelta(days=next_days),
            last_contact=(now - timedelta(days=last_days)) if last_days else None,
            score_reasons=["Demo lead — sample data for showcasing NOVA"],
        )
        db.add(lead)
        db.flush()
        # Give the two most-engaged leads a little activity history (for KPIs/timeline).
        if stage in ("contacted", "appointment_set"):
            db.add(Touchpoint(lead_id=lead.id, type="call", direction="outbound",
                              summary="Intro call — discussed timing and goals.",
                              outcome="connected", created_at=now))
        added += 1
    db.commit()
    return {"added": added}


@router.delete("/demo")
def clear_demo(db: Session = Depends(get_db)):
    """Remove all demo leads (and their touchpoints)."""
    demo = db.query(Lead).filter(Lead.source == DEMO_SOURCE).all()
    n = len(demo)
    for lead in demo:
        db.delete(lead)
    db.commit()
    return {"deleted": n}


@router.get("/deleted")
def list_deleted_leads(db: Session = Depends(get_db)):
    """Recently deleted leads — recoverable until permanently removed."""
    leads = (db.query(Lead).filter(Lead.is_deleted.is_(True))
             .order_by(Lead.deleted_at.desc()).all())
    return [_serialize_lead(l) for l in leads]


@router.get("/today")
def today_dashboard(db: Session = Depends(get_db)):
    """Everything Ruth should act on today: follow-ups due, hot leads, and new leads."""
    now = datetime.utcnow()
    active = db.query(Lead).filter(Lead.is_deleted.isnot(True))

    followups_due = (active.filter(Lead.next_follow_up.isnot(None))
                     .filter(Lead.next_follow_up <= now)
                     .order_by(Lead.next_follow_up.asc()).all())
    hot = (db.query(Lead).filter(Lead.is_deleted.isnot(True))
           .filter(Lead.temperature == "hot")
           .order_by(Lead.score.desc()).all())
    new_leads = (db.query(Lead).filter(Lead.is_deleted.isnot(True))
                 .filter(Lead.stage == "new")
                 .order_by(Lead.score.desc()).limit(10).all())
    return {
        "date": now.strftime("%A, %B %d, %Y"),
        "counts": {
            "followups_due": len(followups_due),
            "hot_leads": len(hot),
            "new_leads": db.query(Lead).filter(Lead.is_deleted.isnot(True),
                                               Lead.stage == "new").count(),
        },
        "followups_due": [_serialize_lead(l) for l in followups_due],
        "hot_leads": [_serialize_lead(l) for l in hot],
        "new_leads": [_serialize_lead(l) for l in new_leads],
    }


@router.get("/kpis")
def activity_kpis(db: Session = Depends(get_db)):
    """Activity scoreboard: calls, contacts, leads, appointments for today / this week / this month.
    Days are measured in Pacific time (Ruth's market) against UTC-stored timestamps."""
    try:
        from zoneinfo import ZoneInfo
        pt = ZoneInfo("America/Los_Angeles")
        utc = ZoneInfo("UTC")
        now_pt = datetime.now(pt)
    except Exception:
        # Fallback: plain UTC if zoneinfo/tzdata unavailable
        now_pt = datetime.utcnow()
        pt = utc = None

    def to_utc_naive(dt_local):
        if pt is None:
            return dt_local
        return dt_local.astimezone(utc).replace(tzinfo=None)

    midnight = now_pt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = to_utc_naive(midnight)
    week_start = to_utc_naive(midnight - timedelta(days=midnight.weekday()))  # Monday
    month_start = to_utc_naive(midnight.replace(day=1))

    def metrics(start):
        calls = (db.query(Touchpoint).filter(Touchpoint.type == "call",
                 Touchpoint.created_at >= start).count())
        contacts = (db.query(Touchpoint).filter(Touchpoint.created_at >= start)
                    .filter((Touchpoint.outcome == "connected") | (Touchpoint.type == "meeting"))
                    .count())
        leads = (db.query(Lead).filter(Lead.is_deleted.isnot(True),
                 Lead.created_at >= start).count())
        appts = (db.query(Touchpoint).filter(Touchpoint.outcome == "appointment_set",
                 Touchpoint.created_at >= start).count())
        appts += db.query(CalendarEvent).filter(CalendarEvent.created_at >= start).count()
        return {"calls": calls, "contacts": contacts, "leads": leads, "appointments": appts}

    return {
        "as_of": now_pt.strftime("%A, %B %d, %Y"),
        "today": metrics(day_start),
        "week": metrics(week_start),
        "month": metrics(month_start),
    }


@router.get("/daily-call-list")
async def get_daily_call_list(db: Session = Depends(get_db)):
    leads = (db.query(Lead).filter(Lead.is_deleted.isnot(True))
             .filter(Lead.stage.in_(["new", "contacted"])).all())
    lead_dicts = [_serialize_lead(l) for l in leads]
    call_list = await generate_daily_call_list(lead_dicts)
    return {"date": datetime.now().strftime("%B %d, %Y"), "calls": call_list}


@router.get("/{lead_id}")
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _serialize_lead(lead)


# Server-managed columns a client must never set via the generic update endpoint.
PROTECTED_LEAD_FIELDS = {
    "id", "created_at", "updated_at", "is_deleted", "deleted_at",
}


@router.put("/{lead_id}")
def update_lead(lead_id: int, updates: dict, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    for key, value in updates.items():
        if key in PROTECTED_LEAD_FIELDS or key.startswith("_"):
            continue
        if hasattr(lead, key):
            setattr(lead, key, value)
    lead.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lead)
    return _serialize_lead(lead)


class BulkAction(BaseModel):
    ids: list[int]
    action: str                      # delete | assign | temperature | stage
    value: Optional[str] = None      # member id (assign), temp, or stage


@router.post("/bulk")
def bulk_action(req: BulkAction, db: Session = Depends(get_db)):
    """Apply one action to many leads at once (delete / assign / temperature / stage)."""
    leads = db.query(Lead).filter(Lead.id.in_(req.ids)).all()
    n = 0
    for lead in leads:
        if req.action == "delete":
            lead.is_deleted = True
            lead.deleted_at = datetime.utcnow()
        elif req.action == "assign":
            lead.assigned_to = int(req.value) if req.value not in (None, "", "none") else None
        elif req.action == "temperature":
            lead.temperature = req.value
        elif req.action == "stage":
            lead.stage = req.value
        else:
            raise HTTPException(400, f"Unknown action: {req.action}")
        n += 1
    db.commit()
    return {"updated": n, "action": req.action}


@router.delete("/{lead_id}")
def delete_lead(lead_id: int, permanent: bool = False, db: Session = Depends(get_db)):
    """Soft-delete a lead (hidden but recoverable). Pass ?permanent=true to remove for good."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if permanent:
        db.delete(lead)
        db.commit()
        return {"lead_id": lead_id, "status": "permanently_deleted"}
    lead.is_deleted = True
    lead.deleted_at = datetime.utcnow()
    db.commit()
    return {"lead_id": lead_id, "status": "deleted", "recoverable": True}


@router.put("/{lead_id}/assign")
def assign_lead(lead_id: int, member_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Assign a lead to a team member (or pass no member_id to unassign)."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.assigned_to = member_id
    db.commit()
    return {"lead_id": lead_id, "assigned_to": member_id}


@router.post("/{lead_id}/recover")
def recover_lead(lead_id: int, db: Session = Depends(get_db)):
    """Restore a soft-deleted lead back into the CRM."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.is_deleted = False
    lead.deleted_at = None
    db.commit()
    return {"lead_id": lead_id, "status": "recovered"}


CONTACT_TOUCH_TYPES = ("call", "email", "text", "meeting")


@router.post("/{lead_id}/touchpoints")
def add_touchpoint(lead_id: int, tp: TouchpointCreate, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    data = tp.dict()
    schedule_next = data.pop("schedule_next", True)
    next_cadence = data.pop("next_cadence", None)
    touchpoint = Touchpoint(lead_id=lead_id, **data)
    db.add(touchpoint)
    now = datetime.utcnow()
    lead.last_contact = now
    # Follow-up automation: after a real contact, auto-schedule the next touch so
    # no lead ever falls through the cracks. Uses the lead's cadence, else a
    # sensible default for its temperature. "note" touches don't reschedule.
    if schedule_next and tp.type in CONTACT_TOUCH_TYPES:
        cadence = next_cadence or lead.follow_up_cadence or default_cadence_for_temperature(lead.temperature)
        lead.follow_up_cadence = cadence
        nxt = compute_next_followup(cadence, now)
        if nxt:
            lead.next_follow_up = nxt
    db.commit()
    return {"id": touchpoint.id, "status": "logged",
            "next_follow_up": lead.next_follow_up.isoformat() if lead.next_follow_up else None,
            "follow_up_cadence": lead.follow_up_cadence,
            "cadence_label": CADENCE_LABELS.get(lead.follow_up_cadence, lead.follow_up_cadence)}


@router.get("/{lead_id}/touchpoints")
def list_touchpoints(lead_id: int, db: Session = Depends(get_db)):
    """Activity timeline for a lead — every call/email/text/note, newest first."""
    tps = (db.query(Touchpoint).filter(Touchpoint.lead_id == lead_id)
           .order_by(Touchpoint.created_at.desc()).all())
    return [{
        "id": t.id, "type": t.type, "direction": t.direction, "summary": t.summary,
        "outcome": t.outcome, "duration_seconds": t.duration_seconds,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in tps]


@router.post("/{lead_id}/draft-followup")
async def draft_followup(lead_id: int, channel: str = "auto", db: Session = Depends(get_db)):
    """AI-drafts the next follow-up message for a lead, aware of its stage + history."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if channel == "auto":
        channel = "text" if lead.phone else ("email" if lead.email else "call")

    tps = (db.query(Touchpoint).filter(Touchpoint.lead_id == lead_id)
           .order_by(Touchpoint.created_at.desc()).limit(5).all())
    history = "; ".join(f"{t.type} ({t.outcome or 'n/a'}): {t.summary or ''}" for t in tps) or "no prior contact logged yet"
    days_since = (datetime.utcnow() - lead.last_contact).days if lead.last_contact else None

    channel_rules = {
        "text": "A friendly SMS text under 320 characters. Casual but professional. No subject line.",
        "email": "A short email. Start with 'Subject:' on its own line, then the body. Warm, concise, skimmable.",
        "call": "A 3-4 sentence phone opener plus one strong question to re-engage them. Not a full script.",
    }
    prompt = (
        f"Draft the next {channel} follow-up from a small-business owner to this lead. "
        f"Goal: build the relationship and move toward a booked call — helpful, never pushy.\n\n"
        f"Lead: {lead.first_name} {lead.last_name}\n"
        f"Company / location: {lead.address or ''} {lead.city or ''}, {lead.state or ''}\n"
        f"Pipeline stage: {lead.stage.value if lead.stage else 'new'} | Temperature: {lead.temperature}\n"
        f"What they need / situation: {lead.life_event or 'unknown'}\n"
        f"Days since last contact: {days_since if days_since is not None else 'never contacted'}\n"
        f"Recent contact history: {history}\n\n"
        f"Format: {channel_rules.get(channel, channel_rules['text'])}\n"
        f"Output ONLY the message text — no preamble, no explanation."
    )
    from agents.brain import think
    message = await think(prompt, system_extra=(
        "You are NOVA, a top-producing salesperson's assistant. You write concise, personable "
        "outreach that sounds like a real human, not a template. Adapt to the owner's industry and "
        "never assume real estate. Never invent facts about the lead beyond what you are told."
    ))
    return {"lead_id": lead_id, "channel": channel, "message": message.strip(),
            "days_since_contact": days_since}


@router.get("/{lead_id}/script")
async def get_script(lead_id: int, script_type: str = "auto", db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    script = await get_call_script(_serialize_lead(lead), script_type)
    return {"lead_id": lead_id, "script_type": script_type, "script": script}


@router.post("/objection")
async def handle_objection_endpoint(req: ObjectionRequest, db: Session = Depends(get_db)):
    lead_context = None
    if req.lead_id:
        lead = db.query(Lead).filter(Lead.id == req.lead_id).first()
        if lead:
            lead_context = _serialize_lead(lead)
    result = await handle_objection(req.objection, lead_context)
    return result


@router.post("/upload")
async def upload_leads(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        leads_data = await process_csv_upload(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    created = []
    for lead_data in leads_data:
        lead = Lead(**{k: v for k, v in lead_data.items() if hasattr(Lead, k)})
        db.add(lead)
        db.flush()
        score_result = await score_lead(lead_data)
        lead.score = score_result.get("final_score", 0)
        lead.score_reasons = score_result.get("final_reasons", [])
        db.commit()
        created.append(lead.id)

    return {"imported": len(created), "lead_ids": created}


def _serialize_lead(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "email": lead.email,
        "phone": lead.phone,
        "address": lead.address,
        "city": lead.city,
        "state": lead.state,
        "zip_code": lead.zip_code,
        "property_type": lead.property_type,
        "bedrooms": lead.bedrooms,
        "bathrooms": lead.bathrooms,
        "sqft": lead.sqft,
        "lot_size": lead.lot_size,
        "year_built": lead.year_built,
        "last_sold_price": lead.last_sold_price,
        "last_sold_date": lead.last_sold_date,
        "estimated_value": lead.estimated_value,
        "property_enriched": lead.property_enriched,
        "enrichment_confidence": lead.enrichment_confidence,
        "score": lead.score,
        "score_reasons": lead.score_reasons,
        "equity_estimate": lead.equity_estimate,
        "years_owned": lead.years_owned,
        "is_absentee": lead.is_absentee,
        "has_expired_listing": lead.has_expired_listing,
        "days_on_market": lead.days_on_market,
        "price_reductions": lead.price_reductions,
        "life_event": lead.life_event,
        "stage": lead.stage.value if lead.stage else "new",
        "temperature": lead.temperature or "cold",
        "follow_up_cadence": lead.follow_up_cadence,
        "source": lead.source,
        "notes": lead.notes,
        "last_contact": lead.last_contact.isoformat() if lead.last_contact else None,
        "next_follow_up": lead.next_follow_up.isoformat() if lead.next_follow_up else None,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "deleted_at": lead.deleted_at.isoformat() if lead.deleted_at else None,
        "assigned_to": lead.assigned_to,
    }
