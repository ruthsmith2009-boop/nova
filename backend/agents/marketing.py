"""
Marketing Engine — offer descriptions, social posts, newsletters, email sequences.
Industry-agnostic: works for any small business generating and nurturing leads.
"""
import json
from agents.brain import think, BUSINESS_KNOWLEDGE
from config import settings


async def write_weekly_newsletter(topic: str, context: dict = None) -> str:
    """Generate a weekly value newsletter for the business's audience (any industry)."""
    context = context or {}
    return await think(
        f"""Write a weekly email newsletter about "{topic}" for a small business's audience of
customers and prospects. Adapt to whatever industry the topic implies — never assume real estate.

Any context/notes to include: {json.dumps(context, indent=2)}

{BUSINESS_KNOWLEDGE}

Write a professional, engaging ~500-word newsletter as {settings.agent_name} of {settings.broker_name}.
Include:
1. A short, friendly intro that hooks the reader
2. The main value section — a helpful insight, update, or how-to on the topic
3. A quick tip of the week the reader can act on today
4. A light, genuine story or example
5. A clear call to action (book a quick call, reply, claim an offer)

Tone: knowledgeable, warm, helpful — like the most useful person in their inbox, not salesy.

Format with HTML-ready headers (use <h2>, <p>, <strong> tags) for email rendering."""
    )


async def write_email_sequence(lead: dict, sequence_type: str) -> list[dict]:
    """Generate a complete email follow-up sequence for a lead stage (universal sales nurture)."""
    sequences = {
        "new_lead": {
            "emails": 5,
            "days": [0, 3, 7, 14, 30],
            "description": "New lead nurture — build trust, provide value, soft ask"
        },
        "post_meeting": {
            "emails": 4,
            "days": [0, 2, 7, 14],
            "description": "After a call/meeting — follow up, handle hesitation, ask for the sale"
        },
        "active_deal": {
            "emails": 6,
            "days": [0, 3, 7, 14, 21, 30],
            "description": "Open opportunity — keep momentum, reassure, keep them engaged"
        },
        "proposal_sent": {
            "emails": 5,
            "days": [0, 3, 7, 14, 21],
            "description": "Proposal follow-up — answer objections, add urgency, close"
        },
        "won": {
            "emails": 4,
            "days": [1, 30, 180, 365],
            "description": "Post-sale nurture — onboarding, referral ask, check-ins"
        }
    }

    seq = sequences.get(sequence_type, sequences["new_lead"])
    lead_name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}"

    result = await think(
        f"""Create a {seq['emails']}-email follow-up sequence for this lead.

Lead: {lead_name}
Company / location: {lead.get('address', '')} {lead.get('city', '')}
What they need / situation: {lead.get('life_event', 'a prospect')}
Sequence: {sequence_type} — {seq['description']}
Send days: {seq['days']} (day 0 = today)

{BUSINESS_KNOWLEDGE}

Write each email. Return JSON array:
[
  {{
    "email_number": 1,
    "send_day": 0,
    "subject": "A quick idea for you",
    "body": "Hi [First Name],\\n\\n[Full email body — 150-250 words, personal, valuable, no hard sell on first email]\\n\\nBest,\\n{settings.agent_name}",
    "purpose": "Build trust, no ask",
    "cta": "soft — reply or grab a quick call"
  }}
]

Make each email genuinely valuable, not a generic template. Personalize for their situation and
industry. Never assume real estate."""
    )

    try:
        return json.loads(result)
    except Exception:
        return [{"error": "Could not generate sequence", "raw": result[:300]}]


async def write_listing_presentation(listing_data: dict, cma_data: dict, seller_data: dict) -> str:
    """Generate a full sales proposal / pitch to win a client."""
    return await think(
        f"""Create a comprehensive sales proposal to win this client.

Offer / scope: {json.dumps(listing_data, indent=2)}
Pricing / numbers: {json.dumps(cma_data, indent=2)}
Client: {json.dumps(seller_data, indent=2)}

{BUSINESS_KNOWLEDGE}

Write the complete proposal as {settings.agent_name}, {settings.broker_name}.

Include all sections:
1. **About Us** — track record, results, why you're credible
2. **Your Situation** — the client's problem and the opportunity
3. **Our Recommendation** — the plan and why it works
4. **What We'll Do** — exactly how the work gets done, step by step
5. **Pricing / Investment** — options and what each includes
6. **Timeline** — week by week from start to result
7. **What Makes Us Different** — specific differentiators, not generic claims
8. **Results You Can Expect** — realistic outcomes (no unsubstantiated guarantees)
9. **Next Steps** — the ask

Format with clear headers. Write with confidence and specificity.
This should be strong enough to win the client against a competitor.
Use HTML formatting (<h2>, <h3>, <p>, <ul><li>, <strong>) for web rendering."""
    )
