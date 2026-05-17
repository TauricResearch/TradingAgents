"""
FastAPI entrypoint for trading-agents-service.

This is the service-wrapper layer around the upstream
TauricResearch/TradingAgents library. The library code lives unchanged
in `tradingagents/` at the repo root; this `app/` directory adds the
HTTP service shell + persistence + auth + observability.

Routes:
- GET /health  — liveness. Always 200 if the process is up.
- GET /ready   — readiness. 200 only when DB + Redis are reachable; 503 otherwise.

Phase 182c adds:
- POST /analyze              — kick off a TradingAgents run
- GET  /stream/{run_id}      — SSE-fed live progress

Treat this file as a python-temp-pro template — the only trading-specific
references are commented future-extension points, not active code.
"""

import asyncio

import sentry_sdk
from fastapi import FastAPI, Response
from sqlalchemy import text

from app.auth import HMACAuthMiddleware
from app.config import settings
from app.db import dispose_engine, get_engine
from app.logging_config import configure_logging
from app.observability import init_sentry
from app.routes.analyze import router as analyze_router
from app.routes.stream import router as stream_router
from app.services.redis_client import close_redis, get_redis


# Logging + Sentry must init BEFORE app construction so the FastAPI
# integration can wrap request handlers at import time. No-op when
# SENTRY_DSN is unset.
configure_logging()
init_sentry()


app = FastAPI(
    title="trading-agents-service",
    description="FastAPI wrapper around TauricResearch/TradingAgents",
    version="0.1.0",
)

# HMAC verification on POST/PUT/PATCH/DELETE. /health, /ready, and the
# FastAPI docs paths bypass — see app/auth.py for the contract. GETs
# pass through the middleware; routes that need auth handle it
# themselves (e.g., /stream/{run_id} uses a query-param token).
app.add_middleware(HMACAuthMiddleware)

# Routes — analyze + stream. /health and /ready are defined inline below.
app.include_router(analyze_router)
app.include_router(stream_router)


# ── Lifecycle ─────────────────────────────────────────────────────────────

@app.on_event("shutdown")
async def shutdown_handler() -> None:
    """Close the async DB pool + shared Redis client on container stop."""
    await dispose_engine()
    await close_redis()


# ── Connection probes for /ready ───────────────────────────────────────────

async def _ping_db() -> bool:
    """True iff a trivial SELECT round-trips against Postgres."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return False


async def _ping_redis() -> bool:
    """
    True iff Redis PING succeeds. TT-295: reuses the shared singleton
    instead of opening a new TCP+TLS handshake on every /ready probe
    (Railway hits this ~every 30s).
    """
    try:
        await get_redis().ping()
        return True
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return False


# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    """
    Liveness probe. Always 200 when the process is up. Railway's healthcheck
    points here — failed deploys get rolled back when this stays non-200
    after the healthcheckTimeout window.
    """
    return {
        "ok": True,
        "service": "trading-agents-service",
        "env": settings.NODE_ENV,
        "app": settings.APP_SLUG,
    }


@app.get("/ready")
async def ready(response: Response) -> dict:
    """
    Readiness probe. 200 only when DB + Redis are reachable. Use this in
    front-of-line load balancer config or before promoting a new deploy —
    /health says "process is alive," /ready says "ready to take traffic."
    """
    db_ok, redis_ok = await asyncio.gather(_ping_db(), _ping_redis())
    ok = db_ok and redis_ok
    if not ok:
        response.status_code = 503
    return {
        "ok": ok,
        "checks": {
            "database": db_ok,
            "redis": redis_ok,
        },
    }


# Future phases:
#   - 182d (Node side) — dashboard pages that hit /analyze + /stream/{run_id}
#   - TT-286 (long-term) — extract /analyze background work to dedicated
#     Arq worker for restart-safety + concurrency limits
