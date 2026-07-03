"""
Lead Scoring Engine — ranks every lead by sell probability.
Factors: equity, DOM, expired listings, absentee, life events, price history.
"""
import json
import pandas as pd
from io import BytesIO
from typing import Optional
from agents.brain import think_structured, SANTA_CLARA_KNOWLEDGE


# ── Follow-up cadences (days between touches) ────────────────────────────────
CADENCE_DAYS = {
    "every_2_day": 2,
    "every_3_day": 3,
    "not_ready_7day": 7,
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "90_day": 90,
    "quarterly": 91,
    "6_month": 182,
    "yearly": 365,
    "1_2_year": 547,   # ~18 months, the post-1-year bucket
}

CADENCE_LABELS = {
    "every_2_day": "Every 2 days (hot)", "every_3_day": "Every 3 days",
    "not_ready_7day": "Not Ready — check in 7 days",
    "weekly": "Weekly", "biweekly": "Every 2 weeks", "monthly": "Monthly",
    "90_day": "Every 90 days", "quarterly": "Quarterly", "6_month": "Every 6 months",
    "yearly": "Yearly", "1_2_year": "1–2 year (long-term nurture)",
}

# Follow-up automation: sensible default cadence for each temperature, so a lead
# always has a next-touch date without the agent picking one manually.
TEMPERATURE_CADENCE = {
    "hot": "every_2_day",
    "warm": "weekly",
    "cold": "monthly",
    "not_ready": "not_ready_7day",
}


def default_cadence_for_temperature(temperature: str) -> str:
    return TEMPERATURE_CADENCE.get((temperature or "").lower(), "monthly")


def compute_next_followup(cadence: str, from_date=None):
    """Return the next follow-up datetime for a cadence."""
    from datetime import datetime, timedelta
    base = from_date or datetime.utcnow()
    days = CADENCE_DAYS.get(cadence)
    return base + timedelta(days=days) if days else None


def suggest_temperature(score: float, temperature: str = None) -> str:
    """Auto-suggest a lead temperature from score (manual 'not_ready' is preserved)."""
    if temperature == "not_ready":
        return "not_ready"
    if score >= 70:
        return "hot"
    if score >= 45:
        return "warm"
    return "cold"


def calculate_base_score(lead_data: dict) -> tuple[float, list[str]]:
    """Rule-based business-fit scoring before AI enhancement.

    Scores how good a fit a small-business owner is for NOVA's AI automation
    services — based on their stated need, source quality, and reachability.
    """
    score = 0.0
    reasons = []

    # What they need — the strongest buying signal
    need = (lead_data.get("life_event") or "").lower()
    need_scores = {
        "missed_calls":     (30, "MISSING CALLS / LOSING LEADS — biggest pain, perfect fit for AI answering + text-back."),
        "missed call":      (30, "MISSING CALLS — perfect fit for missed-call text-back."),
        "follow_up":        (25, "FOLLOW-UP FALLING THROUGH — ideal for automated follow-up sequences."),
        "follow up":        (25, "FOLLOW-UP GAPS — ideal for automated follow-up."),
        "booking":          (22, "WANTS AUTOMATED BOOKING — strong fit for AI scheduling."),
        "ai_calling":       (28, "WANTS AI CALLING — ready-to-buy signal."),
        "full_automation":  (32, "WANTS FULL AUTOMATION — high-value package fit."),
        "website":          (15, "NEEDS A WEBSITE — entry service, upsell path to automation."),
    }
    for key, (pts, reason) in need_scores.items():
        if key in need:
            score += pts
            reasons.append(reason)
            break

    # Source quality — how warm the lead is
    source = (lead_data.get("source") or "").lower()
    source_scores = {
        "referral":  (25, "Referral — warmest possible lead, high trust, fast close."),
        "website":   (18, "Inbound from website — already interested."),
        "networking":(15, "Met at a networking event — real relationship started."),
        "linkedin":  (12, "LinkedIn outreach — professional context, decent warmth."),
        "walk":      (12, "Walk-in — took initiative to reach out."),
        "google":    (10, "Found you on Google/Maps — actively looking."),
        "apollo":    (6,  "Apollo cold prospect — needs nurturing, but a qualified fit."),
        "cold call": (4,  "Cold call — coldest, expect more touches to warm up."),
    }
    matched_source = False
    for key, (pts, reason) in source_scores.items():
        if key in source:
            score += pts
            reasons.append(reason)
            matched_source = True
            break
    if not matched_source and source:
        score += 8

    # Reachability — can NOVA actually work this lead?
    if lead_data.get("phone"):
        score += 10
        reasons.append("Has a direct phone — NOVA can call and text.")
    if lead_data.get("email"):
        score += 8
        reasons.append("Has a verified email — NOVA can run email follow-up.")

    return min(score, 100), reasons


async def ai_enhance_score(lead_data: dict, base_score: float, base_reasons: list) -> dict:
    """Use AI to add nuance and suggest the best approach for each lead."""
    result = await think_structured(
        f"""You are scoring a small-business owner as a prospective client for an AI-automation
consultant (NOVA) that sets up AI phone answering, missed-call text-back, automated lead
follow-up, and online booking for local businesses.

Lead data: {json.dumps(lead_data, indent=2)}
Base score calculated: {base_score}/100
Base reasons: {json.dumps(base_reasons)}

Score how good a fit this business owner is to BUY AI-automation services, and how likely
they are to book a call. Higher = warmer, clearer pain, easier to reach and close.

Return JSON:
{{
  "final_score": 72.5,
  "score_grade": "A",
  "sell_probability": "High",
  "best_approach": "Lead with the missed-call pain — every missed call is a lost job. Offer a 10-min demo.",
  "best_time_to_call": "Weekdays 9-11am before the day gets busy",
  "email_subject_line": "quick question about missed calls at [Company]",
  "key_talking_points": [
    "Local service owners lose 20-30% of leads to missed calls and voicemail tag",
    "AI answers instantly, texts back, and books the job while they work",
    "Set up in days, runs for about the cost of one lost job a month"
  ],
  "objections_to_expect": ["I'm too busy to set this up", "I already have a receptionist", "Is it expensive?"],
  "urgency_factors": ["Every missed call this week is a job lost to a competitor"],
  "final_reasons": ["reason 1", "reason 2"]
}}""",
        use_haiku=True
    )

    try:
        return json.loads(result)
    except Exception:
        return {
            "final_score": base_score,
            "score_grade": "B" if base_score >= 50 else "C",
            "sell_probability": "Medium",
            "best_approach": "Lead with their biggest time-drain; offer a short demo.",
            "final_reasons": base_reasons
        }


async def score_lead(lead_data: dict) -> dict:
    """Full scoring pipeline for a single lead."""
    base_score, base_reasons = calculate_base_score(lead_data)
    ai_result = await ai_enhance_score(lead_data, base_score, base_reasons)
    ai_result["base_score"] = base_score
    ai_result["base_reasons"] = base_reasons
    return ai_result


async def generate_daily_call_list(leads: list[dict]) -> list[dict]:
    """Score all leads and return ranked daily call list with call guides."""
    scored = []
    for lead in leads:
        score_data = await score_lead(lead)
        scored.append({**lead, **score_data})

    # Sort by final_score descending
    scored.sort(key=lambda x: x.get("final_score", 0), reverse=True)

    # Add call rank and simplified call guide
    call_list = []
    for rank, lead in enumerate(scored[:25], 1):  # Top 25 for daily list
        call_list.append({
            "rank": rank,
            "name": f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
            "phone": lead.get("phone", ""),
            "address": lead.get("address", ""),
            "city": lead.get("city", ""),
            "score": lead.get("final_score", 0),
            "grade": lead.get("score_grade", "C"),
            "sell_probability": lead.get("sell_probability", "Low"),
            "why_call_today": lead.get("best_approach", ""),
            "script": lead.get("best_script", ""),
            "talking_points": lead.get("key_talking_points", []),
            "objections": lead.get("objections_to_expect", []),
            "best_time": lead.get("best_time_to_call", ""),
            "lead_id": lead.get("id")
        })

    return call_list


async def process_csv_upload(file_content: bytes, filename: str) -> list[dict]:
    """Parse uploaded CSV/Excel lead file into structured lead objects."""
    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(BytesIO(file_content))
        else:
            df = pd.read_csv(BytesIO(file_content))

        df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

        # Column mapping (flexible import)
        field_map = {
            "first_name": ["first_name", "firstname", "first", "fname"],
            "last_name": ["last_name", "lastname", "last", "lname"],
            "email": ["email", "email_address", "e_mail"],
            "phone": ["phone", "phone_number", "cell", "mobile", "telephone"],
            "address": ["address", "property_address", "street", "street_address"],
            "city": ["city", "town"],
            "zip_code": ["zip", "zip_code", "zipcode", "postal_code"],
            "years_owned": ["years_owned", "ownership_years", "years"],
            "is_absentee": ["absentee", "is_absentee", "non_owner_occupied"],
            "has_expired_listing": ["expired", "has_expired", "expired_listing"],
            "days_on_market": ["days_on_market", "dom", "days"],
            "life_event": ["life_event", "situation", "motivation"],
            "source": ["source", "lead_source", "list_source"]
        }

        leads = []
        for _, row in df.iterrows():
            lead = {}
            for field, aliases in field_map.items():
                for alias in aliases:
                    if alias in df.columns:
                        val = row.get(alias)
                        if pd.notna(val):
                            lead[field] = val
                        break
            if lead.get("first_name") or lead.get("address"):
                leads.append(lead)

        return leads
    except Exception as e:
        raise ValueError(f"Could not parse file: {e}")
