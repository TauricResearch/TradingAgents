"""FastAPI SaaS wrapper around the TradingAgents multi-agent research pipeline.

Monetization model: freemium API-key access. Every signup gets a free tier
with a monthly cap on analysis runs (``free_tier_monthly_limit()`` in
database.py); a Stripe subscription lifts the cap. See webapp/README.md for
the full plan and setup instructions.

This service only ever produces research reports and a suggested decision
label — it never places trades. It is not financial advice; see the
project-wide disclaimer in the main README.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

from . import billing, database, jobs

logger = logging.getLogger(__name__)

app = FastAPI(title="TradingAgents API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    database.init_db()


# --- auth -------------------------------------------------------------


def current_user(x_api_key: str = Header(..., alias="X-API-Key")):
    user = database.get_user_by_api_key(x_api_key)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user


# --- schemas ------------------------------------------------------------


class SignupRequest(BaseModel):
    email: EmailStr


class AnalyzeRequest(BaseModel):
    ticker: str
    trade_date: str | None = None  # defaults to today; YYYY-MM-DD


# --- account endpoints ----------------------------------------------------


@app.post("/api/signup")
def signup(body: SignupRequest):
    if database.get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = database.create_user(body.email)
    return {"email": user["email"], "api_key": user["api_key"], "plan": user["plan"]}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return {
        "email": user["email"],
        "plan": user["plan"],
        "jobs_this_month": database.jobs_this_month(user["id"]),
        "free_tier_limit": database.free_tier_monthly_limit(),
    }


# --- billing endpoints ------------------------------------------------


@app.post("/api/billing/checkout")
def create_checkout(request: Request, user=Depends(current_user)):
    if not billing.billing_configured():
        raise HTTPException(
            status_code=503,
            detail="Billing is not configured on this deployment "
            "(set STRIPE_SECRET_KEY and STRIPE_PRICE_ID).",
        )
    base = str(request.base_url).rstrip("/")
    url = billing.create_checkout_session(
        user,
        success_url=f"{base}/billing/success",
        cancel_url=f"{base}/billing/cancel",
    )
    return {"checkout_url": url}


@app.post("/api/billing/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None, alias="Stripe-Signature")):
    if not billing.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    payload = await request.body()
    try:
        billing.handle_webhook_event(payload, stripe_signature)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid webhook: {exc}") from exc
    return {"received": True}


@app.get("/billing/success")
def billing_success():
    return RedirectResponse(url="/#billing-success")


@app.get("/billing/cancel")
def billing_cancel():
    return RedirectResponse(url="/#billing-cancel")


# --- analysis endpoints -------------------------------------------------


@app.post("/api/analyze")
def analyze(body: AnalyzeRequest, user=Depends(current_user)):
    ticker = body.ticker.upper()
    trade_date = body.trade_date or date.today().isoformat()

    # Cache hit: someone already paid for this exact (ticker, trade_date)
    # recently. Reuse it — no quota spent, no LLM cost, instant result.
    cached_source = database.find_recent_completed_job(ticker, trade_date)
    if cached_source is not None:
        job_id = uuid.uuid4().hex
        database.create_cached_job(job_id, user["id"], cached_source)
        return {"job_id": job_id, "status": "done", "cached": True}

    if user["plan"] == "free" and database.jobs_this_month(user["id"]) >= database.free_tier_monthly_limit():
        raise HTTPException(
            status_code=402,
            detail="Free tier monthly limit reached. Upgrade via /api/billing/checkout.",
        )
    job_id = jobs.submit_job(user["id"], ticker, trade_date)
    return {"job_id": job_id, "status": "queued", "cached": False}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, user=Depends(current_user)):
    job = database.get_job(job_id, user["id"])
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(job)


@app.get("/api/jobs")
def job_history(user=Depends(current_user)):
    return [dict(row) for row in database.list_jobs(user["id"])]


# --- static frontend -----------------------------------------------------
# The React app (webapp/frontend/) builds to dist/, which this mounts as
# the site root. Mounting is skipped (not a hard failure) when dist/ hasn't
# been built yet, so the API is still importable/testable on its own — e.g.
# in CI jobs or local backend work that don't need the built UI.

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
else:
    logger.warning(
        "%s not found — run `npm run build` in webapp/frontend to serve the UI. "
        "API endpoints work without it.",
        _FRONTEND_DIST,
    )
