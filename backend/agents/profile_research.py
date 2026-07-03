"""
Prospect Research — the safe, compliant "you look, NOVA works" way to work a
LinkedIn (or any) profile without scraping.

You view the profile like a normal person and paste the public text in. NOVA then:
  1. Parses the paste into clean, structured fields (name, title, company, etc.)
  2. Optionally pulls extra public context off the open web (Tavily, best-effort)
  3. Scores the prospect with NOVA's existing lead-scoring engine
  4. Writes ready-to-send outreach in the owner's voice:
       - a short LinkedIn connection note (fits LinkedIn's ~300-char limit)
       - a LinkedIn DM / first message
       - a cold email (subject + body)

No scraping and no automation against any platform — a human does the viewing and
pasting, which keeps the account and the business safe. NOVA never invents a fact
that isn't in the pasted text or the web results; unknown fields stay blank.
"""
import json
from typing import Optional

from agents.brain import think, think_structured, BUSINESS_KNOWLEDGE
from agents.research import search_market
from agents.lead_scorer import score_lead, calculate_base_score
from config import settings


async def parse_profile(profile_text: str) -> dict:
    """Pull clean, structured fields out of pasted profile text. Never fabricates —
    anything not present in the paste is left blank."""
    schema = """{
  "first_name": "", "last_name": "", "title": "", "company": "",
  "location": "", "headline": "", "industry": "",
  "email": "", "phone": "", "website": "", "linkedin_url": "",
  "summary": "1-2 sentence plain-English summary of who they are and what they do",
  "signals": ["notable facts pulled ONLY from the text: seniority, company size hints, recent role change, hiring, growth, pain clues"]
}"""
    result = await think_structured(
        f"""Extract structured contact/prospect data from this pasted public profile text
(it may be from LinkedIn, a company About page, or a business directory).

Profile text:
\"\"\"{profile_text[:6000]}\"\"\"

RULES:
- Use ONLY what is actually in the text. NEVER invent a name, email, phone, or company.
- If a field is not present, leave it as "" (empty string). Empty is better than guessed.
- "signals" = short factual bullet points you can actually see in the text (their seniority,
  whether they seem to be a decision-maker, company size hints, a recent job change, hiring, etc.).

Return JSON shaped exactly like:
{schema}""",
        use_haiku=True,
    )
    try:
        data = json.loads(result)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def web_context(parsed: dict) -> list[dict]:
    """Best-effort: pull a little extra PUBLIC context about the person/company from the
    open web so outreach can be specific. Never blocks the flow if it fails."""
    name = f"{parsed.get('first_name','')} {parsed.get('last_name','')}".strip()
    company = parsed.get("company", "")
    if not (name or company):
        return []
    query = f"{name} {company} {parsed.get('title','')}".strip()
    try:
        results = await search_market(query, max_results=3)
        return [r for r in results if "error" not in r]
    except Exception:
        return []


def _lead_data_from_parsed(parsed: dict, niche: str = "") -> dict:
    """Map parsed profile fields onto the CRM lead shape the scorer expects."""
    # life_event carries the prospect's situation/need for the scorer; use their title/industry
    # as the best available "what's going on" signal.
    need = parsed.get("industry") or parsed.get("title") or niche or ""
    return {
        "first_name": parsed.get("first_name", "") or "Contact",
        "last_name": parsed.get("last_name", "") or parsed.get("company", ""),
        "email": parsed.get("email", ""),
        "phone": parsed.get("phone", ""),
        "address": parsed.get("company", ""),
        "city": parsed.get("location", ""),
        "source": "linkedin",
        "life_event": need,
    }


async def write_outreach(parsed: dict, context: list[dict], niche: str,
                         offer: str, tone: str = "warm, professional, human") -> dict:
    """Write connection note + DM + email tailored to this prospect, in the owner's voice."""
    ctx_text = "\n".join(f"- {r.get('title','')}: {r.get('content','')[:300]}" for r in context) or "None."
    what_i_sell = offer or f"{niche} services" if niche else "my services"

    result = await think_structured(
        f"""Write outreach to this prospect for {settings.agent_name} at {settings.broker_name}.

WHAT THE OWNER SELLS: {what_i_sell}
PROSPECT (parsed from a profile they viewed):
{json.dumps(parsed, indent=2)}

EXTRA PUBLIC CONTEXT (from the open web, may be empty):
{ctx_text}

Use the sales playbook below. Lead with the PROSPECT'S likely problem, not the product.
Keep it human and specific to this person — reference something real from their profile.
One clear, tiny call to action (a short call). No hype, no buzzwords, no em-dashes.
Tone: {tone}. Sound like a real person wrote it, not AI.

Write THREE versions:
1. connection_note: a LinkedIn connection request under 280 characters (no link, no hard pitch — just a genuine reason to connect).
2. dm: a LinkedIn direct message / first message, 3-5 short sentences, ends with a soft ask.
3. email: a cold email with a short curiosity subject line and a 4-6 sentence body.

Return JSON:
{{
  "connection_note": "",
  "dm": "",
  "email_subject": "",
  "email_body": "",
  "why_this_works": "one line on the angle you took and why it should land"
}}""",
        system_extra=BUSINESS_KNOWLEDGE,
    )
    try:
        return json.loads(result)
    except Exception:
        return {
            "connection_note": "",
            "dm": "",
            "email_subject": "",
            "email_body": result,  # fall back to raw text so nothing is lost
            "why_this_works": "",
        }


async def research_profile(profile_text: str, niche: str = "", offer: str = "",
                           enrich: bool = True) -> dict:
    """Full pipeline: parse → (optional) web context → score → write outreach."""
    if not profile_text or len(profile_text.strip()) < 20:
        return {"error": "Paste more of the profile — there isn't enough text to work with."}

    parsed = await parse_profile(profile_text)
    if not parsed:
        return {"error": "Couldn't read that profile text. Try pasting the About/Experience section."}

    context = await web_context(parsed) if enrich else []
    lead_data = _lead_data_from_parsed(parsed, niche)

    # Score — always fall back to the deterministic base score so we never return 0 on AI hiccup.
    try:
        score = await score_lead(lead_data)
    except Exception:
        base_score, base_reasons = calculate_base_score(lead_data)
        score = {"final_score": base_score, "final_reasons": base_reasons,
                 "score_grade": "B" if base_score >= 50 else "C"}

    outreach = await write_outreach(parsed, context, niche, offer)

    return {
        "parsed": parsed,
        "web_context": [{"title": r.get("title", ""), "url": r.get("url", "")} for r in context],
        "score": score,
        "outreach": outreach,
        "lead_data": lead_data,  # ready to save to the CRM
    }
