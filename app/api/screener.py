"""Screener endpoints: recent results and a manual trigger."""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ScreenerResultItem
from app.models.base import get_session
from app.repositories.screener import ScreenerRepository
from app.services.screener import run_screener_guarded

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/screener", tags=["screener"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_runs: set[asyncio.Task] = set()


@router.get("", response_model=list[ScreenerResultItem])
async def recent_results(session: SessionDep) -> list[ScreenerResultItem]:
    results = await ScreenerRepository(session).list_recent(limit=40)
    return [ScreenerResultItem.model_validate(r) for r in results]


def _log_run_outcome(task: asyncio.Task) -> None:
    """Report how a background run ended.

    A bare add_done_callback(discard) drops the exception on the floor: nothing
    ever retrieves it, so a failure is invisible apart from an eventual
    "Task exception was never retrieved" at garbage-collection time. That is why
    three weeks of screener trouble left no trace anywhere.
    """
    _runs.discard(task)
    if task.cancelled():
        logger.error("Screener task was cancelled")
        return
    error = task.exception()
    if error is not None:
        logger.error("Screener task raised", exc_info=error)


@router.post("/run", status_code=202)
async def run_now() -> dict:
    """Fire a screener pass now (takes a minute or two; no LLM cost)."""
    # Guarded variant: bounded runtime, and the outcome is logged either way.
    task = asyncio.create_task(run_screener_guarded())
    _runs.add(task)
    task.add_done_callback(_log_run_outcome)
    logger.info("Manual screener run triggered")
    return {"status": "started"}
