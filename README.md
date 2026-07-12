# NOVA — AI Assistant for Small Business

An AI sales assistant + CRM for any small business that runs on leads: it answers
calls, texts back missed callers, follows up automatically, and books jobs.

Built with **FastAPI + SQLite + Claude** (Anthropic). One deployable app: the
backend serves the API and the dashboard frontend together.

---

## What NOVA Does

| Feature | Status |
|---|---|
| AI phone answering + outbound AI calling (Vapi + Twilio) | ✅ |
| Missed-call text-back and auto follow-up sequences | ✅ |
| Lead scoring with AI reasoning + daily ranked call list | ✅ |
| Full CRM pipeline (New → Contacted → Appt Booked → Proposal → Closing → Won) | ✅ |
| Hands-off lead hunting on a schedule (auto-hunt) | ✅ |
| CSV/Excel lead import + auto-scoring | ✅ |
| Call scripts + objection coaching for the owner | ✅ |
| Email sending via SendGrid (with approval workflow) | ✅ |
| Social post generator (Instagram, Facebook, LinkedIn, X) | ✅ |
| Google Calendar booking | ✅ |
| Expense tracking + monthly finance report | ✅ |
| Hot-lead email alerts from calls | ✅ |
| Login wall for the deployed app (HTTP Basic) | ✅ |

---

## Quick Start (local)

```bash
cd ~/nova
pip install -r requirements.txt      # or use your existing venv
cp .env.example .env                 # then fill in your keys
python run_local.py
```

Open **http://127.0.0.1:8098** — API docs at **http://127.0.0.1:8098/docs**.

### Required keys (in `.env`)

```
ANTHROPIC_API_KEY=sk-ant-...      ← Required (Claude AI)
TAVILY_API_KEY=tvly-...           ← Recommended (live web research / lead hunting)
SENDGRID_API_KEY=SG....           ← Optional (email sending)
```

See **`.env.example`** for the full list — identity/branding (BUSINESS_NAME,
AGENT_NAME, AGENT_EMAIL...), login wall (APP_USERNAME / APP_PASSWORD), AI
calling (VAPI_* / TWILIO_* / VAPI_WEBHOOK_SECRET), and DATABASE_URL.

---

## AI Calling Setup (Vapi + Twilio)

1. **Vapi** (voice AI brain) — sign up at **vapi.ai**, copy your API key + phone number ID
2. **Twilio** (phone line) — sign up at **twilio.com**, buy a local number, register A2P 10DLC. You can connect Twilio to Vapi directly inside the Vapi dashboard (simplest path).
3. Add to `.env`: `VAPI_API_KEY`, `VAPI_PHONE_NUMBER_ID`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
4. Set **`VAPI_WEBHOOK_SECRET`** in `.env` and the matching "Server URL Secret" in Vapi so only Vapi can post call results to `/calling/webhook`.
5. For call results to sync back, Vapi needs a public webhook URL. Locally run `ngrok http 8098` and set `PUBLIC_BASE_URL`; on Railway it's auto-detected.
6. In the app: **AI Calling → New Campaign** → describe your goal → NOVA writes the script → **Start**.

---

## Deploying (Railway)

1. Create a Railway project from this repo (`Procfile` included).
2. Add a **volume** mounted at `/data` and set `DATABASE_URL=sqlite:////data/nova.db` so the database survives redeploys.
3. Set all env vars from `.env.example` — especially `APP_USERNAME` / `APP_PASSWORD` (login wall) and `VAPI_WEBHOOK_SECRET`.
4. `PUBLIC_BASE_URL` is derived automatically from `RAILWAY_PUBLIC_DOMAIN`.

Cloning NOVA for a new client? Follow **`docs/CLONE_CHECKLIST.md`**.

---

## How the AI Works

| Task | Model | Why |
|---|---|---|
| Coaching, scripts, objection handling | Claude Sonnet | Needs nuance |
| Marketing + email copy | Claude Sonnet | Creative, client-facing |
| Lead scoring analysis | Claude Haiku | Fast + cheap for data tasks |
| Web research parsing | Claude Haiku | Volume processing |
| Live web search | Tavily API | Real-time business data |

---

## File Structure

```
nova/
├── backend/
│   ├── main.py              ← FastAPI app entry point (+ login wall)
│   ├── database.py          ← All database models
│   ├── config.py            ← Settings (reads .env)
│   ├── agents/              ← AI engines (brain, calling, coach, leads, finance...)
│   └── routers/             ← API endpoints (leads, calling, calendar, finance...)
├── frontend/
│   ├── index.html           ← Full dashboard UI
│   └── static/              ← css/style.css (theme) + js/app.js (logic)
├── docs/CLONE_CHECKLIST.md  ← How to clone NOVA for a new client
├── run_local.py             ← Local dev server on port 8098
├── .env.example             ← Every env key, documented
├── Procfile                 ← Railway start command
└── requirements.txt
```

---

## Key Workflows

### Daily Routine
1. Open NOVA → **Daily Call List** — ranked leads ready to call
2. Click **Get Script** on any lead for a personalized word-for-word script
3. Prospect pushes back → **Coach Me** for instant objection help
4. Log the call → pipeline stage updates automatically
5. **Schedule Follow-up** → goes straight to Google Calendar

### Lead Import
1. **Import Leads** → drag & drop your CSV/Excel
2. NOVA scores every lead 0–100 instantly
3. Ranked call list updates automatically

### Hands-Off Lead Hunting
1. **Lead Finder** → save a hunt (what, where, how often)
2. The built-in scheduler runs it on cadence and saves scored leads into the CRM

---

## Cost Estimate

| Usage | Monthly Cost |
|---|---|
| 50 lead scorings/day | ~$8/mo (Haiku) |
| AI coaching + scripts | ~$10–15/mo (Sonnet) |
| Daily web research | ~$6/mo (Tavily) |
| AI calling | Vapi + Twilio usage-based |
| **Total estimate** | **~$25–50/mo + calling minutes** |
