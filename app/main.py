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
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import redis.asyncio as redis

from app.auth import HMACAuthMiddleware
from app.config import settings
from app.db import dispose_engine, get_engine
from app.logging_config import configure_logging
from app.observability import init_sentry
from app.routes.analyze import router as analyze_router
from app.routes.stream import router as stream_router


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

# CORS — only needed for the /stream/{run_id} SSE endpoint. The browser's
# EventSource enforces same-origin by default; the dashboard at
# lyceum-fund-app.vercel.app reaches across to this service for SSE, so
# we have to allow the cross-origin GET explicitly.
#
# Other routes (POST /analyze) come from the Node-side worker, which is
# server-to-server — no browser CORS check applies, so the worker isn't
# affected.
#
# Wildcard list comes from CORS_ALLOW_ORIGINS env var if set (comma-
# separated), with a sensible default that covers the prod Vercel URL.
# Vercel preview URLs (random per-PR subdomains) won't match; if you
# need previews to work, add them to CORS_ALLOW_ORIGINS or switch to
# allow_origin_regex with a vercel.app pattern.
_default_origins = "https://lyceum-fund-app.vercel.app,http://localhost:3000"
_origins = [
    o.strip() for o in (settings.CORS_ALLOW_ORIGINS or _default_origins).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,                # SSE uses query-param token, no cookies
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Type"],
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
    """Close the async DB pool cleanly on container stop."""
    await dispose_engine()


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
    True iff Redis PING succeeds. Fresh client per call — the singleton
    pattern broke cross-event-loop callbacks in LangGraph (see pubsub.py).
    """
    try:
        client = redis.from_url(settings.REDIS_URL, socket_timeout=2)
        await client.ping()
        await client.aclose()
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
