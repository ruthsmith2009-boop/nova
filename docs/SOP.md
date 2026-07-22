# NOVA — Standard Operating Procedures

NOVA is Ruth's AI sales assistant for **any** small business that generates leads (the universal
sibling to ARIA, which stays real-estate-only). This is the operator's manual: how to run it, deploy
it, and fix the things that commonly come up.

---

## 1. Where everything lives
- **Code:** `~/nova/` (private GitHub repo: `github.com/ruthsmith2009-boop/nova`)
- **Live site:** https://nova-production-12cd.up.railway.app
- **Local dev:** http://127.0.0.1:8098
- **Stack:** FastAPI + SQLite + Claude API. Frontend is static (`frontend/index.html`, `static/js/app.js`, `static/css/style.css`).
- **Railway:** project `nova` (id `0fe63ee7-0f8a-402f-8ae2-374577473072`), service `nova` (id `48ea558b-a250-47da-8f2f-17ad5e2d3429`), environment `production`.

## 2. Run it locally
```bash
cd ~/nova
python run_local.py        # serves API + frontend on http://127.0.0.1:8098
```
`run_local.py` loads the root `.env` so the API keys are present. The launch.json name is `nova`.

## 3. Deploy to the live site
```bash
cd ~/nova
git add -A && git commit -m "..."      # commit first
git push origin main
railway up --detach --service nova     # builds + deploys
```
A deploy takes a few minutes. Because leads now live on a persistent volume (see §5), **deploys no
longer wipe the leads.**

## 4. Environment variables (Railway)
```bash
railway variables --service nova                       # list all
railway variables set "KEY=value" --service nova       # set one
railway variables delete KEY --service nova            # remove one
```
Identity vars that should stay universal (not real-estate): `BROKER_NAME=AI With Ruth`,
`PRIMARY_MARKET=United States (any industry)`, `AGENT_NAME=Ruth Smith`, `AGENT_LICENSE` empty.

## 5. Persistent database (the volume)
The live DB is SQLite. Without a volume, every redeploy wipes it. A volume is now attached:
- **Volume:** `nova-volume`, mounted at `/data`, 5 GB.
- **Var:** `DATABASE_URL=sqlite:////data/nova.db` (four slashes = absolute path).
- Manage: `railway volume list` / `railway volume add -m /data` (link the service first with
  `railway service link nova` or the CLI panics).

## 6. Import / re-import leads
Leads persist across deploys now, so this is only needed for a fresh DB or a new lead list.
Each lead is a `POST /leads/` (auto-scored on arrival). Do them **sequentially** — parallel POSTs
race and create duplicates.
```python
import json, urllib.request, time
B = "https://nova-production-12cd.up.railway.app"
leads = json.load(open("leads.json"))   # list of {first_name,last_name,email,phone,address(=company),city,...}
for l in leads:
    req = urllib.request.Request(f"{B}/leads/", data=json.dumps(l).encode(),
                                 headers={"Content-Type":"application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=60); time.sleep(0.3)
```
Export the current live leads any time: `GET /leads/`.
Note: a lead's **company** is stored in the `address` field (the CRM's schema is generic).

## 7. Health check
```bash
B=https://nova-production-12cd.up.railway.app
for e in / /leads/ /leadgen/providers /coach/prompts /finance/summary /scripts/ /templates/; do
  curl -s -o /dev/null -w "%{http_code}  $e\n" "$B$e"; done
```
All should return 200. The deleted real-estate endpoints (`/listings/`, `/market/*`, `/forms/*`,
`/documents/*`) should return 404 — that's correct.

## 8. Common problems & fixes
- **Leads vanished after deploy** → the volume/`DATABASE_URL` isn't set; see §5, then re-import (§6).
- **`railway volume add` panics** → no service linked. Run `railway service link nova` first.
- **Lead-gen returns weird/real-estate results** → confirm `search_market` (`agents/research.py`)
  isn't passing real-estate domains. It should search the whole web by default.
- **AI output sounds real-estate-y** → check `SYSTEM_PERSONA` and `BUSINESS_KNOWLEDGE` in
  `agents/brain.py` (these inject into every AI call). See `docs/PROMPTS.md`.
- **Vapi calls fail** → voice must be a valid Vapi voice. Use `Savannah` (not `jennifer`).

## 9. Save routine (end of every work session)
1. `git commit` + `git push` (GitHub).
2. Update `~/.claude/skills/nova/SKILL.md` (Progress Log + Next Session).
3. Update the Obsidian note and the Notion NOVA page.
4. Keep `docs/SOP.md` and `docs/PROMPTS.md` current if the ops or prompts changed.

## 10. Open items
- Native Google OAuth sign-in (Gmail/Calendar as aiwithruth@gmail.com) — email already sends via SendGrid.
- Optional dedicated NOVA phone number (currently shares ARIA's Vapi/Twilio line).
