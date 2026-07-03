"""
NOVA Coach — in-the-moment coaching for the business owner using the app.

Acts like a top-producing sales mentor: answers "what do I say / what's my next move / how do I
handle this" with specific, actionable guidance and real words to use. Powered by the Brain.
"""
from agents.brain import think, BUSINESS_KNOWLEDGE

COACH_PERSONA = """You are NOVA's sales COACH for the business owner or rep using this app. Coach
like a top-producing sales mentor who has closed in many industries (home services, agencies,
consulting, SaaS, local services). You draw on the best modern sales thinking (Chris Voss,
Jeb Blount, Brandon Mulrenin's reverse selling, Sandler, consultative discovery).

How you coach:
- Be direct, specific, and confident. Give the actual WORDS to say, not vague theory.
- Keep it tight and practical — a few clear moves, not an essay.
- When useful, give a short script or the exact next step.
- If it's a pricing/strategy question, reason like a pro and commit to a recommendation.
- Stay industry-agnostic: if the question implies a specific trade, adapt to it, but never assume
  real estate or any one field.
- You are a coach/assistant, not a lawyer — for legal/contract specifics, tell them to run it
  through the Compliance check or a licensed attorney."""


async def coach_answer(question: str, lead_context: str = "") -> str:
    prompt = f"Owner's question:\n{question}"
    if lead_context:
        prompt += f"\n\nContext about the lead they're asking about:\n{lead_context}"
    return await think(prompt, system_extra=COACH_PERSONA)


async def coach_next_move(lead: dict) -> str:
    summary = (
        f"Lead: {lead.get('first_name','')} {lead.get('last_name','')}\n"
        f"Company / location: {lead.get('address','')} {lead.get('city','')}\n"
        f"Temperature: {lead.get('temperature','')} | Stage: {lead.get('stage','')} | "
        f"Score: {lead.get('score',0)}/100\n"
        f"What they need / situation: {lead.get('life_event','unknown')}\n"
        f"Last contact: {lead.get('last_contact','none')} | Next follow-up: {lead.get('next_follow_up','none')}\n"
        f"Notes: {lead.get('notes','')}"
    )
    return await think(
        f"Coach me on the single best next move with this lead, and give me the exact words to use.\n\n{summary}",
        system_extra=COACH_PERSONA,
    )


QUICK_PROMPTS = [
    "How do I handle a prospect who says \"you're too expensive\"?",
    "How do I handle \"we want to wait\" or \"now's not a good time\"?",
    "Give me a 30-second voicemail for a lead who's gone cold.",
    "How do I ask for the sale without being pushy?",
    "What's my best opening line on a cold call?",
    "How do I follow up with a lead who's gone quiet?",
]
