# Clone NOVA for a New Client — Checklist

Step-by-step playbook for turning the NOVA template into a white-labeled app
for a paying client. Work top to bottom; nothing here requires code changes
except the theme colors.

---

## 1. Copy the repo

```bash
cp -R ~/nova ~/clients/<client-name>-app
cd ~/clients/<client-name>-app
rm -rf .git && git init && git add -A && git commit -m "Initial clone from NOVA template"
git remote add origin <new-private-github-repo-url>
git push -u origin main
```

Do NOT copy `.env` or `backend/nova.db` into the client repo (they hold Ruth's
keys and data). Start the client's `.env` fresh from `.env.example`.

## 2. Fill in `.env` (from `.env.example`)

| Key | What it controls |
|---|---|
| `BUSINESS_NAME` | App/brand name — browser tab title, sidebar logo, footer, email signatures ("Sent automatically by X AI Calling") |
| `AGENT_NAME` | Owner's name — dashboard footer, startup log, health endpoint |
| `AGENT_LICENSE` | License number if the client's industry has one (else leave blank) |
| `BROKER_NAME` | Legal business name — startup log, email copy |
| `AGENT_PHONE` / `AGENT_EMAIL` | Owner contact info used in generated content |
| `PRIMARY_MARKET` | The market/industry Claude assumes when writing scripts and copy |
| `APP_USERNAME` / `APP_PASSWORD` | Login wall for the deployed app (HTTP Basic). Always set for clients. |
| `APP_SECRET_KEY` | Random string for app security — generate a fresh one per client |
| `ANTHROPIC_API_KEY` | Claude — all AI features. Consider a per-client key to track usage. |
| `TAVILY_API_KEY` | Live web research + lead hunting |
| `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, `SENDGRID_FROM_NAME` | Outbound email — from-address should be the client's domain |
| `VAPI_API_KEY`, `VAPI_PHONE_NUMBER_ID`, `VAPI_ASSISTANT_ID` | AI voice calling |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` | The client's phone line (buy a local number) |
| `VAPI_VOICE`, `VAPI_VOICE_PROVIDER`, `NOVA_PHONE_NUMBER` | Client's voice + business number — see "Telephony (per client)" below |
| `VAPI_WEBHOOK_SECRET` | Shared secret protecting `/calling/webhook` — set the SAME value as the "Server URL Secret" in the Vapi dashboard |
| `LEADGEN_WEBHOOK_TOKEN` | Shared secret for the Zapier inbound-lead webhook |
| `SMS_TEXTBACK_ENABLED` | Missed-call text-back. Keep `false` until the client's A2P 10DLC campaign is approved — see "Missed-call text-back" below |
| `SMS_TEXTBACK_MESSAGE` | Optional custom text-back body (blank = default built from `BUSINESS_NAME`) |
| `SMS_WEBHOOK_TOKEN` | Shared secret for the Twilio inbound-SMS webhook (`/sms/incoming?token=...`) |
| `DATABASE_URL` | Where the SQLite db lives — see step 5 |
| `GOOGLE_ACCOUNT_EMAIL` + calendar keys | The client's Google account for Calendar/Gmail |

## 2b. Telephony (per client)

Every client gets their own number and voice:

1. **Buy the client a Twilio local number** (their area code) in the Twilio console.
2. **Import the number into Vapi** — Vapi dashboard → Phone Numbers → Import (provider = `twilio`, using the client's `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`).
3. **Create a client-named inbound assistant** in Vapi — greeting must include an AI disclosure and the business name from env, e.g. "Thanks for calling `BUSINESS_NAME` — I'm the AI assistant, how can I help?"
4. **Attach the assistant to the number** (Vapi phone number → Inbound → select the assistant).
5. **Set the env vars**: `NOVA_PHONE_NUMBER` = the new number (E.164), and `VAPI_VOICE`:
   - a stock Vapi voice name (keep `VAPI_VOICE_PROVIDER=vapi`), or
   - an ElevenLabs voice ID with `VAPI_VOICE_PROVIDER=11labs` — cloned from ~2 min of the client's audio, **with their written consent**.

## 2c. Missed-call text-back (activate AFTER A2P approval)

The feature ships in the code but DISABLED. When a caller hangs up on the AI
receptionist (or the line is busy / doesn't connect), NOVA texts them back and
logs them as a lead. Do NOT turn it on before the number's A2P 10DLC campaign
clears carrier vetting — unregistered traffic gets filtered.

1. **Wait for A2P approval** — the campaign status in Twilio Console →
   Messaging → Regulatory Compliance must be **Approved** (registration kit:
   `docs/A2P_SOLE_PROP_KIT.md`).
2. **Set the Twilio number's SMS webhook** — Twilio Console → Phone Numbers →
   the number → Messaging Configuration → "A message comes in" →
   Webhook, **POST**, URL: `https://<app>/sms/incoming?token=<SMS_WEBHOOK_TOKEN>`.
   (Importing the number into Vapi only changed its *Voice* webhook —
   messaging still routes through Twilio.)
3. **Set the env vars** on Railway: `SMS_TEXTBACK_ENABLED=true` and
   `SMS_WEBHOOK_TOKEN=<random secret>` (must match the `?token=` in step 2).
   Optionally set `SMS_TEXTBACK_MESSAGE`; blank uses the default built from
   `BUSINESS_NAME`.
4. **Test**: call the number from a cell phone, hang up after one ring →
   a text-back arrives, and the caller appears as a lead (source
   `missed-call`). Reply `BOOK` → lead turns hot + lands in today's follow-ups.
   Reply `STOP` → number is added to `sms_opt_outs` and never texted again.

## 3. Re-theme (CSS variables only)

All colors live in `frontend/static/css/style.css` in the `:root` blocks
(light theme at the top, the active dark "glass" theme around line 253).
Change the variables only — `--gold`, `--gold-bright`, `--gold-gradient`,
`--ink-*`, `--glass-border` — and every button, badge, and gradient follows.
No HTML edits needed. Bump the cache-buster in `index.html`
(`style.css?v=...`) after theme changes.

## 4. New Railway project

1. railway.app → New Project → Deploy from the client's GitHub repo.
2. Add a **volume**: 5 GB, mount path **`/data`**.
3. Set **`DATABASE_URL=sqlite:////data/<client>.db`** (four slashes = absolute path) so the database persists across redeploys.

## 5. Set all env vars on Railway

Paste every key from step 2 into Railway → Variables. `PUBLIC_BASE_URL` is
derived automatically from `RAILWAY_PUBLIC_DOMAIN` — no need to set it.

## 6. Deploy

Push to the repo (Railway auto-deploys) or `railway up`. Then point the
client's custom domain at the Railway service if they have one.

## 7. Smoke test (every clone, every time)

- [ ] Visit the URL → login prompt appears; `APP_USERNAME`/`APP_PASSWORD` work
- [ ] Browser tab + sidebar + footer show the client's `BUSINESS_NAME`
- [ ] Create a lead → it appears in the pipeline with a score
- [ ] Dashboard loads with no red "not configured" alerts (Anthropic/Tavily)
- [ ] AI Automations → Live Demo page plays all three demos
- [ ] `/health` returns the client's owner name
- [ ] (If calling is on) place a test call; confirm the webhook writes the result — and that hitting `/calling/webhook` without the secret returns 401
- [ ] Redeploy once and confirm the test lead is still there (volume works)

---

## Known leftovers in the template (awaiting Ruth's approval to remove)

These are inherited from ARIA and are harmless but still present — do not
delete without Ruth's explicit go-ahead:

- `backend/database.py` — unused `Listing` and `CMAReport` models (real-estate residue; no routes use them)
- `render.yaml` — stale Render deploy config (NOVA deploys on Railway)
