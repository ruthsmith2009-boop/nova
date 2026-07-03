"""
Marketing Engine — MLS descriptions, social posts, newsletters, email sequences.
"""
import json
from agents.brain import think, SANTA_CLARA_KNOWLEDGE
from config import settings


async def write_mls_description(listing_data: dict) -> str:
    """Write an MLS listing description that creates urgency and emotional connection."""
    return await think(
        f"""Write a compelling MLS listing description for this property.

Property: {json.dumps(listing_data, indent=2)}

{SANTA_CLARA_KNOWLEDGE}

Rules for top-producing MLS copy:
- Open with the most compelling feature or lifestyle statement (NOT "Beautiful home!")
- Use vivid, specific language — not generic adjectives
- Lead with what makes this home DIFFERENT from competing listings
- Address the buyer's emotional drivers: safety, community, schools, lifestyle
- Include neighborhood/location value if it's a premium
- Hint at multiple offers without being desperate
- Close with a call to action
- Max 300 words for MLS
- NO ALL CAPS, no exclamation mark overload
- Write for the qualified buyer, not everyone

Return ONLY the listing description text, ready to paste into MLS."""
    )


async def write_social_posts(listing_data: dict, mls_description: str = "") -> dict:
    """Generate social media posts for a new listing."""
    result = await think(
        f"""Create social media posts for this new listing by {settings.agent_name}.

Property: {json.dumps(listing_data, indent=2)}
MLS Description preview: {mls_description[:200] if mls_description else 'N/A'}

{SANTA_CLARA_KNOWLEDGE}

Generate posts for each platform. Return as JSON:
{{
  "instagram_caption": "Compelling caption with line breaks and emoji. 150-200 words. End with hashtags.",
  "instagram_hashtags": "#SantaClaraCounty #[City]RealEstate #JustListed #[Neighborhood]Homes ...",
  "facebook_post": "Longer, more detailed post. Include key facts. 200-300 words. Conversational.",
  "linkedin_post": "Professional angle. Market context + listing details. 150 words. Good for SOI.",
  "twitter_x_post": "Short punchy. Key stats. CTA. Under 240 chars.",
  "stories_text": "Short text for IG/FB stories overlay. 2-3 lines max.",
  "listing_hook": "One compelling sentence for any platform",
  "email_subject": "Subject line for just-listed email blast"
}}""",
        use_haiku=True
    )

    try:
        return json.loads(result)
    except Exception:
        return {"error": "Could not generate social posts", "raw": result[:300]}


async def write_weekly_newsletter(area: str, market_data: dict) -> str:
    """Generate a weekly neighborhood market update newsletter."""
    return await think(
        f"""Write a weekly real estate market newsletter for {area}, Santa Clara County.

Market data this week: {json.dumps(market_data, indent=2)}

{SANTA_CLARA_KNOWLEDGE}

Write a professional, engaging 500-word newsletter as {settings.agent_name}.
Include:
1. Quick market snapshot (3-4 key stats in bold)
2. What's happening in the neighborhood (new listings, price changes, sold)
3. Insight: what does this mean for sellers? For buyers?
4. Featured listing (if listing_data provided)
5. Tip of the week (a quick, valuable real estate insight)
6. Call to action: book a free home valuation

Tone: Knowledgeable neighbor, not salesy. Like the most informed person in the neighborhood
is giving you the real inside scoop.

Format with HTML-ready headers (use <h2>, <p>, <strong> tags) for email rendering."""
    )


async def write_email_sequence(lead: dict, sequence_type: str) -> list[dict]:
    """Generate a complete email follow-up sequence for a lead stage."""
    sequences = {
        "new_lead": {
            "emails": 5,
            "days": [0, 3, 7, 14, 30],
            "description": "New lead nurture — establish expertise, provide value, soft ask"
        },
        "post_appointment": {
            "emails": 4,
            "days": [0, 2, 7, 14],
            "description": "After listing presentation — follow up, handle hesitation, close"
        },
        "active_listing": {
            "emails": 6,
            "days": [0, 3, 7, 14, 21, 30],
            "description": "Seller update sequence — activity report, market pulse, engagement"
        },
        "under_contract": {
            "emails": 5,
            "days": [0, 5, 10, 20, -3],
            "description": "Transaction updates — milestones, deadlines, reassurance"
        },
        "closed": {
            "emails": 4,
            "days": [1, 30, 180, 365],
            "description": "Post-close nurture — referral ask, anniversary, market updates"
        }
    }

    seq = sequences.get(sequence_type, sequences["new_lead"])
    lead_name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}"

    result = await think(
        f"""Create a {seq['emails']}-email follow-up sequence for this lead.

Lead: {lead_name}
Address: {lead.get('address', '')} {lead.get('city', '')}
Situation: {lead.get('life_event', 'homeowner')}
Sequence: {sequence_type} — {seq['description']}
Send days: {seq['days']} (day 0 = today, day -3 = 3 days before close)

{SANTA_CLARA_KNOWLEDGE}

Write each email. Return JSON array:
[
  {{
    "email_number": 1,
    "send_day": 0,
    "subject": "Your home value in today's {lead.get('city', 'Santa Clara County')} market",
    "body": "Hi [First Name],\\n\\n[Full email body — 150-250 words, personal, valuable, no hard sell on first email]\\n\\nBest,\\n{settings.agent_name}",
    "purpose": "Establish value, no ask",
    "cta": "soft — read the market report"
  }}
]

Make each email genuinely valuable, not a generic template. Personalize for their situation.
Use their address/neighborhood for specificity.""",
    )

    try:
        return json.loads(result)
    except Exception:
        return [{"error": "Could not generate sequence", "raw": result[:300]}]


async def write_listing_presentation(listing_data: dict, cma_data: dict, seller_data: dict) -> str:
    """Generate content for a full listing presentation."""
    return await think(
        f"""Create a comprehensive listing presentation for this property.

Property: {json.dumps(listing_data, indent=2)}
CMA: {json.dumps(cma_data, indent=2)}
Seller: {json.dumps(seller_data, indent=2)}

{SANTA_CLARA_KNOWLEDGE}

Write the complete listing presentation as {settings.agent_name}, {settings.broker_name}.

Include all sections:
1. **About Ruth Smith** — track record, sales volume, Santa Clara County expertise
2. **Your Neighborhood Market** — current conditions, opportunity window
3. **Your Home's Value** — CMA results, pricing strategy recommendation
4. **Marketing Plan** — exactly how we'll sell your home (MLS, social, open houses, buyer network)
5. **Pricing Strategy** — the risk of overpricing, the power of competitive pricing
6. **Timeline** — week by week from list to close
7. **Transaction Coordination** — every step handled for you
8. **What Makes Us Different** — specific differentiators, not generic claims
9. **Net Sheet Preview** — what you'll walk away with at different price points
10. **Next Steps** — the ask

Format with clear headers. Write with confidence and specificity.
This should be good enough to win a listing against a competing agent.
Use HTML formatting (<h2>, <h3>, <p>, <ul><li>, <strong>) for web rendering."""
    )
