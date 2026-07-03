# ARIA — Real Estate AI Assistant — Working Notes

_Last updated: 2026-06-28 (session 6 — enrichment fix, delete/recover, FSBO, scheduled auto-hunts, distressed hunts — all DEPLOYED & live)_

## Main goal right now
✅ **DONE — Property auto-enrichment (Option A) is LIVE on Railway and verified.**
When a lead is added with an address, ARIA auto-looks up beds / baths / sqft / lot size /
year built / last sold / estimated value from public web data (Tavily → Zillow/Redfin/Realtor)
and fills the fields in — editable, with a confidence flag.

### What got fixed this session (the open bug from session 5)
- **Root cause of the "Could not parse property data" failure:** the local test ran from
  `backend/` where pydantic couldn't find the root `.env` (so `ANTHROPIC_API_KEY` was empty →
  the auth error). Once env loaded, the *real* bug surfaced: Haiku wraps its JSON in
  ```` ```json … ``` ```` markdown fences despite being told not to, so every bare
  `json.loads()` failed.
- **Fix:** added `_strip_json_fences()` in `backend/agents/brain.py` and applied it inside
  `think_structured()` — strips code fences (and stray prose) before returning. This hardens
  ALL JSON callers at once (enrich, CMA, market snapshot, expired listings).
- **Verified live:** created a lead at `1319 Lincoln Ave, San Jose, CA` on the production site
  → `property_enriched: true`, pulled the real `$1,430,800` Zestimate, returned null for specs
  not in the snippet (never invents), confidence flagged "low". DB migrate() columns all present.

### Also shipped this session (session 6, cont.) — DEPLOYED & verified live
1. **Lead delete + recover (soft delete — roadmap #11).** New columns `is_deleted` + `deleted_at`
   (+ 2 ALTER TABLE migrations). Endpoints: `DELETE /leads/{id}` (soft; `?permanent=true` for hard
   delete), `POST /leads/{id}/recover`, `GET /leads/deleted`. Active lists + daily-call-list exclude
   deleted. Frontend: 🗑 Delete button in lead modal, "🗑 Recently Deleted" view on Leads page with
   Recover / Delete Forever. The leftover "Enrich Test" lead was permanently deleted live → CRM clean.
2. **FSBO auto-leads (roadmap #3).** New `hunt_fsbo(city, state)` targeting Zillow/Redfin
   For-Sale-By-Owner, nationwide. New `fsbo` hunt type + extraction schema. `/leadgen/hunt` gained
   `state` + `auto_save` (finds AND scores+saves in one call). Frontend: "🏷️ FSBO (Zillow/Redfin)"
   option, free-text City (any US city), State field, "⚡ Auto-add found leads to CRM" checkbox.
   Verified: returned real Zillow FSBO addresses, names flagged "needs skip trace" (never invents).
3. **Fixed a latent production bug:** `frontend/static/js/app.js` had `const API =
   'http://localhost:8000'` hardcoded — every API call on the deployed site would have hit the
   user's localhost and failed. Changed to `const API = ''` (same-origin, since FastAPI serves the
   frontend). This was silently breaking the live browser UI.

### Also shipped (session 6, part 3) — scheduled auto-hunts + distressed/waterfront, DEPLOYED & live
4. **Scheduled auto-hunts (hands-off lead gen).** New `ScheduledHunt` table + `backend/agents/
   scheduler.py` — an in-process asyncio background loop (started in `main.py` startup, wakes every
   10 min) that runs due hunts, scores + auto-saves results, stamps `next_run`. Endpoints on the
   leadgen router: `GET/POST /leadgen/schedules`, `PUT/DELETE /leadgen/schedules/{id}`,
   `POST /leadgen/schedules/{id}/run` (run now). Frequencies: hourly/daily/weekly. Frontend: an
   "⏰ Scheduled Auto-Hunts" card on the Lead Generator page (schedule the current hunt, Run now /
   Pause / Delete, shows last run + total added). Verified: schedule create/list/run-now/pause all
   work; run-now found 4 + auto-saved 4. Prod log confirms "Auto-hunt scheduler: running".
   - NOTE: in-process scheduler (no separate Railway cron) because the web service is always on.
     Survives redeploys via `next_run` persisted in the DB.
5. **Distressed hunts (roadmap #10).** `lead_generator.py` → `hunt_distressed` (pre-foreclosure/
   probate/tax-delinquent/vacant/inherited) with a new extraction schema, registered in
   `generate_leads`. `distress_type` → `life_event` on save (the scorer rewards it — a pre-foreclosure
   lead scored **78**). Frontend dropdown gained "⚠️ Distressed / Motivated (Batchleads)".
   _(NOTE: a waterfront hunt was briefly added then removed — Ruth clarified #10 is distressed homes
   only, not waterfront.)_
   - `research.py` → `search_market` now takes a `domains` override (`[]` = whole web). Distressed
     uses `DISTRESSED_DOMAINS` (auction.com/foreclosure.com/realtytrac…) with a whole-web fallback,
     because foreclosure data isn't on the standard portals (that's why the first test found 0).
6. **Batchleads inbound mapping enhanced.** `INBOUND_FIELD_MAP` now maps Batchleads distress fields
   (`foreclosure_status`, `pre_foreclosure`, `lead_type`, `tag`, `vacant`, equity aliases) →
   `life_event`/`is_absentee`/`equity_estimate`. Verified: an inbound pre-foreclosure+absentee+equity
   lead scored 68. This is the VERIFIED distressed path (Batchleads → Zapier → `/leadgen/inbound`);
   the free Tavily distressed hunt is best-effort public signals.

### Dev convenience added
- `run_local.py` (repo root) — loads root `.env` + serves the full app on `127.0.0.1:8099`.
  Registered in `~/.claude/launch.json` as `aria-local` for the preview tooling.

### "bachelors" clarified
- Ruth meant **Batchleads** (batchleads.io, already paid for). Roadmap #10 distressed-property
  hunts should pull from Batchleads (via the existing Zapier → `/leadgen/inbound` webhook, or a
  future direct provider integration). [[project_n8n_upwork]]

This is part of the larger v2 enhancement push (luxury UI + 15-item roadmap).

## Session 6 part 17 — removed "How ARIA Works" page from the app (IP protection)
- Ruth's call: don't expose ARIA's architecture in the live app (demo copy risk). Removed nav +
  `page-howitworks` + extraPages entry. Architecture kept PRIVATE in Notion + the skill only.
  Don't re-add an architecture page to the app. (`/docs` still exists but is behind login.)

## Session 6 part 16 — Coach + Attorney/Compliance sub-agents (DEPLOYED & live)
- **Coach** (`agents/coach.py` + `routers/coach.py`): ARIA coaches Ruth — `/coach/ask`,
  `/coach/next-move/{id}`, `/coach/prompts`. "🎓 Coach Me" page + lead-modal button. (Internal
  coaching — NOT the sellable coaching product.)
- **Attorney/Compliance** (`agents/attorney.py` + `routers/compliance.py`): `/compliance/check`
  flags Fair Housing / disclosure / advertising / CAN-SPAM / TCPA + fixes + rewrite. "⚖️ Compliance
  Check" page. Not legal advice. (Last roadmap sub-agent — now built.)
- ARIA now = 11 AI + 3 automation = 14 sub-agents. Updated How ARIA Works diagram.
- TOMORROW (Ruth): connect accounts — Batchleads, Dropbox/SkySlope, DocuSign.

## Session 6 part 15 — saved smart lists (DEPLOYED & live)
- All Leads "💾 Save View": save search/temp/stage as named views (localStorage); chips apply/delete.

## Session 6 part 14 — transaction checklist (DEPLOYED & live)
- `ChecklistItem` table + listing routes (seed 12 milestones, toggle, add, delete). "📋 Checklist"
  button on each listing → modal with progress bar.

## Session 6 part 13 — bulk lead actions (DEPLOYED & live)
- `POST /leads/bulk` (delete/assign/temperature/stage). Leads table checkboxes + select-all + bulk bar.

## Session 6 part 12 — message templates (DEPLOYED & live)
- `routers/templates.py` + `MessageTemplate` table: built-in + custom email/text templates;
  `/templates/render` fills merge fields from a lead. "📧 Templates" page (use/create/delete).

## Session 6 part 11 — "How ARIA Works" page (DEPLOYED & live)
- New "🧩 How ARIA Works" nav page (Command Center): in-theme diagram of Dashboard → Brain → 9 AI
  sub-agents + 3 automation sub-agents → Data & Services + 5-step flow. Static (extraPages).
- Terminology: agents under ARIA = "sub-agents" (12 total: 9 AI + 3 automation). Code in
  backend/agents/; live API explorer at /docs.

## Session 6 part 10 — daily KPI tracker (DEPLOYED & live)
- `GET /leads/kpis` (today/week/month: calls, contacts, leads, appointments; Pacific-time days via
  zoneinfo + tzdata in requirements). Dashboard "📈 Daily KPIs" card w/ editable goals (localStorage)
  + progress bars.

## Session 6 part 9 — Transaction Forms auto-fill (DEPLOYED & live)
- `routers/forms.py`: `/forms/catalog` + `/forms/prepare` fill lead/listing + agent data into 7 CA
  agent forms (RLA/RPA/AD/TDS/AVID/SPQ/Net Sheet). "📝 Transaction Forms" page: pick lead → prepare → copy.
- Compliance: ARIA preps DRAFT field data only (no C.A.R. form reproduction); transfer to zipForms/
  DocuSign. Data tiers — ARIA: contact PII (name/addr/email/phone). Glide: signed compliance docs.
  DocuSign: e-sign. Title co: SSN/wiring/financials. NEVER put SSN/financials in ARIA.

## Session 6 part 8 — lead search, temp filter, CSV export (DEPLOYED & live)
- All Leads page: search box + temperature filter + Export CSV (client-side over loaded leads).

## Session 6 part 7 — manager overview + activity timeline (DEPLOYED & live)
- **Manager Overview** — `GET /team/overview` (team totals + per-member counts by temp/stage +
  unassigned). Card at top of Team page.
- **Lead activity timeline** — `GET /leads/{id}/touchpoints`; "🕑 Activity" section in lead modal
  with history + one-line quick-log.

## Session 6 part 6 — Today dashboard, team, integrations, vault filtering (DEPLOYED & live)
- **Today panel** — `GET /leads/today` (followups due / hot / new + counts); panel on Dashboard.
- **Team / multi-user foundation** — `TeamMember` table + `routers/team.py` (CRUD, roles).
  `Lead.assigned_to` (+migrate) + `PUT /leads/{id}/assign`; member delete unassigns leads.
  Frontend: "👔 Team" page + "Assign" picker in lead modal.
- **Integrations hub** — `routers/integrations.py` (`GET /integrations/`) groups all connectors with
  connected status; config keys for docusign/mls/zipforms/disclosures. Frontend "🔌 Integrations" page.
- **Document Vault filtering** — `GET /documents/?category=` + `/documents/summary`; filter + count UI.
- BUG fixed: unescaped apostrophe in a single-quoted JS string broke the whole inline `<script>` block
  (all inline functions undefined). Rephrased. Lesson: avoid apostrophes in single-quoted JS strings;
  verify `typeof fn` in preview after big inline-script edits.

## Session 6 part 5 — scripts, document vault, fonts, domain (DEPLOYED & live)
- **Bigger main-content fonts** — override block at end of `style.css` (body 17px etc.).
- **Scripts upload/delete** — `routers/scripts.py` + `Script` table. Built-ins read-only; custom
  scripts DB-backed + deletable. Endpoints: GET/POST `/scripts/`, POST `/scripts/upload`,
  DELETE `/scripts/{id}`. Frontend "📂 My Scripts" card.
- **Document Vault (3-yr compliance)** — `routers/documents.py` + `Document` table. Upload/list/
  download/delete; `retain_until = now + 3yr`; delete blocked in retention window unless `?force=true`.
  Stored on persistent volume (`get_docs_dir()` → `/data/documents` on Railway). `/documents/integrations`
  reports Dropbox/SkySlope/Glide status (stubbed). Frontend "🗄️ Document Vault" card. `.gitignore`
  broadened to `data/` so client docs never hit GitHub. Verified live (volume write/read/delete).
- **Custom domain — ✅ LIVE: https://aria.divinerealtyteam.com** (SSL issued, verified).
  DNS at GoDaddy: CNAME `aria` → `wk2rsnbj.up.railway.app` + TXT `_railway-verify.aria`.
  `PUBLIC_BASE_URL` updated to the new domain (applies on next deploy). Old Railway URL still works.

## Backups & version control (set up 2026-06-28)
- Git repo backed up to a PRIVATE GitHub repo: https://github.com/ruthsmith2009-boop/aria-re
  (remote `origin`, branch `main`). gh CLI installed + authed; `gh auth setup-git` done so plain
  `git push`/`git fetch` work.
- `.env` and other secrets stay local (gitignored, verified not on GitHub).
- Save routine: every session → push to GitHub + update Claude skill + update Notion. "commit first"
  = on-demand snapshot before a big task.

## Live deployment
- Host: Railway (project `aria-re`), builder = railpack, Python pinned to 3.12 via `.python-version`.
- Login wall: HTTP Basic Auth middleware in `main.py`. Public paths: `/health`,
  `/calling/webhook`, `/leadgen/inbound`.
- DB: SQLite on a Railway persistent volume. `create_all()` only makes new TABLES, not new
  COLUMNS — so new columns are added via idempotent `migrate()` ALTER TABLE statements at startup.

## Files changed / created this session

### Backend
- `backend/database.py` — Lead model gained: `temperature` (default "cold"),
  `follow_up_cadence`, `state`, and property fields `bedrooms` (Int), `bathrooms` (Float),
  `sqft` (Int), `lot_size` (String), `year_built` (Int), `last_sold_price` (Float),
  `last_sold_date` (String), `estimated_value` (Float), `property_enriched` (Bool, default False),
  `enrichment_confidence` (String). Added 13 ALTER TABLE statements to `migrate()` (idempotent,
  try/except per statement), called by `create_tables()`.
- `backend/agents/research.py` — Added `HOME_MARKET_TERMS` + `_is_home_market()`; `run_cma()`
  takes `state`, returns 3 separate comp sets (zillow/redfin/mls) + `source_estimates`; injects
  Santa Clara knowledge only for home-market properties. **NEW: `enrich_property(address, city,
  state)`** — Tavily search + `think_structured` (Haiku) extraction with strict "never invent"
  rules; returns specs + `enrichment_confidence`.
- `backend/agents/brain.py` — SYSTEM_PERSONA rewritten (home base San Jose & SCC; research/CMA
  anywhere in US, adapt to local law).
- `backend/agents/lead_scorer.py` — `CADENCE_DAYS`, `CADENCE_LABELS`,
  `compute_next_followup(cadence)`, `suggest_temperature(score)`.
- `backend/agents/lead_generator.py` — Tavily hunts, `ingest_inbound_lead()`,
  `available_providers()`, `_apply_score()` helper (falls back to base score, not 0).
- `backend/agents/finance.py` — Finance agent (CATEGORIES, ARIA_STACK, summarize,
  ai_categorize, monthly_report).
- `backend/routers/leads.py` — import `enrich_property` + `PROP_FIELDS` tuple; `LeadCreate`
  gained `state`; `create_lead` auto-enriches after scoring; NEW endpoints
  `POST /leads/{id}/enrich`, `PUT /leads/{id}/cadence`, `PUT /leads/{id}/temperature`,
  `GET /leads/cadences`; `_serialize_lead` returns state + all property fields.
- `backend/routers/market.py` — `CMARequest` gained `state`; passed into `run_cma`.
- `backend/config.py` — vapi_*, twilio_*, public_base_url, redx/batchleads/propstream keys,
  leadgen_webhook_token, aria_username/aria_password; `primary_market` = "San Jose & Santa
  Clara County, CA — Bay Area (serves all US markets)".
- `backend/main.py` — Basic Auth middleware; routers wired (leads, market, listings, marketing,
  calendar, social, calling, leadgen, finance).

### Frontend
- `frontend/index.html` — Google Fonts (Cormorant Garamond + Inter); nav items (Lead Generator,
  AI Calling, Finance & Costs); tagline "San Jose · Bay Area · Nationwide"; market-area free-text
  + datalist; CMA + Add Lead forms gained State field + auto-lookup note.
- `frontend/static/css/style.css` — Luxury palette (navy `#0b1c30`, champagne gold `#c5a572`,
  cream `#faf8f3`, gold/navy gradients); serif headings; body 16px; **enlarged left sidebar**
  (nav-item 18px, icons 22px, section labels 12.5px gold).
- `frontend/static/js/app.js` — `tempBadge()`, `CADENCE_OPTIONS`, `setLeadTemp()`,
  `setLeadCadence()`, `enrichLead()`, `compRows()`; lead detail modal shows temperature buttons,
  cadence dropdown, and a Property Details card with "🔄 Auto-fill from address" button; Add Lead
  form sends state; CMA renders 3 comp sources.

## Decisions made & why
- **Auto-enrich = Option A** (auto-fill on save, editable) — Ruth wants property specs populated
  from just the address, but knows web data is approximate; MLS connection later gives exact data.
- **Never-invent rule** in enrichment prompt — public data can be wrong, so unmatched fields
  return null and confidence drops to "low" rather than guessing.
- **San Jose as home base, search open to all US** — Ruth asked for both: San Jose identity
  everywhere AND nationwide search. Home-market knowledge only injected when address is local.
- **Python 3.12 pin** — pandas 2.2.2 has no 3.13 wheel; 3.13 tried to compile from source and
  failed (no compiler in Railway build image).
- **migrate() ALTER TABLE** — needed because create_all won't add columns to existing live tables.
- **Provider = BatchLeads (batchleads.io) via Zapier** — Ruth already pays for it (not BatchData).
- **Twilio $20 to start** — Ruth isn't actively calling yet.

## Open bugs / not fixed
- ~~Enrich local test failed / not deployed~~ — FIXED + deployed (session 6, see top).
- ~~No lead delete endpoint~~ — DONE (soft delete + recover, session 6).
- ~~API base hardcoded to localhost:8000~~ — FIXED (same-origin, session 6).
- Twilio A2P 10DLC / 408 campaign approval still pending (~2 days).
- Vapi + Zapier webhooks still need to be pointed at the live Railway URL.
- **FSBO "auto" is one-click, not scheduled.** True hands-off auto-leads would need a scheduled
  job (Railway cron) to run hunts on a cadence — future enhancement.

## Next steps
1. **Open question for Ruth:** enlarge **main content** fonts (cards/tables/buttons), not just the
   sidebar? (sidebar was already enlarged in session 5.)
2. **Set up Batchleads in Zapier** for the verified distressed pipeline: build distressed lists in
   Batchleads → Zapier "Webhooks by Zapier" POST to
   `https://aria-re-production.up.railway.app/leadgen/inbound?token=<LEADGEN_WEBHOOK_TOKEN>`.
   Map foreclosure_status / equity / absentee fields (mapping already supports them).
3. Remaining v2 roadmap: #5 integrations (DocuSign/Disclosure.io/Glide/MLS/zipForms),
   #12 teams/multi-user/manager, #13 doc upload + routing, #14 best-of CRM features
   (Lofty/Follow Up Boss). Done this session: #3 FSBO ✅, #10 distressed/waterfront ✅,
   #11 recover-deleted ✅, plus scheduled auto-hunts ✅.
4. Future: custom domain `aria.divinerealtyteam.com`.

---

## 2026-06-29 — Dashboard de-clutter + luxe redesign

- Removed the "(This is ARIA coaching you…)" parenthetical from the Coach page intro. Deployed.
- Dashboard was cluttered (KPIs + Today + stats + pipeline + quick actions all stacked open).
  Reworked into collapsible `<details>` panels (`.panel`/`summary`/`.panel-body` in style.css) —
  native, no JS. ☀️ Today open by default; 📈 Daily KPIs / 📊 Snapshot / 🪜 Pipeline / ⚡ Quick Actions
  collapsed until clicked. Gold chevron rotates on open.
- Luxe look: `.main` now a deep ink-navy radial gradient (`--canvas`); ivory panels/cards float with
  soft shadow; navy topbar with gold-gradient title. No more white/cream "paper" feel.
- `loadToday()` / `loadKPIs()` lost their inner `.card` wrappers (panel is the container now).
- Files: frontend/index.html (dashboard markup + the two render fns), frontend/static/css/style.css.
- Verified in local preview (5 panels, only Today open, no console errors), then deployed to Railway.

---

## 2026-06-29 (cont.) — Batchleads → ARIA connection attempt (BLOCKED on Batchleads' side)

Goal: auto-flow Batchleads leads into ARIA, free, no manual import.

ARIA side DONE + deployed:
- Added path-token inbound webhook: `POST /leadgen/inbound/{token}` (GET/HEAD return 200 "ready"
  for validation pings; POST ingests). Reason: BatchLeads' webhook URL field rejects any URL with
  a "?", so `/leadgen/inbound?token=` wouldn't save. New no-`?` URL:
  `https://aria-re-production.up.railway.app/leadgen/inbound/<LEADGEN_WEBHOOK_TOKEN>`.
  `/leadgen/inbound/info` now advertises both URLs. Tested end-to-end locally (created:1). Live.

Batchleads blockers (all on THEIR end):
1. Native "Push to CRM" webhook — only fires from the **Inbox** (messaging add-on). Ruth's plan has
   no Inbox; "Export to" only offers Excel + Podio. So the saved webhook ("Aria") can't be triggered.
2. Zapier — their app is in **private beta**, the public version points to a **dead domain**
   (`app.batchleadstacker.com` → getaddrinfo ENOTFOUND), and the invite link is **EXPIRED**
   ("invited by support@getbatch.co"). Got as far as: Zap trigger = "Property Added to a List",
   connect via the "Zapier Api Key" (5514ef…) → fails on the dead domain.

NEXT (waiting on Ruth → Batchleads support@getbatch.co): emailed them for (a) a working Zapier
invite link, (b) whether her plan has REST API access + how to get an API key (docs:
developer.batchservice.com — can retrieve saved properties/lists/statuses/contacts).
- If working Zapier invite → finish the Zap (trigger → Webhooks by Zapier POST to the inbound URL).
- If API access → BUILD an ARIA→Batchleads auto-pull connector on the existing scheduler (pull
  saved properties from a chosen list/status, ingest via existing INBOUND_FIELD_MAP). No Zapier needed.
- Interim option offered (Ruth declined manual workflow): one-time Batchleads Export→Excel → ARIA Upload.

Also this session: dashboard redesigned into collapsible <details> panels on a luxe navy canvas
(see entry above); Coach page disclaimer line removed.

### Batchleads support reply (2026-06-29) — API ruled out, Zapier still the path
- **API: NO.** BatchLeads has no data API (SMS-only). Programmatic lead-pull = their separate PAID
  product **BatchData**. So ARIA auto-pull connector is NOT buildable on Ruth's current plan.
- **Zapier:** support asked "what CRM?" → clarified CRM is a custom app (use "Webhooks by Zapier"
  POST as the action); the real blocker is the **BatchLeads trigger** failing to connect
  (`app.batchleadstacker.com` ENOTFOUND). Asked them for a working invite link to their Zapier app.
- Fallbacks if they can't fix Zapier: subscribe to BatchData (paid) → build auto-pull, or manual CSV.

---

## 2026-06-29 (cont.) — Follow-up automation engine + demo readiness

New feature (built, tested end-to-end locally, deployed):
- **Auto-schedule next follow-up**: logging a call/text/email/meeting touchpoint now auto-sets the
  lead's `next_follow_up` from its cadence (or a temperature default). `note` touches don't reschedule.
  Backend: `add_touchpoint` in routers/leads.py; `default_cadence_for_temperature` + new cadences
  `every_2_day`/`every_3_day` in agents/lead_scorer.py.
- **GET /leads/followups?days=N** — overdue + upcoming queue (static route, before /{lead_id}).
- **POST /leads/{id}/draft-followup?channel=auto** — AI drafts a channel-aware (text/email/call) next
  message via brain.think, aware of stage + last touchpoints. Frontend: "✍️ Draft" button on the Today
  panel → modal with Copy.
- **Demo data**: POST /leads/seed-demo (8 realistic sample leads, source="demo", varied temp/stage/
  next_follow_up) + DELETE /leads/demo. Frontend "✨ Load Demo" / "Clear Demo" buttons on Leads page.
- **Cache-busting**: app.js/style.css now `?v=20260629` so deploys always load fresh JS/CSS
  (fixes browsers hard-caching app.js — was making new functions look "undefined").

Demo tomorrow: click "✨ Load Demo" on the Leads page before the demo → dashboard/pipeline/Today/
call-list all populate; show Today follow-ups → ✍️ Draft (AI message) and Log (auto-schedules next);
Coach Me, Lead Generator, scoring. "Clear Demo" after.

Known minor: dashboard alert banner "N leads need follow-up today" can differ from the Today tile
count by a bit (client parses naive-UTC datetimes as local). Cosmetic; the Today tile is authoritative.

### Count fix + dry-run (2026-06-29, later)
- Dashboard banner now uses server `/leads/today` count (matches Today tile; naive-UTC mismatch fixed).
- Full 19-page click-through dry-run with demo data: every page renders, zero console errors. Deployed + healthy.
