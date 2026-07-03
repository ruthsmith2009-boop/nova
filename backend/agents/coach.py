"""
ARIA Coach — in-the-moment coaching for Ruth (NOT the sellable coaching product).

Acts like a top-producing broker mentor: answers "what do I say / what's my next move / how do I
handle this" with specific, actionable guidance and real words to use. Powered by the Brain.
"""
from agents.brain import think, SANTA_CLARA_KNOWLEDGE

COACH_PERSONA = """You are ARIA's real-estate COACH for the agent using this app. Coach like a
top-producing broker mentor with deep Santa Clara County / Bay Area experience, trained on the best
(Mike Ferry, Tom Ferry, Brian Buffini, Brandon Mulrenin).

How you coach:
- Be direct, specific, and confident. Give the actual WORDS to say, not vague theory.
- Keep it tight and practical — a few clear moves, not an essay.
- When useful, give a short script or the exact next step.
- If it's a pricing/strategy question, reason like a pro and commit to a recommendation.
- You are a coach/assistant, not a lawyer — for legal/contract specifics, tell them to run it
  through the Compliance check or a licensed attorney."""


async def coach_answer(question: str, lead_context: str = "") -> str:
    prompt = f"Agent's question:\n{question}"
    if lead_context:
        prompt += f"\n\nContext about the lead they're asking about:\n{lead_context}"
    return await think(prompt, system_extra=COACH_PERSONA)


async def coach_next_move(lead: dict) -> str:
    summary = (
        f"Lead: {lead.get('first_name','')} {lead.get('last_name','')}\n"
        f"Address: {lead.get('address','')} {lead.get('city','')}\n"
        f"Temperature: {lead.get('temperature','')} | Stage: {lead.get('stage','')} | "
        f"Score: {lead.get('score',0)}/100\n"
        f"Situation/life event: {lead.get('life_event','unknown')}\n"
        f"Last contact: {lead.get('last_contact','none')} | Next follow-up: {lead.get('next_follow_up','none')}\n"
        f"Notes: {lead.get('notes','')}"
    )
    return await think(
        f"Coach me on the single best next move with this lead, and give me the exact words to use.\n\n{summary}",
        system_extra=COACH_PERSONA,
    )


QUICK_PROMPTS = [
    "What should I say to a seller who thinks their home is worth more than the comps?",
    "How do I handle “we want to wait until spring”?",
    "Give me a 30-second voicemail for an expired listing.",
    "How do I ask for a price reduction without losing the listing?",
    "What's my best opening line for a FSBO?",
    "How do I follow up with a lead who's gone quiet?",
]
