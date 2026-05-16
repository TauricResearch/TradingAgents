"""
POST /analyze — kick off a TradingAgents run.

Auth: HMAC middleware (verified at the Starlette middleware layer before
this handler runs). The Node-side worker is the expected caller.

Flow:
  1. Create a `runs` row in status `pending`
  2. Schedule the analysis as a FastAPI BackgroundTask (returns
     immediately so the HTTP roundtrip is fast)
  3. Respond 202 with the runId so the Node side can subscribe to SSE

The actual work happens in `app.services.trading_agents_runner.run_analysis`.
That function owns DB state transitions + pub-sub for the rest of the
run's lifetime.

v1 uses FastAPI BackgroundTasks. The long-term replacement is a dedicated
Arq worker process (filed as TT-286) — same business logic, different
invocation site.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Run
from app.services.trading_agents_runner import run_analysis


logger = logging.getLogger(__name__)
router = APIRouter()


class AnalyzeRequest(BaseModel):
    """Body for POST /analyze. All fields required."""

    runId:     str = Field(..., min_length=1, description="Caller-supplied run ID (UUID). Must be unique.")
    userId:    str = Field(..., min_length=1, description="User this run is attributed to (Prisma User.id).")
    ticker:    str = Field(..., min_length=1, max_length=20, description="Exchange ticker, e.g. 'AAPL'.")
    tradeDate: str = Field(..., min_length=1, description="ISO date YYYY-MM-DD that the analysis targets.")


class AnalyzeResponse(BaseModel):
    runId:  str
    status: str = "pending"


@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
async def analyze(
    body: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> AnalyzeResponse:
    """
    Create a `runs` row + schedule background analysis. Returns 202
    immediately. Subscribe to `GET /stream/{runId}?token=...` for live
    progress; the run row also gets updated as the pipeline progresses.

    Idempotency: if a row with this runId already exists, return its
    current state without scheduling a new analysis. This lets the
    Node-side worker retry the enqueue without spawning duplicate runs.
    """
    existing = await db.get(Run, body.runId)
    if existing:
        # Already scheduled. Don't re-enqueue. Return what we have.
        return AnalyzeResponse(runId=body.runId, status=existing.status)

    db.add(
        Run(
            id=body.runId,
            user_id=body.userId,
            ticker=body.ticker,
            trade_date=body.tradeDate,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
    )
    # Commit before scheduling so the row is visible when the background
    # task starts (which may run before the response is fully flushed).
    await db.commit()

    background_tasks.add_task(
        run_analysis,
        run_id=body.runId,
        user_id=body.userId,
        ticker=body.ticker,
        trade_date=body.tradeDate,
    )

    logger.info(
        "analyze enqueued",
        extra={"run_id": body.runId, "ticker": body.ticker, "user_id": body.userId},
    )
    return AnalyzeResponse(runId=body.runId, status="pending")
