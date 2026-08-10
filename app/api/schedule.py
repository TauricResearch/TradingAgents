"""Schedule slot management endpoints. Edits re-sync the live scheduler."""

import asyncio
import logging
from typing import Annotated

import pytz
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ScheduleSlotCreate, ScheduleSlotItem, ScheduleSlotUpdate
from app.core.logging import log_task_exception
from app.core.scheduler import parse_hhmm, sync_slot_jobs
from app.domain import Market
from app.models.base import get_session
from app.models.entities import ScheduleSlot
from app.repositories.schedule import ScheduleRepository
from app.services.pipeline import run_slot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule", tags=["schedule"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Strong refs for fire-and-forget slot runs (asyncio keeps only weak refs).
_manual_runs: set[asyncio.Task] = set()


@router.get("", response_model=list[ScheduleSlotItem])
async def list_slots(session: SessionDep) -> list[ScheduleSlotItem]:
    slots = await ScheduleRepository(session).list_all()
    return [ScheduleSlotItem.model_validate(s) for s in slots]


@router.post("", response_model=ScheduleSlotItem, status_code=status.HTTP_201_CREATED)
async def create_slot(
    body: ScheduleSlotCreate, request: Request, session: SessionDep
) -> ScheduleSlotItem:
    try:
        pytz.timezone(body.timezone)
    except pytz.UnknownTimeZoneError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown timezone: {body.timezone}",
        ) from exc
    market = None
    if body.market and body.market != "any":
        try:
            market = Market(body.market).value
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown market: {body.market}",
            ) from exc
    slot = await ScheduleRepository(session).add(ScheduleSlot(
        label=body.label,
        run_time=body.run_time,
        timezone=body.timezone,
        market=market,
        enabled=body.enabled,
        max_tickers=body.max_tickers,
    ))
    item = ScheduleSlotItem.model_validate(slot)
    _schedule_resync(request.app.state.scheduler)
    return item


@router.delete("/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slot(slot_id: int, request: Request, session: SessionDep) -> None:
    repo = ScheduleRepository(session)
    slot = await repo.get(slot_id)
    if slot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")
    await session.delete(slot)
    _schedule_resync(request.app.state.scheduler)


def _schedule_resync(scheduler) -> None:
    task = asyncio.create_task(sync_slot_jobs(scheduler), name="sync_slot_jobs")
    _manual_runs.add(task)
    task.add_done_callback(_manual_runs.discard)
    task.add_done_callback(log_task_exception)


@router.patch("/{slot_id}", response_model=ScheduleSlotItem)
async def update_slot(
    slot_id: int, body: ScheduleSlotUpdate, request: Request, session: SessionDep
) -> ScheduleSlotItem:
    slot = await ScheduleRepository(session).get(slot_id)
    if slot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")

    if body.timezone is not None:
        try:
            pytz.timezone(body.timezone)
        except pytz.UnknownTimeZoneError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown timezone: {body.timezone}",
            ) from exc
        slot.timezone = body.timezone
    if body.run_time is not None:
        parse_hhmm(body.run_time)  # already regex-validated; belt and braces
        slot.run_time = body.run_time
    if body.market is not None:
        if body.market == "any":
            slot.market = None
        else:
            try:
                slot.market = Market(body.market).value
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Unknown market: {body.market}",
                ) from exc
    if body.label is not None:
        slot.label = body.label
    if body.enabled is not None:
        slot.enabled = body.enabled
    if body.max_tickers is not None:
        slot.max_tickers = body.max_tickers

    await session.flush()
    # Commit happens when the request-scoped transaction closes; re-sync the
    # scheduler afterwards so the new cron reflects what was just saved.
    item = ScheduleSlotItem.model_validate(slot)
    _schedule_resync(request.app.state.scheduler)
    return item


@router.post("/{slot_id}/run", status_code=202)
async def run_slot_now(slot_id: int, session: SessionDep) -> dict:
    """Fire a slot immediately (respects the daily run budget)."""
    slot = await ScheduleRepository(session).get(slot_id)
    if slot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")
    if not slot.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Slot is disabled; enable it first"
        )
    task = asyncio.create_task(run_slot(slot_id), name=f"run_slot:{slot_id}")
    _manual_runs.add(task)
    task.add_done_callback(_manual_runs.discard)
    task.add_done_callback(log_task_exception)
    logger.info("Manual run triggered for slot %r", slot.label)
    return {"slot": slot.label, "status": "started"}
