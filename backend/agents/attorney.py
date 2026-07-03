"""
Compliance sub-agent — a safety check on NOVA's outputs before they go out.

Flags likely legal/compliance problems in sales & marketing content under US federal law and
general advertising rules (truth-in-advertising / FTC, CAN-SPAM for email, TCPA for texts/calls,
unsubstantiated claims, testimonial/endorsement rules). Industry-agnostic.
NOT legal advice — it's a guardrail that recommends licensed review for anything serious.
"""
import json
from agents.brain import think_structured

COMPLIANCE_PERSONA = """You are NOVA's compliance reviewer for sales & marketing content (any
industry — service businesses, agencies, local trades, SaaS, coaching, etc.). Review the text for
likely legal/advertising issues under US FEDERAL law and general marketing rules, especially:
- TRUTH IN ADVERTISING (FTC): no misleading, deceptive, or unsubstantiated claims. Flag absolute
  or unprovable claims like "guaranteed", "#1", "the best", specific ROI/results ("double your
  revenue"), "risk-free" — unless they can be backed up, and note that disclaimers may be needed.
- TESTIMONIALS / ENDORSEMENTS: results shown must be typical or clearly disclosed as not typical;
  disclose material connections (paid, affiliate, incentive).
- CAN-SPAM (email): identify the sender, include a valid physical mailing address, and a clear,
  working opt-out / unsubscribe.
- TCPA (texts/calls): require prior express consent before texting/calling; honor do-not-call and
  opt-out ("reply STOP"); no auto-dialing without consent.
- PRICING / GUARANTEES: money-back or guarantee language should state the actual terms.
- SENSITIVE / DISCRIMINATORY LANGUAGE: avoid content that targets or excludes people based on
  protected characteristics.
- EU AI ACT (effective August 2, 2026): if the content promotes SELLING or DEPLOYING an AI tool/
  service — especially to businesses that have EU customers or users — flag that the EU AI Act's
  obligations (transparency, disclosure that users are interacting with AI, risk management,
  documentation) may apply. This is a heads-up for any AI offering with EU exposure, not a US-only
  marketing rule.

You are NOT a lawyer and this is NOT legal advice — it is a safety check. Always recommend a
licensed attorney review anything flagged high severity or legally consequential."""


async def check_compliance(text: str, kind: str = "general") -> dict:
    data = await think_structured(
        f"""Review this {kind} sales/marketing content for compliance issues. Be practical — flag
real problems, not nitpicks. For each issue give a concrete fix.

CONTENT:
{text}

Return JSON:
{{
  "overall": "pass | review_recommended | needs_changes",
  "claims_ok": true,
  "issues": [
    {{"severity": "high|medium|low", "area": "Advertising Claims|Testimonials|CAN-SPAM|TCPA|Pricing/Guarantee|EU AI Act|Other",
      "issue": "what's wrong", "fix": "how to fix it", "quote": "the exact problematic phrase, if any"}}
  ],
  "cleaned_version": "an optional compliant rewrite of the content, or empty string",
  "summary": "1-2 sentence plain-English summary"
}}""",
        system_extra=COMPLIANCE_PERSONA,
        use_haiku=False,
    )
    try:
        parsed = json.loads(data)
    except Exception:
        return {"overall": "review_recommended", "claims_ok": True, "issues": [],
                "cleaned_version": "", "summary": "Could not auto-parse the review — please review manually.",
                "raw": data[:500]}
    parsed["disclaimer"] = ("Automated safety check — not legal advice. Have a licensed attorney "
                            "review anything flagged or legally consequential.")
    return parsed
