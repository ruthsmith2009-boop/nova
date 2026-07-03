# ARIA — AI Real Estate Agent
### Santa Clara County Listing Agent AI System

Built for Ruth Smith | Fully autonomous AI listing agent powered by Claude Sonnet + Tavily.

---

## What ARIA Does

| Feature | Status |
|---|---|
| Live market data (Zillow, Redfin, Realtor.com via Tavily) | ✅ |
| Automated CMA with comps + net sheet | ✅ |
| Lead scoring (equity, DOM, life events, expired listings) | ✅ |
| Daily ranked call list with AI reasoning | ✅ |
| Objection handling (Mike Ferry, Tom Ferry, Brian Buffini, Brandon Mulrenin) | ✅ |
| Personalized call scripts per lead | ✅ |
| CSV/Excel lead import + auto-scoring | ✅ |
| California documents: RLA, TDS, Net Sheet (draft PDFs) | ✅ |
| MLS listing description writer | ✅ |
| Social media post generator (Instagram, Facebook, LinkedIn, Twitter) | ✅ |
| Weekly neighborhood newsletter | ✅ |
| Email sequence generator (5 sequences × 5 stages) | ✅ |
| Email sending via SendGrid (with approval workflow) | ✅ |
| Google Calendar integration | ✅ |
| Full CRM pipeline view | ✅ |
| Built-in Scripts & Objections library | ✅ |
| AI outbound calling (Vapi + Twilio) | ✅ |
| Calling campaigns: start / pause / stop | ✅ |
| Duplicate-number checking | ✅ |
| Call-window control + max attempts | ✅ |
| AI call-script generation per campaign | ✅ |
| Call results → CRM pipeline + auto follow-up | ✅ |
| Hot-lead email alerts from calls | ✅ |

---

## Quick Start

### Step 1 — Install
```bash
cd ~/aria-re
chmod +x setup.sh
./setup.sh
```

### Step 2 — Add API Keys
Edit the `.env` file:
```
ANTHROPIC_API_KEY=sk-ant-...      ← Required (Claude AI)
TAVILY_API_KEY=tvly-...           ← Required (live market data)
SENDGRID_API_KEY=SG....           ← Optional (email sending)
```

Get keys:
- **Anthropic**: https://console.anthropic.com → API Keys
- **Tavily**: https://tavily.com → Sign up free
- **SendGrid**: https://sendgrid.com → Free tier (100 emails/day)

### Step 3 — Fill in Your Info
In `.env`, update:
```
AGENT_NAME=Ruth Smith
AGENT_LICENSE=your DRE number
BROKER_NAME=Your Brokerage Name
AGENT_PHONE=(408) 555-0100
AGENT_EMAIL=ruthsmith2009@gmail.com
```

### Step 4 — Start the App
```bash
cd ~/aria-re
source venv/bin/activate
cd backend
uvicorn main:app --reload --port 8000
```

Open your browser: **http://localhost:8000**

API documentation: **http://localhost:8000/docs**

---

## AI Calling Setup (Vapi + Twilio)

ARIA places real outbound AI calls. The setup:

1. **Vapi** (voice AI brain) — sign up at **vapi.ai**, copy your API key + phone number ID
2. **Twilio** (phone line) — sign up at **twilio.com**, buy a local 408 number, register A2P 10DLC to avoid spam flags. You can connect Twilio to Vapi directly inside the Vapi dashboard (simplest path).
3. Add to `.env`:
   ```
   VAPI_API_KEY=...
   VAPI_PHONE_NUMBER_ID=...
   TWILIO_ACCOUNT_SID=...
   TWILIO_AUTH_TOKEN=...
   TWILIO_PHONE_NUMBER=+1408...
   PUBLIC_BASE_URL=https://your-ngrok-url.ngrok.io
   ```
4. For call results to sync back automatically, Vapi needs a public webhook URL. For local testing run `ngrok http 8000` and set `PUBLIC_BASE_URL` to the ngrok URL.
5. In the app: **AI Calling → New Campaign** → describe your goal → ARIA writes the script → **Start**. Results land in **Call Results** and update the CRM automatically.

Pipeline dispositions: New, Called, Interested, Not Interested, Follow-up Required, Decision Maker Needed, Mgmt Not Available, Custom Plan Requested, Appointment/Callback, Closed.

---

## Google Calendar Setup (Optional)

1. Go to https://console.cloud.google.com
2. Create a project → Enable "Google Calendar API"
3. Create OAuth 2.0 credentials → Download as `credentials.json`
4. Place `credentials.json` in the `backend/` folder
5. On first run, a browser window will open to authorize

---

## How the AI Works

| Task | Model | Why |
|---|---|---|
| Objection handling | Claude Sonnet | Needs nuance and coaching knowledge |
| Document generation | Claude Sonnet | High stakes, needs accuracy |
| Listing presentations | Claude Sonnet | Creative, complex |
| Lead scoring analysis | Claude Haiku | Fast + cheap for data tasks |
| Market research parsing | Claude Haiku | Volume processing |
| Web search | Tavily API | Real-time data from Zillow, Redfin, MLS |

---

## File Structure

```
aria-re/
├── backend/
│   ├── main.py              ← FastAPI app entry point
│   ├── database.py          ← All database models
│   ├── config.py            ← Settings (reads .env)
│   ├── agents/
│   │   ├── brain.py         ← AI model routing (Sonnet/Haiku)
│   │   ├── research.py      ← Market data + CMA engine
│   │   ├── lead_scorer.py   ← Lead scoring + call list
│   │   ├── scripts.py       ← Objection handling + call scripts
│   │   ├── documents.py     ← CA disclosure document generation
│   │   ├── marketing.py     ← MLS copy, social, newsletters
│   │   ├── email_agent.py   ← SendGrid email sending
│   │   └── calendar_agent.py ← Google Calendar integration
│   └── routers/
│       ├── leads.py         ← Lead CRUD + scoring API
│       ├── market.py        ← CMA + market snapshot API
│       ├── listings.py      ← Listing management API
│       ├── marketing.py     ← Email + newsletter API
│       └── calendar.py      ← Scheduling API
├── frontend/
│   ├── index.html           ← Full dashboard UI
│   └── static/
│       ├── css/style.css    ← All styles
│       └── js/app.js        ← All frontend logic
├── data/
│   └── documents/           ← Generated PDFs saved here
├── .env                     ← Your API keys (never commit this)
├── requirements.txt
└── setup.sh
```

---

## Key Workflows

### Daily Routine
1. Open ARIA → **Daily Call List** — ranked leads ready to call
2. Click **Get Script** on any lead for a personalized word-for-word script
3. If seller pushes back → **Objection Help** button instantly
4. Log the call → stage updates automatically
5. **Schedule Follow-up** → goes straight to Google Calendar

### New Listing
1. **My Listings** → Add Listing
2. Click **Presentation** → full listing presentation generated
3. Click **MLS Copy** → paste-ready MLS description
4. Click **Social Posts** → all platforms ready
5. **Documents** → RLA + TDS + Net Sheet PDFs generated

### Lead Import
1. **Import Leads** → drag & drop your CSV/Excel
2. ARIA scores every lead 0-100 instantly
3. Ranked call list updates automatically

---

## California Document Notes

ARIA generates **draft PDFs for review**. These are NOT legally binding — they are:
- Pre-filled with property and agent data to save you time
- Flagged with everything that needs your review or seller signature
- Designed to be used alongside official **C.A.R. forms** (RLA, TDS, SPQ, AVID)

For executed documents, use **zipForm Plus** or **Dotloop** with official CAR forms.
ARIA's PDFs serve as your prep/review checklists.

---

## Cost Estimate

| Usage | Monthly Cost |
|---|---|
| 50 lead scorings/day | ~$8/mo (Haiku) |
| 10 CMAs/day | ~$12/mo (Sonnet) |
| 5 documents/day | ~$15/mo (Sonnet) |
| Daily market research | ~$6/mo (Tavily) |
| **Total estimate** | **~$40-60/mo** |

Heavy usage (100+ leads/day, multiple presentations) may run $100-150/mo.
