"""
Auto-hunt scheduler — runs saved lead hunts on a cadence so leads flow in hands-off.

Runs as an in-process background task inside the FastAPI app (the web service is always
on, so no separate cron service is needed). Each ScheduledHunt row stores what to hunt,
where, and how often; the loop wakes periodically, runs anything due, scores + saves the
results, and stamps the next run time.
"""
import asyncio
import traceback
from datetime import datetime, timedelta

from database import SessionLocal, ScheduledHunt
from agents.lead_generator import generate_leads, save_generated_leads

# How often the loop wakes to check for due hunts.
CHECK_INTERVAL_SECONDS = 600  # 10 minutes

FREQUENCY_DELTA = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
}


def compute_next_run(frequency: str, from_time: datetime = None) -> datetime:
    base = from_time or datetime.utcnow()
    return base + FREQUENCY_DELTA.get(frequency, FREQUENCY_DELTA["daily"])


async def run_one(hunt: ScheduledHunt, db) -> dict:
    """Run a single scheduled hunt, auto-saving the results into the CRM."""
    result = await generate_leads(
        hunt.hunt_type, city=hunt.city or "", state=hunt.state or "",
        neighborhood=hunt.neighborhood or "", niche=hunt.niche or "",
        provider=hunt.provider or "tavily",
    )
    found = result.get("total", 0)
    saved = 0
    if result.get("leads"):
        save = await save_generated_leads(db, result["leads"], hunt.hunt_type)
        saved = save.get("saved", 0)

    now = datetime.utcnow()
    hunt.last_run = now
    hunt.next_run = compute_next_run(hunt.frequency, now)
    hunt.last_found = found
    hunt.last_saved = saved
    hunt.total_saved = (hunt.total_saved or 0) + saved
    hunt.last_status = f"{now.strftime('%Y-%m-%d %H:%M')} UTC — found {found}, added {saved}"
    db.commit()
    return {"hunt_id": hunt.id, "found": found, "saved": saved}


async def run_due_hunts() -> list[dict]:
    """Find every enabled hunt that's due and run it. Safe to call repeatedly."""
    db = SessionLocal()
    ran = []
    try:
        now = datetime.utcnow()
        due = (db.query(ScheduledHunt)
               .filter(ScheduledHunt.enabled.is_(True))
               .filter((ScheduledHunt.next_run.is_(None)) | (ScheduledHunt.next_run <= now))
               .all())
        for hunt in due:
            try:
                ran.append(await run_one(hunt, db))
            except Exception as e:
                hunt.last_status = f"error: {e}"
                hunt.next_run = compute_next_run(hunt.frequency)  # back off, don't hammer
                db.commit()
    finally:
        db.close()
    return ran


async def scheduler_loop():
    """Background loop: wake every CHECK_INTERVAL_SECONDS and run due hunts."""
    while True:
        try:
            await run_due_hunts()
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
