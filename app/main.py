"""
FastAPI entrypoint for trading-agents-service.

This is the service-wrapper layer around the upstream
TauricResearch/TradingAgents library. The library code lives unchanged
in `tradingagents/` at the repo root; this `app/` directory adds the
HTTP service shell + persistence + observability.

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
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import sentry_sdk
from fastapi import FastAPI, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import redis.asyncio as redis

from app.config import settings
from app.observability import init_sentry


# Sentry must init BEFORE app construction so the FastAPI integration can
# wrap request handlers at import time. No-op when SENTRY_DSN is unset.
init_sentry()


app = FastAPI(
    title="trading-agents-service",
    description="FastAPI wrapper around TauricResearch/TradingAgents",
    version="0.1.0",
)


# ── Connection probes for /ready ───────────────────────────────────────────
# Engines + clients lazily; readiness pings them. Don't hold connections
# open across the process lifetime here — let SQLAlchemy + redis pool
# manage that. This is just for the health-check shape.

def _asyncpg_url(raw: str) -> tuple[str, dict]:
    """
    Normalize a Postgres URL for asyncpg + SQLAlchemy. Returns (url, connect_args).

    asyncpg doesn't accept libpq-style query params (`sslmode`, `channel_binding`)
    that psycopg2 and Prisma include in their connection strings — they trip
    `TypeError: connect() got an unexpected keyword argument 'sslmode'` at
    connect time. We strip those params from the URL and translate
    `sslmode=require` → `connect_args={"ssl": "require"}`.

    Also coerces `postgresql://` / `postgres://` → `postgresql+asyncpg://` so
    SQLAlchemy picks the right dialect.
    """
    url = raw
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))

    connect_args: dict = {}
    sslmode = query.pop("sslmode", None)
    # channel_binding is a libpq SCRAM option asyncpg handles automatically;
    # asyncpg rejects it as a kwarg, so we just drop it.
    query.pop("channel_binding", None)

    if sslmode in ("require", "verify-ca", "verify-full"):
        connect_args["ssl"] = "require"

    cleaned = parsed._replace(query=urlencode(query))
    return urlunparse(cleaned), connect_args


async def _ping_db() -> bool:
    """True iff a trivial SELECT round-trips against Postgres."""
    try:
        url, connect_args = _asyncpg_url(settings.DATABASE_URL)
        engine = create_async_engine(
            url,
            pool_pre_ping=False,
            pool_size=1,
            connect_args=connect_args,
        )
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return True
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return False


async def _ping_redis() -> bool:
    """True iff Redis PING succeeds."""
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


# Phase 182b adds:
#   - HMAC auth middleware (signed POST verification)
#   - SQLAlchemy session dependency
#
# Phase 182c adds:
#   - POST /analyze  routes/analyze.py
#   - GET  /stream/{run_id}  routes/stream.py
#   - LangChain callback handler → Redis pub-sub
