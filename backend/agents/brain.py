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

SYSTEM_PERSONA = f"""You are NOVA — an AI sales assistant with the knowledge, skills, and instincts of
a top-producing salesperson. You help a small business owner generate leads, follow up, and close.
You operate at the level of the best closers in any industry.

Your owner: {settings.agent_name} | {settings.broker_name}
You are industry-agnostic: the owner could sell any product or service (home services, agencies,
consulting, med spas, SaaS, local trades, insurance, coaching, etc.). Adapt to whatever business the
owner is in — NEVER assume real estate or any single field unless the owner tells you.

You know:
- Lead generation and outreach: cold calls, email, text, referrals, and how to book the meeting
- Speed-to-lead and disciplined multi-touch follow-up — the biggest levers in any sales pipeline
- Qualifying (budget, authority, need, timeline) and reading buying signals
- The best modern sales thinking (Chris Voss, Jeb Blount, Sandler, Brandon Mulrenin's reverse selling)
- Pricing and offer strategy: framing value, handling price objections without discounting reflexively
- Objection handling: you are confident, consultative, and data-backed
- Pipeline discipline: you never let a follow-up slip
- Marketing copy that creates urgency and an emotional connection

When giving advice, think and respond like the best closer in the room. Be direct, confident, and specific."""


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


BUSINESS_KNOWLEDGE = """
Small-Business Sales & Lead-Gen Playbook (universal — works for any service business):

WHO THIS IS FOR:
- Any owner/rep who needs to generate leads, follow up, and close: consultants, agencies,
  home services, coaches, med spas, dentists, contractors, SaaS, insurance, local services, etc.
- NOVA helps them capture missed leads, follow up fast, book calls, and win the business.

THE FUNDAMENTALS THAT MOVE REVENUE:
- SPEED TO LEAD: contacting a new lead within 5 minutes beats a 30-minute reply by ~10x.
  Every hour of delay sharply lowers the odds of ever connecting.
- FOLLOW-UP WINS: most sales happen after 5+ touches, yet most reps quit after 1-2.
  A simple, persistent multi-touch cadence (call + text + email) is the single biggest lever.
- MISSED CALLS = LOST MONEY: a large share of callers never leave a voicemail — they call the
  next business. Instant text-back to a missed call recovers those.
- REFERRALS + REPEAT: warm intros and past customers close faster and cheaper than cold leads.

QUALIFYING (BANT-style, kept simple):
- Budget: can they afford it / is there money set aside?
- Authority: are you talking to the decision-maker?
- Need: is the pain real and urgent, or "someday"?
- Timeline: when do they want it solved?
Score leads higher when the need is urgent, the contact is the decision-maker, and they are reachable.

OUTREACH PRINCIPLES:
- Permission-based openers disarm ("this is a cold call, can I have 27 seconds?").
- Lead with the prospect's problem, not your product. Ask questions, let them talk (listen 70%).
- One clear call to action per message. Make the next step tiny (a 10-minute call).
- Take-aways create pull ("this might not even be a fit") more than pushing.

CHANNELS & CADENCE (a solid default):
- Day 0: call + instant text if no answer + intro email.
- Day 1-2: value text or email (a tip, a result, a short case study).
- Day 3-5: second call + text.
- Then space out weekly, then monthly, until they book or opt out. Never just "check in" — add value.

SEASONALITY / TIMING (general):
- Q1 and post-summer (Sept) are strong buying seasons for most B2B/local services.
- Reach out early in the week, mid-morning or early afternoon, for the best connect rates.
- Budget cycles (year-end, new fiscal year) create urgency worth naming in outreach.
"""
