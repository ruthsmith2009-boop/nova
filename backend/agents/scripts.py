"""
Scripts & Objection Handling — for selling AI automation to small businesses.
Helps Ruth (AI With Ruth) win clients: cold outreach, discovery, demo booking,
and confident answers to every "I'm too busy / too expensive / already have someone" objection.
"""
from agents.brain import think

SCRIPT_LIBRARY = {
    "reverse_selling": """
REVERSE SELLING — PERMISSION-BASED OPENER (Brandon Mulrenin style, for AI automation):

① OPENER — permission + disarming honesty (lower their guard):
"Hi [Name], you don't know me, and I'll be honest — this is a cold call. Can I have
27 seconds to tell you why I called, and then you can decide if it's worth continuing
or you can hang up on me? Fair enough?"

[Wait for the yes. The yes gives YOU permission and lowers their resistance.]

② REASON — curiosity, NOT a pitch:
"So the reason I called is I work with [type of business] owners who are quietly losing
customers to missed calls and slow follow-up. Honestly, I don't even know if that's a
problem for you — it might not be. Would you be opposed to me asking a couple quick
questions to find out, and if it's not a fit, I'll get out of your hair?"

③ DISCOVERY — reverse it, let THEM pull (ask, don't tell):
- "When a call comes in and you're tied up on a job, what happens to it right now?"
- "And the ones that go to voicemail — how many of those do you figure actually call back?"
- "If a missed call never turned into a lost job again, what would that be worth to you?"

[Talk 30%, listen 70%. The person asking the questions is the one in control.
Do NOT jump in to pitch. Let the pain surface in their own words.]

④ TAKE-AWAY CLOSE — make them chase it:
"Look, I don't even know yet if what I do is right for you — and I'd rather tell you it's
not than sell you something you don't need. Would you be opposed to a quick 10-minute look
so we can both find out? If it's not for you, no hard feelings at all."

GOLDEN RULES (Brandon's reverse-selling philosophy):
- Never pitch. Ask questions and let them sell themselves.
- Lead with the truth ("this is a cold call") — honesty disarms.
- Use take-aways ("this might not be for you") — scarcity makes them lean in.
- The goal of the call is the next step (the demo), not to close on the phone.
""",

    "missed_call_pain": """
MISSED-CALL PAIN OPENER (the #1 hook for local businesses):

"Hi [Name], this is Ruth with AI With Ruth. I'll be quick — I help [type of business]
owners stop losing customers to missed calls and voicemail tag.

Quick question: when you're busy on a job and the phone rings, what happens to that call?

[Listen.]

Right — and here's the thing: most of those callers don't leave a message, they just
call the next business on Google. I set up a simple AI assistant that answers instantly,
texts them back, and books the job for you — even when you can't pick up.

Would it be worth 10 minutes to see how it'd work for [Company]?"
""",

    "cold_intro": """
COLD INTRO (short, permission-based, no pitch):

"Hi [Name], this is Ruth — I know I'm calling out of the blue, can I have 20 seconds
to tell you why, and you can tell me to buzz off?

[Yes.]

I build simple AI assistants for local businesses — they answer calls, follow up with
leads, and book appointments automatically, so owners stop losing work when they're busy.
I built one for my own business in a few days.

I'm not asking you to buy anything today. I'd just love to show you a 10-minute demo and
see if it'd save you time. Fair enough?"
""",

    "follow_up_pain": """
FOLLOW-UP GAP OPENER:

"Hi [Name] — quick one. When a new customer reaches out and you can't get back to them
right away, who follows up? [Listen.]

That's the gap I close. My AI assistant follows up by text and email automatically until
they book — so leads stop slipping through the cracks. Owners tell me it's like hiring a
full-time follow-up person for a fraction of the cost. Can I show you in 10 minutes?"
""",

    "demo_close": """
BOOK-THE-DEMO CLOSE:

"Here's all I'm asking: give me 10 minutes. I'll show you exactly what it looks like when
a call comes in, gets answered, and turns into a booked job — using your business as the
example. If it's not a fit, no hard feelings. What's better for you, later this week or early next?"
""",
}

OBJECTION_KEYWORDS = {
    "busy": "too_busy",
    "time": "too_busy",
    "expensive": "too_expensive",
    "cost": "too_expensive",
    "afford": "too_expensive",
    "price": "too_expensive",
    "receptionist": "already_have_someone",
    "already have": "already_have_someone",
    "staff": "already_have_someone",
    "assistant": "already_have_someone",
    "think about it": "think_about_it",
    "not interested": "not_interested",
    "robot": "sounds_robotic",
    "impersonal": "sounds_robotic",
    "ai": "sounds_robotic",
}

OBJECTION_SCRIPTS = {
    "too_busy": """
"I hear you — and honestly, that's exactly why this helps. It runs itself. Setup is on me,
it takes a few days, and once it's on you do nothing. The whole point is to give you time
back, not take more. 10 minutes now saves you hours every week."
""",
    "too_expensive": """
"Totally fair to ask. Here's the math: most local businesses lose 20-30% of their calls,
and each missed call can be a job worth hundreds. This runs for about the cost of ONE lost
job a month. So it usually pays for itself the first week. Want me to show you the numbers
for your business?"
""",
    "already_have_someone": """
"That's great — this doesn't replace them, it backs them up. When your person is on another
call, at lunch, or it's after hours, the AI catches what would've gone to voicemail. Your
team handles the humans; the AI makes sure nothing slips at 7pm on a Saturday."
""",
    "think_about_it": """
"Of course — it's your business. Can I make it easy? Let me just show you the 10-minute demo
so you're deciding with the full picture instead of guessing. If it's still a no after that,
I'll leave you alone. Worst case you lose 10 minutes."
""",
    "not_interested": """
"No problem at all, I appreciate you being straight with me. Can I ask one thing — is it that
missed calls and follow-up aren't a pain for you, or just that now's not the time? [Listen.]
Totally get it. Mind if I check back in a month? No pressure."
""",
    "sounds_robotic": """
"Great question — the tech has come a long way. It sounds natural, it's polite, and it's
trained on YOUR business so it answers like someone who works there. And it's honest — it
tells callers it's an assistant. Let me play you a real call so you can hear it yourself."
""",
}


async def handle_objection(objection_text: str, lead_context: dict = None) -> dict:
    """AI-powered objection handling with script suggestions."""
    objection_lower = objection_text.lower()
    script_key = None
    for keyword, key in OBJECTION_KEYWORDS.items():
        if keyword in objection_lower:
            script_key = key
            break

    base_script = OBJECTION_SCRIPTS.get(script_key, "") if script_key else ""

    context_str = ""
    if lead_context:
        context_str = f"""
Prospect context:
- Name: {lead_context.get('first_name', '')} {lead_context.get('last_name', '')}
- Business: {lead_context.get('address', '')}
- City: {lead_context.get('city', '')}
- What they need: {lead_context.get('life_event', 'unknown')}
"""

    response = await think(
        f"""A small-business owner just said: "{objection_text}"
{context_str}

You are Ruth from "AI With Ruth" — you sell simple AI automation (AI phone answering,
missed-call text-back, automated follow-up, online booking) to local businesses.

Reference framework:
{base_script}

Write a warm, confident, non-pushy response that acknowledges their concern, reframes it
around time and money saved, and moves toward booking a short demo. Sound like a real
person, not a salesperson.

Format:
**Immediate Response** (what to say right now):
[Response]

**Follow-up if they push back**:
[Response]

**Proof point to reference**:
- [one concrete point — e.g. missed-call stats, "built my own in days", pays for itself]

**Close**:
[How to book the 10-minute demo]"""
    )

    return {
        "objection": objection_text,
        "script_used": script_key or "custom_ai",
        "response": response,
        "coach_framework": script_key.replace("_", " ").title() if script_key else "NOVA Custom"
    }


async def get_call_script(lead: dict, script_type: str = "auto") -> str:
    """Generate a personalized outreach script for a specific business prospect."""
    need = (lead.get("life_event") or "").lower()
    if script_type == "auto":
        if "missed" in need or "call" in need:
            script_type = "missed_call"
        elif "follow" in need:
            script_type = "follow_up"
        else:
            script_type = "cold_intro"

    script_frameworks = {
        "missed_call": SCRIPT_LIBRARY["missed_call_pain"],
        "follow_up": SCRIPT_LIBRARY["follow_up_pain"],
        "cold_intro": SCRIPT_LIBRARY["cold_intro"],
    }
    framework = script_frameworks.get(script_type, SCRIPT_LIBRARY["cold_intro"])

    return await think(
        f"""Write a complete, personalized outreach call script for this business prospect.

Prospect: {lead.get('first_name', '')} {lead.get('last_name', '')}
Business: {lead.get('address', '')} {lead.get('city', '')}
What they need: {lead.get('life_event', 'unknown')}
Fit score: {lead.get('score', 0)}/100

Script type: {script_type}
Framework:
{framework}

You are Ruth from "AI With Ruth", selling simple AI automation to local businesses.
Write a natural, word-for-word script including:
- Opening (first 10 seconds, permission-based)
- The pain question that gets them nodding
- What NOVA does, in plain English (answers calls, texts back, books jobs, follows up)
- One proof point ("I built my own in days / it pays for itself")
- Close for a 10-minute demo

Make it sound like a real, warm human — not a telemarketer. No jargon."""
    )
