"""
NOVA — AI Assistant for Small Business — FastAPI Backend
"""
import sys
import os
import secrets
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from database import create_tables
from routers import (
    leads, marketing, calendar, social, calling, leadgen, finance,
    scripts, team, integrations, templates, coach, compliance,
)
from config import settings

app = FastAPI(
    title="NOVA — AI Assistant for Small Business",
    description="AI sales assistant for any small business that generates leads",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Login wall ────────────────────────────────────────────────────────────────
# When ARIA_USERNAME + ARIA_PASSWORD are set (i.e. when deployed), the dashboard and
# API require HTTP Basic Auth. Webhooks and health are exempt — external services
# (Vapi, Zapier) must reach them, and they carry their own token security.
import base64

PUBLIC_PATHS = ("/health", "/calling/webhook", "/leadgen/inbound")


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    user = settings.aria_username
    pw = settings.aria_password
    # No credentials configured (local dev) → no login required
    if not (user and pw):
        return await call_next(request)
    # Public endpoints bypass the login wall
    if any(request.url.path.startswith(p) for p in PUBLIC_PATHS):
        return await call_next(request)

    header = request.headers.get("Authorization", "")
    if header.startswith("Basic "):
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
            given_user, _, given_pw = decoded.partition(":")
            if secrets.compare_digest(given_user, user) and secrets.compare_digest(given_pw, pw):
                return await call_next(request)
        except Exception:
            pass
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="NOVA"'},
        content="Authentication required",
    )

# Include all routers
app.include_router(leads.router)
app.include_router(marketing.router)
app.include_router(calendar.router)
app.include_router(social.router)
app.include_router(calling.router)
app.include_router(leadgen.router)
app.include_router(finance.router)
app.include_router(scripts.router)
app.include_router(team.router)
app.include_router(integrations.router)
app.include_router(templates.router)
app.include_router(coach.router)
app.include_router(compliance.router)

# Serve frontend
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "static")), name="static")


@app.on_event("startup")
async def startup():
    create_tables()
    # Hands-off auto-leads: background loop that runs saved hunts on their cadence.
    import asyncio
    from agents.scheduler import scheduler_loop
    asyncio.create_task(scheduler_loop())
    print(f"✅ NOVA — AI Assistant for Small Business started")
    print(f"   Owner: {settings.agent_name} | {settings.broker_name}")
    print(f"   Focus: Universal sales & lead generation (any industry)")
    print(f"   Auto-hunt scheduler: running")
    print(f"   API docs: http://localhost:8000/docs")


@app.get("/")
def serve_frontend():
    index = os.path.join(frontend_path, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "NOVA — AI Assistant for Small Business API", "docs": "/docs"}


@app.get("/health")
def health():
    return {
        "status": "running",
        "agent": settings.agent_name,
        "market": settings.primary_market
    }


@app.get("/config")
def get_config():
    return {
        "agent_name": settings.agent_name,
        "broker_name": settings.broker_name,
        "agent_email": settings.agent_email,
        "agent_phone": settings.agent_phone,
        "primary_market": settings.primary_market,
        "anthropic_configured": bool(settings.anthropic_api_key),
        "tavily_configured": bool(settings.tavily_api_key),
        "sendgrid_configured": bool(settings.sendgrid_api_key),
    }
