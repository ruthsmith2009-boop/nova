"""
Lead Generator — finds real, publicly-listed business prospects via Tavily and feeds them into
NOVA's CRM. Industry-agnostic: it works for any sales/service business generating leads.

Hunt types:
  1. ideal_clients      — businesses that match your ideal-customer profile (by niche + area)
  2. local_businesses   — local businesses in an area you could sell to
  3. referral_partners  — complementary businesses that could send you referrals

Architecture: a pluggable provider interface. `tavily` is free and built in. Paid providers
(Apollo, and other B2B data tools) are stubbed and become available once their API key is added.

GUARANTEE: the free scanner only returns leads it actually found in search results. It never
invents names, businesses, or phone numbers. Missing contact info is flagged "needs_research".
"""
import json
from datetime import datetime
from typing import Optional

from agents.research import search_market
from agents.brain import think_structured, BUSINESS_KNOWLEDGE
from agents.lead_scorer import score_lead, calculate_base_score
from config import settings


async def _apply_score(lead, lead_data: dict):
    """Score a lead, always falling back to the deterministic base score (never 0 on AI failure)."""
    base_score, base_reasons = calculate_base_score(lead_data)
    try:
        result = await score_lead(lead_data)
        lead.score = result.get("final_score") or base_score
        lead.score_reasons = result.get("final_reasons") or base_reasons
    except Exception:
        lead.score = base_score
        lead.score_reasons = base_reasons


# ── Paid provider registry (stubs until configured) ───────────────────────────
def _paid_provider_status() -> dict:
    """Report which paid lead providers are configured via .env keys."""
    return {
        "apollo": bool(getattr(settings, "apollo_api_key", None)),
    }


def available_providers() -> dict:
    paid = _paid_provider_status()
    return {
        "tavily": {"configured": bool(settings.tavily_api_key), "type": "free",
                   "gives": "real public business prospects (name, website, sometimes phone/email)"},
        "apollo": {"configured": paid["apollo"], "type": "paid",
                   "gives": "verified business contacts with emails + direct phone numbers"},
    }


# ── Free Tavily hunts ─────────────────────────────────────────────────────────
async def _extract_leads(context: str, hunt_type: str, area: str) -> list[dict]:
    """Use Claude to pull ONLY real leads out of search results — no fabrication."""
    schema_hint = """[{
  "business_name": "", "contact_name": "", "phone": "", "email": "",
  "website": "", "city": "%s", "industry": "", "source": "linkedin|directory|web|google",
  "why_good_fit": "why this business is a good prospect for you",
  "contact_status": "found|needs_research"
}]""" % area

    result = await think_structured(
        f"""Extract REAL business leads from these search results for a "{hunt_type.replace('_',' ')}"
hunt in {area}.

Search results:
{context[:5000]}

CRITICAL RULES:
- Only include businesses that genuinely appear in the search results above.
- NEVER invent business names, contact names, phone numbers, or emails. If a field isn't in the
  results, leave it as "" (empty) and set contact_status to "needs_research".
- It is better to return 2 real leads than 10 fabricated ones. Return [] if nothing real is found.

Return a JSON array shaped like:
{schema_hint}""",
        use_haiku=True,
    )
    try:
        leads = json.loads(result)
        return leads if isinstance(leads, list) else []
    except Exception:
        return []


async def hunt_ideal_clients(niche: str, area: str = "") -> list[dict]:
    niche = niche or "small business"
    where = area or "United States"
    queries = [
        f"{niche} {where} business owner contact directory",
        f"{niche} companies {where} email phone website",
        f"{niche} {where} LinkedIn business owner",
    ]
    ctx = []
    for q in queries:
        for r in await search_market(q, max_results=4):
            if "error" not in r:
                ctx.append(f"{r.get('url','')}\n{r.get('content','')[:500]}")
    return await _extract_leads("\n\n".join(ctx), "ideal_clients", where)


async def hunt_local_businesses(city: str, state: str = "", niche: str = "") -> list[dict]:
    area = f"{city}, {state}" if state else (city or "your area")
    focus = niche or "local small business"
    queries = [
        f"{focus} in {area} owner contact phone email",
        f"best {focus} {area} directory listing",
        f"{focus} {area} Google business profile contact",
    ]
    ctx = []
    for q in queries:
        for r in await search_market(q, max_results=4):
            if "error" not in r:
                ctx.append(f"{r.get('url','')}\n{r.get('content','')[:500]}")
    return await _extract_leads("\n\n".join(ctx), "local_businesses", area)


async def hunt_referral_partners(niche: str, area: str = "") -> list[dict]:
    """Find complementary businesses that serve the same customers and could refer work."""
    niche = niche or "complementary service business"
    where = area or "your area"
    queries = [
        f"{niche} {where} business owner partnership referral contact",
        f"{niche} companies {where} directory contact info",
        f"{niche} {where} LinkedIn owner",
    ]
    ctx = []
    for q in queries:
        for r in await search_market(q, max_results=4):
            if "error" not in r:
                ctx.append(f"{r.get('url','')}\n{r.get('content','')[:500]}")
    return await _extract_leads("\n\n".join(ctx), "referral_partners", where)


# ── Orchestrator ──────────────────────────────────────────────────────────────
async def generate_leads(hunt_type: str, city: str = "", neighborhood: str = "",
                         niche: str = "", provider: str = "tavily", state: str = "") -> dict:
    """Run a lead hunt. Returns raw leads (not yet saved). provider selects the data source."""
    if provider != "tavily":
        status = _paid_provider_status()
        if not status.get(provider):
            return {"leads": [], "provider": provider, "configured": False,
                    "message": f"{provider} is not connected. Add its API key in .env to enable "
                               f"verified leads with phone numbers and emails."}

    area = f"{city}, {state}" if (city and state) else (city or neighborhood or "")
    if hunt_type == "ideal_clients":
        leads = await hunt_ideal_clients(niche, area)
    elif hunt_type == "local_businesses":
        leads = await hunt_local_businesses(city, state, niche)
    elif hunt_type == "referral_partners":
        leads = await hunt_referral_partners(niche, area)
    else:
        # Default to an ideal-client hunt for any unknown/legacy type.
        leads = await hunt_ideal_clients(niche, area)

    found = sum(1 for l in leads if l.get("contact_status") == "found")
    needs_research = len(leads) - found
    return {
        "hunt_type": hunt_type, "provider": "tavily", "configured": True,
        "total": len(leads), "with_contact": found, "needs_research": needs_research,
        "leads": leads,
        "note": ("Some leads have no public phone/email — flagged 'needs research'. "
                 "Connect a paid provider (Apollo) to auto-fill verified contact info.")
                if needs_research else "",
    }


INBOUND_FIELD_MAP = {
    "first_name": ["first_name", "firstname", "first", "fname", "contact_first_name"],
    "last_name": ["last_name", "lastname", "last", "lname", "contact_last_name"],
    "email": ["email", "email_address", "e_mail", "work_email"],
    "phone": ["phone", "phone_number", "cell", "mobile", "telephone", "phone1", "work_phone"],
    "address": ["address", "company", "business_name", "organization", "street", "street_address"],
    "city": ["city", "town", "location"],
    "zip_code": ["zip", "zip_code", "zipcode", "postal_code"],
    # What the prospect needs / their situation (kept as life_event for CRM compatibility).
    "life_event": ["life_event", "situation", "need", "interest", "notes", "message",
                   "lead_type", "list_type", "tag", "industry", "title", "job_title"],
}


async def ingest_inbound_lead(db, payload: dict, default_source: str = "zapier") -> dict:
    """Accept a flexible lead payload (from a website form/Zapier/any source), score + save it."""
    from database import Lead

    # Normalize incoming keys, then map to our fields
    flat = {str(k).lower().strip().replace(" ", "_"): v for k, v in payload.items()}
    lead_data = {}
    for field, aliases in INBOUND_FIELD_MAP.items():
        for alias in aliases:
            if alias in flat and flat[alias] not in (None, ""):
                lead_data[field] = flat[alias]
                break

    lead_data["source"] = flat.get("source") or default_source
    if not (lead_data.get("phone") or lead_data.get("address") or lead_data.get("email")):
        return {"status": "rejected", "reason": "No phone, email, or company/address in payload"}

    # Duplicate check
    q = db.query(Lead)
    existing = None
    if lead_data.get("phone"):
        existing = q.filter(Lead.phone == lead_data["phone"]).first()
    elif lead_data.get("email"):
        existing = q.filter(Lead.email == lead_data["email"]).first()
    elif lead_data.get("address"):
        existing = q.filter(Lead.address == lead_data["address"]).first()
    if existing:
        return {"status": "duplicate", "lead_id": existing.id}

    lead = Lead(**{k: v for k, v in lead_data.items() if hasattr(Lead, k)})
    db.add(lead)
    db.flush()
    await _apply_score(lead, lead_data)
    db.commit()
    return {"status": "created", "lead_id": lead.id, "score": lead.score}


async def save_generated_leads(db, leads: list[dict], hunt_type: str) -> dict:
    """Score and save generated leads into the CRM (Lead table), skipping duplicates."""
    from database import Lead

    saved, skipped = [], 0
    for raw in leads:
        # All hunts now return a business-shaped lead.
        contact = raw.get("contact_name") or ""
        parts = contact.split(" ", 1) if contact else []
        first = (parts[0] if parts else "") or "Contact"
        last = (parts[1] if len(parts) > 1 else "") or raw.get("business_name", "")
        why = raw.get("why_good_fit", "")
        notes = (f"Prospect: {raw.get('business_name','')}. {why} "
                 f"Website: {raw.get('website','')}").strip()
        lead_data = {
            "first_name": first, "last_name": last,
            "phone": raw.get("phone", ""), "email": raw.get("email", ""),
            "address": raw.get("business_name", ""), "city": raw.get("city", ""),
            "source": f"leadgen_{raw.get('source','web')}",
            "life_event": raw.get("industry", "") or raw.get("business_name", ""),
            "notes": notes, "property_type": "Business Prospect",
        }

        # Duplicate check by phone, then email, then company/address
        q = db.query(Lead)
        if lead_data.get("phone"):
            existing = q.filter(Lead.phone == lead_data["phone"]).first()
        elif lead_data.get("email"):
            existing = q.filter(Lead.email == lead_data["email"]).first()
        elif lead_data.get("address"):
            existing = q.filter(Lead.address == lead_data["address"]).first()
        else:
            existing = None
        if existing:
            skipped += 1
            continue

        lead = Lead(**{k: v for k, v in lead_data.items() if hasattr(Lead, k)})
        db.add(lead)
        db.flush()
        await _apply_score(lead, lead_data)
        db.commit()
        saved.append(lead.id)

    return {"saved": len(saved), "skipped_duplicates": skipped, "lead_ids": saved}
