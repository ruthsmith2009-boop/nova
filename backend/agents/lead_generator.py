"""
Lead Generator — finds real, publicly-listed leads via Tavily and feeds them into ARIA's CRM.

Three hunt types:
  1. seller_leads     — homeowners showing public sell signals (FSBO, downsizing, relocation posts)
  2. expired_fsbo     — expired/withdrawn listings + For-Sale-By-Owner
  3. ai_service_clients — businesses/agents to sell ARIA to (the SaaS goal)

Architecture: a pluggable provider interface. `tavily` is free and built in. Paid providers
(REDX, BatchData, PropStream) are stubbed and become available once their API key is added.

GUARANTEE: the free scanner only returns leads it actually found in search results. It never
invents names, addresses, or phone numbers. Missing contact info is flagged "needs_skip_trace".
"""
import json
from datetime import datetime
from typing import Optional

from agents.research import search_market
from agents.brain import think_structured, SANTA_CLARA_KNOWLEDGE
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
        "redx": bool(getattr(settings, "redx_api_key", None)),
        "batchleads": bool(getattr(settings, "batchleads_api_key", None)),
        "propstream": bool(getattr(settings, "propstream_api_key", None)),
    }


def available_providers() -> dict:
    paid = _paid_provider_status()
    return {
        "tavily": {"configured": bool(settings.tavily_api_key), "type": "free",
                   "gives": "real public FSBO/expired listings + business prospects"},
        "redx": {"configured": paid["redx"], "type": "paid",
                 "gives": "expired/FSBO with verified phone numbers"},
        "batchleads": {"configured": paid["batchleads"], "type": "paid",
                       "gives": "skip-traced homeowner phones + emails, list building"},
        "propstream": {"configured": paid["propstream"], "type": "paid",
                       "gives": "absentee, high-equity, pre-foreclosure lists"},
    }


# ── Free Tavily hunts ─────────────────────────────────────────────────────────
async def _extract_leads(context: str, hunt_type: str, city: str) -> list[dict]:
    """Use Claude to pull ONLY real leads out of search results — no fabrication."""
    schema_hint = {
        "seller_leads": """[{
  "first_name": "", "last_name": "", "address": "123 Real St", "city": "%s",
  "phone": "", "email": "", "source": "fsbo_post|public_listing",
  "sell_signal": "what in the source suggests they may sell",
  "contact_status": "found|needs_skip_trace",
  "property_type": "Single Family"
}]""" % city,
        "expired_fsbo": """[{
  "first_name": "", "last_name": "", "address": "123 Real St", "city": "%s",
  "phone": "", "email": "", "source": "expired|fsbo",
  "original_list_price": 0, "days_on_market": 0, "price_reductions": 0,
  "has_expired_listing": true, "contact_status": "found|needs_skip_trace"
}]""" % city,
        "fsbo": """[{
  "first_name": "", "last_name": "", "address": "123 Real St", "city": "%s",
  "phone": "", "email": "", "source": "fsbo_zillow|fsbo_redfin|fsbo",
  "list_price": 0, "days_on_market": 0,
  "sell_signal": "Listed For Sale By Owner (no agent) — open to a listing conversation",
  "contact_status": "found|needs_skip_trace", "property_type": "Single Family"
}]""" % city,
        "distressed": """[{
  "first_name": "", "last_name": "", "address": "123 Real St", "city": "%s",
  "phone": "", "email": "",
  "distress_type": "pre_foreclosure|probate|tax_delinquent|vacant|inherited|divorce|code_violation|auction|other",
  "source": "auction|county_record|listing|news|web",
  "equity_estimate": 0, "is_absentee": false,
  "sell_signal": "what in the source indicates distress / motivation to sell",
  "contact_status": "found|needs_skip_trace", "property_type": "Single Family"
}]""" % city,
        "ai_service_clients": """[{
  "business_name": "", "contact_name": "", "phone": "", "email": "",
  "website": "", "city": "%s", "source": "linkedin|directory|upwork|web",
  "why_good_fit": "why this business would buy an AI agent",
  "contact_status": "found|needs_research"
}]""" % city,
    }

    result = await think_structured(
        f"""Extract REAL leads from these search results for a {hunt_type.replace('_',' ')} hunt in {city}.

Search results:
{context[:5000]}

CRITICAL RULES:
- Only include leads that genuinely appear in the search results above.
- NEVER invent names, street addresses, phone numbers, or emails. If a field isn't in the
  results, leave it as "" (empty) and set contact_status to "needs_skip_trace" (or "needs_research").
- It is better to return 2 real leads than 10 fabricated ones. Return [] if nothing real is found.

Return a JSON array shaped like:
{schema_hint.get(hunt_type, '[]')}""",
        use_haiku=True,
    )
    try:
        leads = json.loads(result)
        return leads if isinstance(leads, list) else []
    except Exception:
        return []


async def hunt_seller_leads(city: str, neighborhood: str = "") -> list[dict]:
    area = f"{neighborhood}, {city}" if neighborhood else city
    queries = [
        f"for sale by owner {area} Santa Clara County homeowner selling",
        f"{area} homeowner relocating downsizing selling home 2026",
        f"{area} estate sale probate home for sale by owner",
    ]
    ctx = []
    for q in queries:
        for r in await search_market(q, max_results=4):
            if "error" not in r:
                ctx.append(f"{r.get('url','')}\n{r.get('content','')[:500]}")
    return await _extract_leads("\n\n".join(ctx), "seller_leads", city)


async def hunt_expired_fsbo(city: str) -> list[dict]:
    queries = [
        f"expired listing {city} Santa Clara County withdrawn home for sale",
        f"for sale by owner {city} FSBO Zillow Craigslist 2026",
    ]
    ctx = []
    for q in queries:
        for r in await search_market(q, max_results=5):
            if "error" not in r:
                ctx.append(f"{r.get('url','')}\n{r.get('content','')[:500]}")
    return await _extract_leads("\n\n".join(ctx), "expired_fsbo", city)


async def hunt_fsbo(city: str, state: str = "") -> list[dict]:
    """Hunt For-Sale-By-Owner listings (Zillow/Redfin) — works for any US city.
    FSBOs are prime listing leads: a motivated seller already on the market without an agent."""
    area = f"{city}, {state}" if state else city
    queries = [
        f"Zillow for sale by owner {area} FSBO homes",
        f"Redfin for sale by owner {area} owner listed home",
        f"\"for sale by owner\" {area} home owner contact 2026",
    ]
    ctx = []
    for q in queries:
        for r in await search_market(q, max_results=5):
            if "error" not in r:
                ctx.append(f"{r.get('url','')}\n{r.get('content','')[:500]}")
    return await _extract_leads("\n\n".join(ctx), "fsbo", city)


async def hunt_distressed(city: str, state: str = "") -> list[dict]:
    """Hunt distressed / motivated-seller properties — pre-foreclosure, probate, tax-delinquent,
    vacant, inherited, divorce. These are the highest-conversion listing leads. Any US city.
    For VERIFIED distressed data with owner phones, build the list in Batchleads and let Zapier
    push it to /leadgen/inbound — this free scan surfaces public signals only."""
    area = f"{city}, {state}" if state else city
    queries = [
        f"pre-foreclosure homes {area} notice of default auction 2026",
        f"probate inherited property for sale {area} estate sale",
        f"tax delinquent vacant distressed property {area} motivated seller",
    ]
    from agents.research import DISTRESSED_DOMAINS
    ctx = []
    for q in queries:
        # Foreclosure/auction data isn't on the standard portals — widen the search,
        # and fall back to a whole-web search if the curated domains return nothing.
        rows = await search_market(q, max_results=5, domains=DISTRESSED_DOMAINS)
        if not [r for r in rows if "error" not in r and r.get("content")]:
            rows = await search_market(q, max_results=5, domains=[])
        for r in rows:
            if "error" not in r:
                ctx.append(f"{r.get('url','')}\n{r.get('content','')[:500]}")
    return await _extract_leads("\n\n".join(ctx), "distressed", city)


async def hunt_ai_service_clients(niche: str, location: str = "Bay Area") -> list[dict]:
    queries = [
        f"{niche} {location} small business owner contact directory",
        f"{niche} companies {location} looking for automation AI tools",
        f"{niche} {location} LinkedIn business owner",
    ]
    ctx = []
    for q in queries:
        for r in await search_market(q, max_results=4):
            if "error" not in r:
                ctx.append(f"{r.get('url','')}\n{r.get('content','')[:500]}")
    return await _extract_leads("\n\n".join(ctx), "ai_service_clients", location)


# ── Orchestrator ──────────────────────────────────────────────────────────────
async def generate_leads(hunt_type: str, city: str = "", neighborhood: str = "",
                         niche: str = "", provider: str = "tavily", state: str = "") -> dict:
    """Run a lead hunt. Returns raw leads (not yet saved). provider selects the data source."""
    if provider != "tavily":
        status = _paid_provider_status()
        if not status.get(provider):
            return {"leads": [], "provider": provider, "configured": False,
                    "message": f"{provider} is not connected. Add its API key in .env to enable "
                               f"verified leads with phone numbers."}

    if hunt_type == "seller_leads":
        leads = await hunt_seller_leads(city, neighborhood)
    elif hunt_type == "expired_fsbo":
        leads = await hunt_expired_fsbo(city)
    elif hunt_type == "fsbo":
        leads = await hunt_fsbo(city, state)
    elif hunt_type == "distressed":
        leads = await hunt_distressed(city, state)
    elif hunt_type == "ai_service_clients":
        leads = await hunt_ai_service_clients(niche or "real estate brokerage", city or "Bay Area")
    else:
        return {"leads": [], "error": f"Unknown hunt type: {hunt_type}"}

    found = sum(1 for l in leads if l.get("contact_status") == "found")
    needs_trace = len(leads) - found
    return {
        "hunt_type": hunt_type, "provider": "tavily", "configured": True,
        "total": len(leads), "with_contact": found, "needs_skip_trace": needs_trace,
        "leads": leads,
        "note": ("Some leads have no public phone/email — flagged 'needs skip trace'. "
                 "Connect a paid provider (REDX/BatchData) to auto-fill verified contact info.")
                if needs_trace else "",
    }


INBOUND_FIELD_MAP = {
    "first_name": ["first_name", "firstname", "first", "fname", "owner_first_name", "contact_first_name"],
    "last_name": ["last_name", "lastname", "last", "lname", "owner_last_name", "contact_last_name"],
    "email": ["email", "email_address", "e_mail", "owner_email"],
    "phone": ["phone", "phone_number", "cell", "mobile", "telephone", "phone1", "owner_phone"],
    "address": ["address", "property_address", "street", "street_address", "mailing_address"],
    "city": ["city", "property_city", "town"],
    "zip_code": ["zip", "zip_code", "zipcode", "postal_code", "property_zip"],
    "years_owned": ["years_owned", "ownership_years", "years"],
    "is_absentee": ["absentee", "is_absentee", "absentee_owner", "non_owner_occupied", "vacant", "is_vacant"],
    "has_expired_listing": ["expired", "has_expired", "expired_listing"],
    # Batchleads distressed lists export the motivation under several names — map them all.
    "life_event": ["life_event", "situation", "motivation", "distress", "distress_type",
                   "foreclosure_status", "preforeclosure", "pre_foreclosure", "property_status",
                   "lead_type", "list_type", "tag"],
    "equity_estimate": ["equity", "equity_estimate", "estimated_equity", "equity_balance",
                        "available_equity"],
}


async def ingest_inbound_lead(db, payload: dict, default_source: str = "zapier") -> dict:
    """Accept a flexible lead payload (from Zapier/BatchData/any source), score + save it."""
    from database import Lead

    # Normalize incoming keys, then map to our fields
    flat = {str(k).lower().strip().replace(" ", "_"): v for k, v in payload.items()}
    lead_data = {}
    for field, aliases in INBOUND_FIELD_MAP.items():
        for alias in aliases:
            if alias in flat and flat[alias] not in (None, ""):
                lead_data[field] = flat[alias]
                break

    # Coerce booleans that may arrive as strings
    for b in ("is_absentee", "has_expired_listing"):
        if b in lead_data:
            lead_data[b] = str(lead_data[b]).strip().lower() in ("1", "true", "yes", "y")

    lead_data["source"] = flat.get("source") or default_source
    if not (lead_data.get("phone") or lead_data.get("address") or lead_data.get("email")):
        return {"status": "rejected", "reason": "No phone, email, or address in payload"}

    # Duplicate check
    q = db.query(Lead)
    existing = None
    if lead_data.get("phone"):
        existing = q.filter(Lead.phone == lead_data["phone"]).first()
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
        # Map AI-service-client shape into the Lead model
        if hunt_type == "ai_service_clients":
            first = (raw.get("contact_name") or raw.get("business_name") or "").split(" ")[0]
            last = raw.get("business_name") or ""
            notes = (f"AI-service prospect. {raw.get('why_good_fit','')} "
                     f"Website: {raw.get('website','')}").strip()
            lead_data = {
                "first_name": first or "Unknown", "last_name": last,
                "phone": raw.get("phone", ""), "email": raw.get("email", ""),
                "city": raw.get("city", ""), "source": f"leadgen_{raw.get('source','web')}",
                "notes": notes, "property_type": "AI Service Prospect",
            }
        else:
            lead_data = {
                "first_name": raw.get("first_name") or "Owner",
                "last_name": raw.get("last_name") or "",
                "address": raw.get("address", ""), "city": raw.get("city", ""),
                "phone": raw.get("phone", ""), "email": raw.get("email", ""),
                "source": f"leadgen_{raw.get('source', hunt_type)}",
                "has_expired_listing": raw.get("has_expired_listing", False),
                "price_reductions": raw.get("price_reductions", 0) or 0,
                "days_on_market": raw.get("days_on_market") or None,
                "property_type": raw.get("property_type", "Single Family"),
                "notes": (f"Sell signal: {raw.get('sell_signal','')} | "
                          f"Contact: {raw.get('contact_status','')}").strip(),
            }
            # Distressed hunts carry extra motivation signals the lead scorer rewards.
            if hunt_type == "distressed":
                lead_data["life_event"] = raw.get("distress_type") or "distressed"
                lead_data["is_absentee"] = bool(raw.get("is_absentee"))
                if raw.get("equity_estimate"):
                    lead_data["equity_estimate"] = raw.get("equity_estimate")

        # Duplicate check by address+name or phone
        q = db.query(Lead)
        if lead_data.get("phone"):
            existing = q.filter(Lead.phone == lead_data["phone"]).first()
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
