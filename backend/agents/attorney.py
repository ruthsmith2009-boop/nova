"""
Attorney / Compliance sub-agent — a safety check on ARIA's outputs before they go out.

Flags likely legal/compliance problems in real-estate content under California + US federal law
(Fair Housing, required disclosures, advertising rules, CAN-SPAM, TCPA, DRE license display).
NOT legal advice — it's a guardrail that recommends licensed review for anything serious.
"""
import json
from agents.brain import think_structured

COMPLIANCE_PERSONA = """You are ARIA's compliance reviewer for real-estate content. Review the text
for likely legal/compliance issues under CALIFORNIA and US FEDERAL law, especially:
- FAIR HOUSING: no language that discriminates, steers, or expresses preference/limitation based on
  protected classes (race, color, religion, sex, familial status, national origin, disability, plus
  CA classes: marital status, sexual orientation, gender identity, source of income, age, ancestry,
  genetic info). Flag phrases like "perfect for families", "safe neighborhood", "exclusive", etc.
- REQUIRED DISCLOSURES: agency relationship, material facts, known defects (for CA listings/TDS).
- ADVERTISING: DRE license # + broker identification on marketing; no misleading/unsubstantiated
  claims ("guaranteed", "#1", specific ROI) without basis.
- CAN-SPAM (email): identify sender, valid physical address, clear opt-out.
- TCPA (texts/calls): prior express consent; honor do-not-call.

You are NOT a lawyer and this is NOT legal advice — it is a safety check. Always recommend a licensed
attorney/broker review anything flagged high severity or legally consequential."""


async def check_compliance(text: str, kind: str = "general") -> dict:
    data = await think_structured(
        f"""Review this {kind} real-estate content for compliance issues. Be practical — flag real
problems, not nitpicks. For each issue give a concrete fix.

CONTENT:
{text}

Return JSON:
{{
  "overall": "pass | review_recommended | needs_changes",
  "fair_housing_ok": true,
  "issues": [
    {{"severity": "high|medium|low", "area": "Fair Housing|Disclosure|Advertising|CAN-SPAM|TCPA|Other",
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
        return {"overall": "review_recommended", "fair_housing_ok": True, "issues": [],
                "cleaned_version": "", "summary": "Could not auto-parse the review — please review manually.",
                "raw": data[:500]}
    parsed["disclaimer"] = ("Automated safety check — not legal advice. Have a licensed attorney or "
                            "your broker review anything flagged or legally consequential.")
    return parsed
