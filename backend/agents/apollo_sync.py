"""
Apollo → NOVA sync.

Pulls every contact saved in the team's Apollo account into NOVA's CRM so Apollo
is never the system of record — NOVA is. Safe to run repeatedly: existing leads
are matched by email address and updated in place, never duplicated.

Requires APOLLO_API_KEY in .env (Apollo → Settings → Integrations → API).
"""
import httpx
from datetime import datetime

from config import settings
from database import SessionLocal, Lead

APOLLO_CONTACTS_URL = "https://api.apollo.io/api/v1/contacts/search"


def sync_apollo_contacts() -> dict:
    """Pull all Apollo contacts and upsert them into the Lead table."""
    if not settings.apollo_api_key:
        return {"status": "skipped", "reason": "No APOLLO_API_KEY configured"}

    headers = {
        "X-Api-Key": settings.apollo_api_key,
        "Content-Type": "application/json",
    }

    created, updated, skipped_no_email = 0, 0, 0
    page, total_pages = 1, 1
    db = SessionLocal()
    try:
        while page <= total_pages:
            resp = httpx.post(
                APOLLO_CONTACTS_URL,
                headers=headers,
                json={"page": page, "per_page": 100},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            total_pages = data.get("pagination", {}).get("total_pages", 1)

            for c in data.get("contacts", []):
                email = (c.get("email") or "").strip().lower()
                if not email:
                    skipped_no_email += 1
                    continue

                lead = db.query(Lead).filter(Lead.email.ilike(email)).first()
                company = (c.get("organization_name") or "").strip()
                phone = c.get("sanitized_phone") or ""
                if not phone and c.get("account"):
                    phone = c["account"].get("sanitized_phone") or ""

                if lead is None:
                    lead = Lead(
                        first_name=c.get("first_name") or "",
                        last_name=c.get("last_name") or "",
                        email=email,
                        phone=phone,
                        city=c.get("city") or "",
                        state=c.get("state") or "",
                        source="Apollo",
                        notes=f"Company: {company}\nTitle: {c.get('title') or ''}".strip(),
                    )
                    db.add(lead)
                    created += 1
                else:
                    # Fill blanks only — never overwrite data Ruth typed in NOVA.
                    if not lead.phone and phone:
                        lead.phone = phone
                    if not lead.city and c.get("city"):
                        lead.city = c["city"]
                    if not lead.state and c.get("state"):
                        lead.state = c["state"]
                    if company and "Company:" not in (lead.notes or ""):
                        lead.notes = ((lead.notes or "") + f"\nCompany: {company}").strip()
                    lead.updated_at = datetime.utcnow()
                    updated += 1

            db.commit()
            page += 1

        return {
            "status": "ok",
            "created": created,
            "updated": updated,
            "skipped_no_email": skipped_no_email,
        }
    except httpx.HTTPStatusError as e:
        db.rollback()
        return {"status": "failed", "error": f"Apollo API {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        db.rollback()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()
