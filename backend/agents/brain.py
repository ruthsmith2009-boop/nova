"""
ARIA's AI Brain — routes tasks to the right model for cost efficiency.
Complex tasks (docs, presentations, objection handling) → Claude Sonnet
Research/data tasks → Claude Haiku
"""
import anthropic
from config import settings

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"

SYSTEM_PERSONA = f"""You are ARIA — an AI real estate agent assistant with the knowledge, skills, and
instincts of a top-producing listing agent. You operate at the level of the best agents in the market.

Your agent: {settings.agent_name} | {settings.broker_name} | DRE #{settings.agent_license}
Home base: San Jose & Santa Clara County, California (and the greater Bay Area).
Coverage: You can research markets, run CMAs, and advise on properties ANYWHERE in the United States —
not just California. When a property or lead is outside the Bay Area, adapt to that local market, its
state's real estate laws, and its disclosure requirements. Never assume California rules apply elsewhere.

You know:
- Your home market — San Jose & every Santa Clara County micro-market — deeply: price per sqft, turnover, buyer demographics
- How to quickly research and analyze ANY US market you're given (price trends, comps, local dynamics)
- California real estate law, CAR forms, C.A.R. standard of practice — and how to flag when out-of-state rules differ
- Scripts from Mike Ferry, Tom Ferry, Brian Buffini, and Brandon Mulrenin (especially reverse selling, expired approach)
- Pricing strategy: how to price to sell vs. price to net maximum
- Objection handling: you are confident, consultative, and data-backed
- Transaction coordination: you never miss a deadline
- Marketing: MLS descriptions that create urgency and emotional connection

When giving advice, think and respond like the best agent in the room. Be direct, confident, and specific."""


async def think(prompt: str, system_extra: str = "", use_haiku: bool = False) -> str:
    """Send a prompt to Claude and get a response."""
    client = get_client()
    model = HAIKU if use_haiku else SONNET
    system = SYSTEM_PERSONA
    if system_extra:
        system = system + "\n\n" + system_extra

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


def _strip_json_fences(text: str) -> str:
    """Strip ```json ... ``` code fences (and stray prose) so json.loads works.
    Models often wrap JSON in markdown fences despite being told not to."""
    t = text.strip()
    if t.startswith("```"):
        # drop the opening fence line (``` or ```json) and the closing fence
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
        t = t.strip()
    # If there's still leading/trailing prose, grab the outermost JSON object/array.
    if not (t.startswith("{") or t.startswith("[")):
        starts = [i for i in (t.find("{"), t.find("[")) if i != -1]
        ends = [i for i in (t.rfind("}"), t.rfind("]")) if i != -1]
        if starts and ends:
            t = t[min(starts):max(ends) + 1]
    return t.strip()


async def think_structured(prompt: str, system_extra: str = "", use_haiku: bool = False) -> str:
    """Like think() but instructs Claude to return JSON. Strips markdown fences so the
    result is safe to pass straight into json.loads()."""
    raw = await think(
        prompt,
        system_extra=(system_extra + "\n\nRespond ONLY with valid JSON. No markdown, no explanation."),
        use_haiku=use_haiku
    )
    return _strip_json_fences(raw)


SANTA_CLARA_KNOWLEDGE = """
Santa Clara County Micro-Market Knowledge Base:

WILLOW GLEN (San Jose 95125, 95008):
- Charming bungalows, craftsmen, Spanish revival. Strong community identity.
- Median ~$1.4-1.6M. Buyers: young families, downsizers. Very low inventory.
- Lincoln Ave corridor drives premium pricing. Walkability premium.

LOS GATOS (95030, 95032):
- Premium suburban. Top-rated schools (Los Gatos Union, LGUSD).
- Median $2.2-2.8M. Luxury homes, hillside estates.
- Strong tech buyer pool (Netflix, Apple employees).

SARATOGA (95070):
- Prestige market. Saratoga Union schools = massive premium.
- Median $2.8-3.5M. Estate lots, custom homes.
- Asian buyer demographic strong. All-cash offers common.

CUPERTINO (95014):
- Apple HQ effect. #1 school district in county (Cupertino Union + Fremont HS).
- Median $2.4-3.0M. Heavy Chinese-American buyer pool.
- Multiple offers standard even in slow markets.

SUNNYVALE (94085-94089):
- Tech corridor (LinkedIn, Google, Amazon). Mix of price points.
- Median $1.8-2.2M. Strong rental demand.

CAMPBELL (95008):
- Undervalued relative to neighbors. Up-and-coming.
- Median $1.3-1.5M. Young professionals, first-time move-up buyers.
- Downtown Campbell = walkability premium.

SAN JOSE NEIGHBORHOODS:
- Almaden Valley: $1.8-2.2M, Almaden schools, established families
- Evergreen: $1.2-1.5M, newer construction, diverse buyers
- Berryessa: $900K-1.2M, BART access, value play
- Silver Creek: $1.5-1.8M, guard-gated, luxury

MARKET DYNAMICS:
- Spring (Feb-May): Peak season, 15-25% above asking typical in hot micro-markets
- Summer: Slightly slower, international buyers active
- Fall: Second strongest season
- Winter: Lowest inventory = least competition, serious buyers only
- Tech layoffs = 10-15% demand reduction in affected areas
- Interest rate sensitivity: Every 1% rate increase = ~10% buyer pool reduction
"""
