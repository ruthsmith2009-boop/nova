"""
Finance Agent — tracks all business costs (real estate + AI/tech), flags tax-deductible
expenses, computes monthly burn, and generates plain-English spend summaries.
"""
import json
from datetime import datetime, timedelta
from agents.brain import think, think_structured

# Category sets per business segment
CATEGORIES = {
    "real_estate": [
        "MLS & Association Dues", "E&O Insurance", "Marketing & Advertising",
        "Signage & Lockboxes", "Photography & Staging", "Mileage & Auto",
        "Client Gifts", "Office & Supplies", "Continuing Education",
        "Transaction Coordination", "Referral & Commission Fees", "Licensing & DRE",
    ],
    "ai_tech": [
        "AI APIs (Claude/OpenAI)", "Web Research (Tavily)", "Calling (Twilio/Vapi)",
        "Hosting (Railway/Render)", "Lead Data (BatchLeads/REDX)", "Email (SendGrid)",
        "Domains", "Software & SaaS", "Automation (Zapier)",
    ],
    "shared": [
        "Subscriptions", "Bank & Merchant Fees", "Phone & Internet", "Accounting/Legal", "Other",
    ],
}

# The ARIA tool stack — quick-add helper so Ruth can track build costs fast.
# Amounts are EDITABLE estimates; she confirms real numbers.
ARIA_STACK = [
    {"vendor": "Anthropic (Claude API)", "category": "AI APIs (Claude/OpenAI)", "segment": "ai_tech", "recurrence": "monthly", "amount": 50, "notes": "Estimate — usage based ($40-60/mo typical)"},
    {"vendor": "Tavily", "category": "Web Research (Tavily)", "segment": "ai_tech", "recurrence": "monthly", "amount": 0, "notes": "Free tier (1,000 searches/mo)"},
    {"vendor": "Twilio", "category": "Calling (Twilio/Vapi)", "segment": "ai_tech", "recurrence": "monthly", "amount": 5, "notes": "Number ~$1.15 + A2P ~$4 + per-min usage"},
    {"vendor": "Vapi", "category": "Calling (Twilio/Vapi)", "segment": "ai_tech", "recurrence": "monthly", "amount": 0, "notes": "Usage based (~5-9¢/min). Free credits to start"},
    {"vendor": "Railway (hosting)", "category": "Hosting (Railway/Render)", "segment": "ai_tech", "recurrence": "monthly", "amount": 5, "notes": "Hobby plan, always-on"},
    {"vendor": "BatchLeads", "category": "Lead Data (BatchLeads/REDX)", "segment": "real_estate", "recurrence": "monthly", "amount": 0, "notes": "Confirm your plan price"},
    {"vendor": "SendGrid", "category": "Email (SendGrid)", "segment": "ai_tech", "recurrence": "monthly", "amount": 0, "notes": "Free tier (100 emails/day)"},
    {"vendor": "divinerealtyteam.com (domain)", "category": "Domains", "segment": "shared", "recurrence": "yearly", "amount": 18, "notes": "Annual renewal"},
]


def monthly_equivalent(amount: float, recurrence: str) -> float:
    if recurrence == "monthly":
        return amount
    if recurrence == "yearly":
        return amount / 12
    return 0.0  # one-time doesn't count toward recurring burn


def summarize(expenses: list[dict]) -> dict:
    """Compute totals: by segment, by category, monthly recurring burn, YTD, deductible."""
    now = datetime.utcnow()
    year_start = datetime(now.year, 1, 1)

    by_segment = {"real_estate": 0.0, "ai_tech": 0.0, "shared": 0.0}
    by_category = {}
    monthly_burn = 0.0
    ytd_total = 0.0
    deductible_ytd = 0.0
    recurring = []

    for e in expenses:
        amt = e.get("amount", 0) or 0
        seg = e.get("segment", "shared")
        by_segment[seg] = by_segment.get(seg, 0) + amt
        cat = e.get("category", "Other")
        by_category[cat] = by_category.get(cat, 0) + amt

        rec = e.get("recurrence", "one_time")
        if rec in ("monthly", "yearly"):
            mb = monthly_equivalent(amt, rec)
            monthly_burn += mb
            recurring.append({**e, "monthly_equivalent": round(mb, 2)})

        # YTD (count one-time in current year + recurring annualized to-date is complex;
        # keep it simple: one-time this year + recurring counted as incurred)
        edate = e.get("date")
        try:
            d = datetime.fromisoformat(edate) if isinstance(edate, str) else edate
        except Exception:
            d = now
        if d and d >= year_start:
            ytd_total += amt if rec == "one_time" else 0
        if e.get("is_tax_deductible"):
            deductible_ytd += amt if rec == "one_time" else 0

    return {
        "by_segment": {k: round(v, 2) for k, v in by_segment.items()},
        "by_category": {k: round(v, 2) for k, v in sorted(by_category.items(), key=lambda x: -x[1])},
        "monthly_recurring_burn": round(monthly_burn, 2),
        "annual_recurring": round(monthly_burn * 12, 2),
        "recurring_items": sorted(recurring, key=lambda x: -x["monthly_equivalent"]),
        "ytd_one_time": round(ytd_total, 2),
        "deductible_ytd": round(deductible_ytd, 2),
        "expense_count": len(expenses),
    }


async def ai_categorize(description: str, amount: float = 0) -> dict:
    """Suggest category, segment, and deductibility from a free-text description."""
    result = await think_structured(
        f"""Categorize this business expense for a CA real estate broker who also builds AI tools.

Expense: "{description}" (${amount})

Segments: real_estate, ai_tech, shared.
Real-estate categories: {CATEGORIES['real_estate']}
AI/tech categories: {CATEGORIES['ai_tech']}
Shared categories: {CATEGORIES['shared']}

Return JSON:
{{"segment": "real_estate|ai_tech|shared", "category": "exact category from the lists",
  "is_tax_deductible": true, "reason": "1 short sentence"}}""",
        use_haiku=True,
    )
    try:
        return json.loads(result)
    except Exception:
        return {"segment": "shared", "category": "Other", "is_tax_deductible": True,
                "reason": "Could not auto-categorize"}


async def monthly_report(expenses: list[dict], summary: dict) -> str:
    """Plain-English spend summary + insights as Ruth's finance advisor."""
    return await think(
        f"""You are Ruth Smith's finance advisor. Summarize her business spending clearly and
honestly. Be direct, like a sharp bookkeeper — flag anything notable.

Summary data: {json.dumps(summary, indent=2)}

Write a short report (~250 words):
1. Total monthly recurring burn + what's driving it
2. Real estate vs AI/tech split — what it says about where money is going
3. Tax-deductible total so far (note: not tax advice, confirm with her CPA)
4. 2-3 specific observations or money-saving opportunities
5. One encouraging note if she's keeping costs lean while building

Tone: practical, supportive, no fluff.""",
    )
