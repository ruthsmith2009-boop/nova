"""
Market Research Engine — pulls live data via Tavily, runs CMAs, tracks market trends.
"""
import json
import asyncio
from datetime import datetime
from typing import Optional
from tavily import TavilyClient
from config import settings
from agents.brain import think, think_structured, SANTA_CLARA_KNOWLEDGE

_tavily = None


def get_tavily() -> TavilyClient:
    global _tavily
    if _tavily is None:
        _tavily = TavilyClient(api_key=settings.tavily_api_key)
    return _tavily


HOME_MARKET_TERMS = [
    "santa clara", "san jose", "willow glen", "los gatos", "saratoga", "cupertino",
    "sunnyvale", "campbell", "almaden", "evergreen", "berryessa", "silver creek",
    "bay area", "south bay", "silicon valley", "95125", "95008", "95030", "95032",
    "95070", "95014", "94085", "94086", "94087", "94089",
]


def _is_home_market(city: str = "", location: str = "") -> bool:
    """True if the location looks like Ruth's home market (SCC / San Jose / Bay Area)."""
    text = f"{city} {location}".lower()
    return any(term in text for term in HOME_MARKET_TERMS)


DEFAULT_MARKET_DOMAINS = ["zillow.com", "redfin.com", "realtor.com", "mercurynews.com",
                          "sfgate.com", "bizjournals.com", "car.org"]
# Distressed/foreclosure data lives on auction + public-record sites, not the standard portals.
DISTRESSED_DOMAINS = ["zillow.com", "redfin.com", "realtor.com", "auction.com",
                      "foreclosure.com", "realtytrac.com", "hubzu.com"]


async def search_market(query: str, max_results: int = 5, domains: list = None) -> list[dict]:
    """Search the web for real estate market data.
    `domains`: override the include-domains list. Pass [] to search the whole web (no filter)."""
    try:
        client = get_tavily()
        kwargs = {"query": query, "search_depth": "advanced", "max_results": max_results}
        # None → default portal list; non-empty list → that list; [] → no domain filter.
        use_domains = DEFAULT_MARKET_DOMAINS if domains is None else domains
        if use_domains:
            kwargs["include_domains"] = use_domains
        results = client.search(**kwargs)
        return results.get("results", [])
    except Exception as e:
        return [{"error": str(e)}]


async def get_market_snapshot(area: str) -> dict:
    """Pull current market stats for any area (city/neighborhood/region, any US state)."""
    queries = [
        f"{area} real estate market stats 2025 median price days on market",
        f"{area} home sales inventory active listings 2025",
        f"{area} real estate market update absorption rate trends"
    ]
    all_results = []
    for q in queries:
        results = await search_market(q, max_results=3)
        all_results.extend(results)

    context = "\n\n".join([
        f"Source: {r.get('url','')}\n{r.get('content','')[:500]}"
        for r in all_results if "error" not in r
    ])

    analysis = await think_structured(
        f"""Based on this live market data for {area}, extract key market statistics.

Market data:
{context}

{SANTA_CLARA_KNOWLEDGE}

Return JSON with this exact structure:
{{
  "area": "{area}",
  "median_price": 1500000,
  "avg_days_on_market": 12,
  "active_listings": 45,
  "sold_last_30_days": 28,
  "absorption_rate_months": 1.6,
  "list_to_sale_ratio": 1.08,
  "market_condition": "seller's market",
  "trend": "prices rising 5% YoY",
  "key_insights": ["insight 1", "insight 2", "insight 3"],
  "data_confidence": "high/medium/low",
  "as_of": "{datetime.now().strftime('%Y-%m-%d')}"
}}""",
        use_haiku=True
    )

    try:
        return json.loads(analysis)
    except Exception:
        return {
            "area": area,
            "error": "Could not parse market data",
            "raw": analysis[:500],
            "as_of": datetime.now().strftime('%Y-%m-%d')
        }


async def run_cma(address: str, bedrooms: int = None, bathrooms: float = None,
                  sqft: int = None, city: str = "", state: str = "") -> dict:
    """Run a full Comparative Market Analysis for any US address."""
    parts = [address]
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    location = ", ".join(parts) if len(parts) > 1 else f"{address} (confirm city/state)"

    queries = [
        f"homes sold near {location} 2024 2025 comparable sales",
        f"Redfin Zillow {location} recent sales comps",
        f"active listings similar homes {city or location} {bedrooms or 3} bed"
    ]

    all_results = []
    for q in queries:
        results = await search_market(q, max_results=4)
        all_results.extend(results)

    context = "\n\n".join([
        f"Source: {r.get('url','')}\n{r.get('content','')[:600]}"
        for r in all_results if "error" not in r
    ])

    prop_details = f"Property: {location}"
    if bedrooms:
        prop_details += f", {bedrooms} bed"
    if bathrooms:
        prop_details += f", {bathrooms} bath"
    if sqft:
        prop_details += f", {sqft} sqft"

    home_market_ref = SANTA_CLARA_KNOWLEDGE if _is_home_market(city, location) else \
        "(Out-of-area property — use local market data from the search results; do NOT apply Santa Clara County figures.)"

    cma_result = await think_structured(
        f"""Run a professional CMA (Comparative Market Analysis) for this property.

{prop_details}

Live market data gathered:
{context}

Home-market reference (use ONLY if the subject property is in this area):
{home_market_ref}

Provide THREE SEPARATE comp sets so the agent/client can compare sources side by side:
- "zillow_comps": comps drawn from Zillow data in the results (Zestimate-influenced)
- "redfin_comps": comps drawn from Redfin data in the results
- "mls_comps": comps that look like agent/MLS sold data
Each source often values a home differently — showing all three builds trust and supports pricing.
If a source has no data in the results, return an empty array for it and note it.

Return a detailed JSON CMA:
{{
  "subject_property": "{address}",
  "suggested_list_price_low": 1400000,
  "suggested_list_price_mid": 1475000,
  "suggested_list_price_high": 1550000,
  "recommended_list_price": 1475000,
  "pricing_strategy": "moderate",
  "price_per_sqft": 850,
  "source_estimates": {{
    "zillow_estimate": 1460000,
    "redfin_estimate": 1490000,
    "mls_comp_based": 1475000,
    "spread_note": "Zillow runs ~2% low vs Redfin here; MLS comps land in between"
  }},
  "zillow_comps": [
    {{"address": "123 Oak St", "sale_price": 1450000, "sale_date": "2025-03", "bedrooms": 3, "bathrooms": 2, "sqft": 1600, "days_on_market": 8, "source": "Zillow"}}
  ],
  "redfin_comps": [
    {{"address": "789 Pine St", "sale_price": 1490000, "sale_date": "2025-04", "bedrooms": 3, "bathrooms": 2, "sqft": 1620, "days_on_market": 6, "source": "Redfin"}}
  ],
  "mls_comps": [
    {{"address": "456 Elm Ave", "sale_price": 1475000, "sale_date": "2025-03", "bedrooms": 3, "bathrooms": 2, "sqft": 1580, "days_on_market": 9, "source": "MLS"}}
  ],
  "active_competition": [
    {{"address": "456 Elm Ave", "list_price": 1499000, "days_on_market": 15, "bedrooms": 3, "sqft": 1550}}
  ],
  "market_conditions": "Seller's market with low inventory",
  "absorption_rate_months": 1.4,
  "avg_days_on_market": 10,
  "pricing_rationale": "Based on the three comp sets and current demand...",
  "aggressive_strategy": "List at $1.35M to generate multiple offers",
  "conservative_strategy": "List at $1.55M, allow room to negotiate",
  "recommended_strategy": "List at $1.475M — priced to attract serious buyers while leaving negotiation room",
  "estimated_net_proceeds": {{
    "sale_price": 1475000,
    "agent_commission_total": 41300,
    "title_escrow_fees": 8500,
    "transfer_tax": 1623,
    "misc_closing": 3000,
    "estimated_net": 1420577
  }}
}}""",
    )

    try:
        return json.loads(cma_result)
    except Exception:
        return {"error": "CMA generation failed", "raw": cma_result[:500]}


async def enrich_property(address: str, city: str = "", state: str = "") -> dict:
    """Look up public property details for an address (beds/baths/sqft/lot/year/value).
    Uses Tavily public data (Zillow/Redfin/Realtor). Returns specs + a confidence flag.
    NOTE: public web data is approximate — flag low confidence when unsure; never invent."""
    parts = [address] + [p for p in (city, state) if p]
    location = ", ".join(parts)

    results = []
    for q in [f"{location} Zillow bedrooms bathrooms square feet year built",
              f"{location} Redfin property details lot size last sold price"]:
        for r in await search_market(q, max_results=4):
            if "error" not in r:
                results.append(f"{r.get('url','')}\n{r.get('content','')[:600]}")
    context = "\n\n".join(results)

    if not context.strip():
        return {"property_enriched": False, "enrichment_confidence": "low",
                "note": "No public property data found for this address"}

    data = await think_structured(
        f"""Extract public property details for: {location}

Search results:
{context}

RULES: Only use values that actually appear in the results. NEVER invent numbers. If a field
isn't found, use null. Set confidence "low" if the results don't clearly match this exact address.

Return JSON:
{{
  "bedrooms": 3, "bathrooms": 2, "sqft": 1600, "lot_size": "6,000 sqft",
  "year_built": 1985, "last_sold_price": 1250000, "last_sold_date": "2021-06",
  "estimated_value": 1480000, "enrichment_confidence": "high|medium|low",
  "note": "1 short sentence on what was found / any caveat"
}}""",
        use_haiku=True,
    )
    try:
        parsed = json.loads(data)
        parsed["property_enriched"] = True
        return parsed
    except Exception:
        return {"property_enriched": False, "enrichment_confidence": "low",
                "note": "Could not parse property data"}


async def track_expired_listings(city: str) -> list[dict]:
    """Find recently expired and withdrawn listings in the area."""
    results = await search_market(
        f"expired listings {city} Santa Clara County real estate price reduction withdrawn 2025",
        max_results=5
    )
    context = "\n".join([r.get("content", "")[:300] for r in results if "error" not in r])

    analysis = await think_structured(
        f"""Analyze these search results for expired/withdrawn listings in {city}.

{context}

Return JSON array of expired listing leads (use realistic Santa Clara County data if specifics unavailable):
[{{
  "address": "123 Main St",
  "city": "{city}",
  "original_list_price": 1495000,
  "days_on_market": 45,
  "price_reductions": 2,
  "last_reduction_amount": -50000,
  "expired_date": "2025-05-15",
  "reason_likely_expired": "overpriced, needed updates",
  "opportunity_score": 8.5,
  "suggested_approach": "Expired listing script — lead with data, acknowledge their frustration"
}}]""",
        use_haiku=True
    )

    try:
        return json.loads(analysis)
    except Exception:
        return []


async def get_neighborhood_report(neighborhood: str) -> str:
    """Generate a detailed neighborhood market report for newsletters/clients."""
    snapshot = await get_market_snapshot(neighborhood)
    extra_data = await search_market(
        f"{neighborhood} real estate news trends buyers sellers 2025", max_results=3
    )
    extra_context = "\n".join([r.get("content", "")[:400] for r in extra_data if "error" not in r])

    report = await think(
        f"""Write a professional neighborhood market report for {neighborhood}, Santa Clara County.

Market stats: {json.dumps(snapshot, indent=2)}

Additional context: {extra_context}

{SANTA_CLARA_KNOWLEDGE}

Format as a polished 400-word report suitable for a client newsletter or social media.
Include: current market conditions, what sellers should know, what buyers should know,
notable trends, and a forward-looking outlook. Write in a confident, knowledgeable tone
as Ruth Smith, top listing agent."""
    )
    return report
