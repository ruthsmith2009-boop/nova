# NOVA — AI Prompt Library

Every place NOVA talks to Claude. Edit the file listed to change how that feature behaves.
All prompts are **universal sales** now — none assume real estate. If any output ever drifts back
toward real estate, the first two entries below are almost always the cause.

> IP note: these are Ruth's private prompts. Keep them out of demo videos and public posts
> (per the "protect IP / demo the product, not the builder" rule).

---

## Core (injected into EVERY AI response)
| What | File | Symbol | Does |
|---|---|---|---|
| System persona | `backend/agents/brain.py` | `SYSTEM_PERSONA` | Casts NOVA as a top salesperson for any industry (was "top listing agent"). Prepended to every `think()` call. |
| Knowledge base | `backend/agents/brain.py` | `BUSINESS_KNOWLEDGE` | Universal sales playbook: speed-to-lead, follow-up cadence, BANT qualifying, permission openers. Injected into coach, social, calling, marketing, lead-gen. (Was `SANTA_CLARA_KNOWLEDGE`.) |

## Feature prompts
| Feature | File | Symbol / function | Does |
|---|---|---|---|
| Coach persona | `backend/agents/coach.py` | `COACH_PERSONA` | Universal sales mentor (Voss / Blount / Sandler / Mulrenin). |
| Coach quick prompts | `backend/agents/coach.py` | `QUICK_PROMPTS` | The suggested-question chips on the Coach page. |
| Compliance checker | `backend/agents/attorney.py` | `COMPLIANCE_PERSONA` + `check_compliance()` | Reviews ads/emails/texts for FTC claims, testimonials, CAN-SPAM, TCPA, **EU AI Act** (flags AI offerings with EU exposure). |
| Lead scoring (AI) | `backend/agents/lead_scorer.py` | `ai_enhance_score()` | Scores a lead as a prospective buyer (need, reachability, decision-maker, warmth). Industry-agnostic. |
| Call scripts | `backend/agents/scripts.py` | `SCRIPT_LIBRARY` | Reverse Selling (Brandon Mulrenin), Missed-Call opener, Cold Intro, Follow-Up, Demo Close. |
| Objection handling | `backend/agents/scripts.py` | `OBJECTION_SCRIPTS` + `handle_objection()` | Responses to too busy / too expensive / already have someone / think about it / not interested / sounds robotic. |
| AI call assistant | `backend/agents/calling.py` | `build_assistant_script()` | Turns a plain-English goal into a Vapi phone-assistant config. Default industry = "small business". |
| Newsletter | `backend/agents/marketing.py` | `write_weekly_newsletter()` | Value newsletter on any topic the owner types. |
| Email sequences | `backend/agents/marketing.py` | `write_email_sequence()` | Nurture series: new_lead / post_meeting / active_deal / proposal_sent / won. |
| Offer / proposal copy | `backend/agents/marketing.py` | `write_mls_description()`, `write_listing_presentation()` | Generic offer descriptions + full sales proposals (names kept for import compatibility; content is universal). |
| Social post suite | `backend/agents/social.py` | `generate_post_suite()` | One brief → posts for IG/FB/LinkedIn/X/YouTube/TikTok/Google Business. Types: new_offer, customer_win, promo, industry_update, tip, spotlight, testimonial, custom. |
| Video scripts | `backend/agents/social.py` | `generate_video_script()` | Full YouTube/TikTok scripts for any industry. |
| Follow-up drafts | `backend/routers/leads.py` | `draft_followup` prompt | Drafts the next text/email/call opener from the owner to a lead. |
| Lead extraction | `backend/agents/lead_generator.py` | `_extract_leads()` | Pulls REAL business prospects from web-search results; never fabricates contacts. |
| Profile parse | `backend/agents/profile_research.py` | `parse_profile()` | Pulls clean structured fields out of a pasted LinkedIn/About/directory profile; never invents a field. |
| Prospect outreach | `backend/agents/profile_research.py` | `write_outreach()` | Writes a LinkedIn connection note + DM + cold email in the owner's voice, leading with the prospect's problem. No em-dashes, no buzzwords. |

## Rules baked into the prompts
- Every generative prompt says **"never assume real estate"** and adapts to the owner's actual industry.
- The lead extractor is told to **never invent** names/phones/emails; missing contact → `needs_research`.
- Compliance is explicitly **"a safety check, not legal advice."**

## How to tune a prompt
1. Edit the symbol in the file above.
2. Test locally (`python run_local.py`, hit the feature).
3. Commit + push + `railway up --detach --service nova` (see `docs/SOP.md`).
