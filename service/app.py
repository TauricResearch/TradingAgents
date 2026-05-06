"""FastAPI application factory + entrypoint.

Run from the repo root with:
    uvicorn service.app:app --host 0.0.0.0 --port 8000 --reload   # dev
    uvicorn service.app:app --host 0.0.0.0 --port 8000            # prod

Or via the console script (after pip install '.[service]'):
    tradingagents-api
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gui import storage
from service.runner_pool import pool
from service.streaming import broadcaster
from service.routers import (
    briefs,
    calendar as calendar_router,
    charts as charts_router,
    chat,
    exports,
    health,
    memory,
    news_feed,
    notes,
    planner,
    portfolio,
    runs,
    settings,
    simulation,
    streaming,
    watchlist,
)

logger = logging.getLogger(__name__)


def _allowed_origins() -> list[str]:
    """Origins allowed for CORS.

    Defaults to common LAN dev origins. Override with CORS_ORIGINS env var
    (comma-separated), e.g. for the deployed Next.js host.
    """
    raw = os.environ.get("CORS_ORIGINS")
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # NAS LAN — adjust via CORS_ORIGINS env var if your NAS IP differs.
        "http://192.168.2.34:3000",
        "http://192.168.2.34",
    ]


app = FastAPI(
    title="TradingAgents API",
    version="0.3.0",
    description=(
        "REST + WebSocket API for the TradingAgents framework. Powers the "
        "Next.js frontend; also usable directly as the integration surface "
        "for any custom client. OpenAPI docs at /docs."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    storage.init_db()
    loop = asyncio.get_running_loop()
    pool.attach_loop(loop)
    broadcaster.start(loop)
    # Pre-warm the broadcaster with watchlist tickers so prices show up
    # without a manual subscribe.
    for entry in storage.list_watchlist():
        try:
            await broadcaster.subscribe("price", entry["ticker"])
        except Exception:
            pass
    logger.info("TradingAgents API ready. CORS origins: %s", _allowed_origins())


@app.on_event("shutdown")
async def _shutdown() -> None:
    await broadcaster.stop()


# Routers
app.include_router(health.router)
app.include_router(runs.router)
app.include_router(briefs.router)
app.include_router(chat.router)
app.include_router(notes.router)
app.include_router(settings.router)
app.include_router(memory.router)
app.include_router(charts_router.router)
app.include_router(exports.router)
app.include_router(streaming.router)
app.include_router(watchlist.router)
app.include_router(portfolio.router)
app.include_router(calendar_router.router)
app.include_router(news_feed.router)
app.include_router(simulation.router)
app.include_router(planner.router)


def main() -> int:
    """Console-script entrypoint — ``tradingagents-api``."""
    import uvicorn

    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "8000"))
    uvicorn.run("service.app:app", host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
