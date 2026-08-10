"""Run history and manual run triggers."""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import RunTriggeredResponse, SignalItem
from app.core.logging import log_task_exception
from app.domain import Market
from app.models.base import get_session
from app.repositories.signals import SignalRepository
from app.repositories.watchlist import WatchlistRepository
from app.services.pipeline import run_market, run_ticker, runs_remaining_today

logger = logging.getLogger(__name__)

router = APIRouter(tags=["runs"])

# Keep strong references so fire-and-forget run tasks aren't garbage-collected
# mid-flight (asyncio only holds weak refs to tasks).
_background_runs: set[asyncio.Task] = set()


@router.get("/signals", response_model=list[SignalItem])
async def list_signals(
    session: Annotated[AsyncSession, Depends(get_session)],
    symbol: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[SignalItem]:
    records = await SignalRepository(session).list_recent(symbol=symbol, limit=limit)
    return [SignalItem.model_validate(r) for r in records]


@router.post("/runs/ticker/{symbol}", response_model=RunTriggeredResponse, status_code=202)
async def trigger_ticker_run(
    symbol: str, session: Annotated[AsyncSession, Depends(get_session)]
) -> RunTriggeredResponse:
    """Analyze one watchlist ticker right now (counts against the daily budget)."""
    ticker = await WatchlistRepository(session).get_by_symbol(symbol)
    if ticker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{symbol.upper()} is not on the watchlist — add it first",
        )
    if await runs_remaining_today() <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily run budget exhausted — raise ASSISTANT_DAILY_RUN_BUDGET or wait for tomorrow",
        )
    task = asyncio.create_task(run_ticker(ticker.symbol), name=f"run_ticker:{ticker.symbol}")
    _background_runs.add(task)
    task.add_done_callback(_background_runs.discard)
    task.add_done_callback(log_task_exception)
    logger.info("Manual analysis triggered for %s", ticker.symbol)
    return RunTriggeredResponse(market=ticker.symbol)


@router.post("/runs/{market}", response_model=RunTriggeredResponse, status_code=202)
async def trigger_run(market: Market) -> RunTriggeredResponse:
    """Kick off a full market run now (includes weekly-tier tickers).

    Returns immediately; a watchlist run takes minutes to hours of LLM time.
    Progress lands in logs, Telegram, and the email digest. The pipeline's
    internal lock serializes this with any scheduled run already in flight.
    """
    task = asyncio.create_task(run_market(market, include_weekly=True), name=f"run_market:{market.value}")
    _background_runs.add(task)
    task.add_done_callback(_background_runs.discard)
    task.add_done_callback(log_task_exception)
    logger.info("Manual run triggered for %s", market.value)
    return RunTriggeredResponse(market=market.value)
