from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database import get_db, ScheduledHunt
from agents.lead_generator import (
    generate_leads, save_generated_leads, available_providers, ingest_inbound_lead,
)
from agents.scheduler import compute_next_run, run_one
from config import settings

router = APIRouter(prefix="/leadgen", tags=["lead-generator"])


class HuntRequest(BaseModel):
    hunt_type: str  # ideal_clients | local_businesses | referral_partners
    city: Optional[str] = ""
    state: Optional[str] = ""
    neighborhood: Optional[str] = ""
    niche: Optional[str] = ""
    provider: str = "tavily"
    auto_save: bool = False  # if true, found leads are scored + saved to the CRM immediately


class SaveRequest(BaseModel):
    hunt_type: str
    leads: list[dict]


@router.get("/providers")
def get_providers():
    return available_providers()


@router.post("/hunt")
async def run_hunt(req: HuntRequest, db: Session = Depends(get_db)):
    result = await generate_leads(
        req.hunt_type, city=req.city, state=req.state, neighborhood=req.neighborhood,
        niche=req.niche, provider=req.provider,
    )
    # "Auto" mode: score + drop the found leads straight into the CRM.
    if req.auto_save and result.get("leads"):
        saved = await save_generated_leads(db, result["leads"], req.hunt_type)
        result["auto_saved"] = saved
    return result


@router.post("/save")
async def save_leads(req: SaveRequest, db: Session = Depends(get_db)):
    if not req.leads:
        raise HTTPException(400, "No leads to save")
    result = await save_generated_leads(db, req.leads, req.hunt_type)
    return result


# ── Scheduled auto-hunts (hands-off lead generation) ──────────────────────────
class ScheduleCreate(BaseModel):
    hunt_type: str
    city: Optional[str] = ""
    state: Optional[str] = ""
    neighborhood: Optional[str] = ""
    niche: Optional[str] = ""
    provider: str = "tavily"
    frequency: str = "daily"   # hourly | daily | weekly
    enabled: bool = True


def _serialize_schedule(s: ScheduledHunt) -> dict:
    return {
        "id": s.id, "hunt_type": s.hunt_type, "city": s.city, "state": s.state,
        "neighborhood": s.neighborhood, "niche": s.niche, "provider": s.provider,
        "frequency": s.frequency, "enabled": s.enabled,
        "last_run": s.last_run.isoformat() if s.last_run else None,
        "next_run": s.next_run.isoformat() if s.next_run else None,
        "last_found": s.last_found, "last_saved": s.last_saved,
        "total_saved": s.total_saved, "last_status": s.last_status,
    }


@router.get("/schedules")
def list_schedules(db: Session = Depends(get_db)):
    rows = db.query(ScheduledHunt).order_by(ScheduledHunt.created_at.desc()).all()
    return [_serialize_schedule(s) for s in rows]


@router.post("/schedules")
def create_schedule(req: ScheduleCreate, db: Session = Depends(get_db)):
    s = ScheduledHunt(**req.dict())
    s.next_run = compute_next_run(req.frequency) if req.enabled else None
    db.add(s)
    db.commit()
    db.refresh(s)
    return _serialize_schedule(s)


@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id: int, updates: dict, db: Session = Depends(get_db)):
    s = db.query(ScheduledHunt).filter(ScheduledHunt.id == schedule_id).first()
    if not s:
        raise HTTPException(404, "Schedule not found")
    for k, v in updates.items():
        if hasattr(s, k) and k not in ("id", "created_at"):
            setattr(s, k, v)
    # If it was just enabled (or its cadence changed) and has no next run, schedule one.
    if s.enabled and not s.next_run:
        s.next_run = compute_next_run(s.frequency)
    if not s.enabled:
        s.next_run = None
    db.commit()
    return _serialize_schedule(s)


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    s = db.query(ScheduledHunt).filter(ScheduledHunt.id == schedule_id).first()
    if not s:
        raise HTTPException(404, "Schedule not found")
    db.delete(s)
    db.commit()
    return {"id": schedule_id, "status": "deleted"}


@router.post("/schedules/{schedule_id}/run")
async def run_schedule_now(schedule_id: int, db: Session = Depends(get_db)):
    s = db.query(ScheduledHunt).filter(ScheduledHunt.id == schedule_id).first()
    if not s:
        raise HTTPException(404, "Schedule not found")
    result = await run_one(s, db)
    return {"ran": result, "schedule": _serialize_schedule(s)}


def _check_webhook_token(token: Optional[str]):
    """Shared-secret check so randoms can't post leads to you."""
    expected = getattr(settings, "leadgen_webhook_token", None)
    if expected and token != expected:
        raise HTTPException(401, "Invalid or missing webhook token")


async def _ingest_webhook_body(request: Request, db: Session) -> dict:
    """Parse the JSON body (single object or list) and ingest every lead."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Body must be JSON")

    items = payload if isinstance(payload, list) else [payload]
    results = []
    for item in items:
        if isinstance(item, dict):
            results.append(await ingest_inbound_lead(db, item, default_source="web_zapier"))

    created = sum(1 for r in results if r.get("status") == "created")
    dupes = sum(1 for r in results if r.get("status") == "duplicate")
    rejected = sum(1 for r in results if r.get("status") == "rejected")
    return {"received": len(items), "created": created,
            "duplicates": dupes, "rejected": rejected, "results": results}


@router.post("/inbound")
async def inbound_webhook(request: Request, token: Optional[str] = None,
                          db: Session = Depends(get_db)):
    """
    Generic inbound lead webhook for Zapier / website forms / any external source.
    Accepts a single lead object OR a list of lead objects in the JSON body.
    Optional ?token= must match LEADGEN_WEBHOOK_TOKEN in .env (if that key is set).
    """
    _check_webhook_token(token)
    return await _ingest_webhook_body(request, db)


@router.get("/inbound/info")
def inbound_info():
    """Show the webhook URL + setup hints for connecting a website form / Zapier / any source."""
    base = settings.public_base_url or "http://localhost:8000"
    has_token = bool(getattr(settings, "leadgen_webhook_token", None))
    query_url = f"{base}/leadgen/inbound" + ("?token=YOUR_TOKEN" if has_token else "")
    # Path-style URL has no "?" — use this one for tools that reject query strings.
    path_url = f"{base}/leadgen/inbound" + ("/YOUR_TOKEN" if has_token else "")
    return {
        "webhook_url": query_url,
        "webhook_url_no_querystring": path_url,
        "method": "POST",
        "needs_public_url": not bool(settings.public_base_url),
        "token_required": has_token,
        "example_payload": {
            "first_name": "Jane", "last_name": "Doe", "phone": "+14085551234",
            "email": "jane@example.com", "company": "Acme Plumbing", "city": "San Jose",
            "life_event": "wants more booked jobs", "source": "website_form",
        },
        "setup_steps": [
            "1. In Zapier (or your website form tool) add a Webhook action.",
            f"2. URL (no '?'): {path_url}",
            "3. Method POST, JSON body with the lead's name, phone/email, and company.",
            "4. Test it — the lead appears in NOVA, auto-scored.",
        ],
    }


@router.api_route("/inbound/{token}", methods=["GET", "HEAD", "POST"])
async def inbound_webhook_path(token: str, request: Request,
                               db: Session = Depends(get_db)):
    """
    Same inbound webhook, but with the token in the URL PATH instead of a
    query string — e.g. /leadgen/inbound/<token>. Some tools reject
    webhook URLs that contain a "?". GET/HEAD return a 200 "ready" so those
    services' URL-validation pings succeed; POST ingests the lead(s).
    """
    _check_webhook_token(token)
    if request.method in ("GET", "HEAD"):
        return {"status": "ready", "message": "NOVA inbound webhook is live. POST leads here."}
    return await _ingest_webhook_body(request, db)
