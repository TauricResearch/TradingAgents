"""APScheduler wiring: cron jobs are built from DB-backed schedule slots.

Slots are user-configurable from the dashboard (time, timezone, market filter,
tickers-per-run, enabled). ``sync_slot_jobs`` reconciles APScheduler with the
slots table and is called at startup and after every schedule edit.

Stock-market slots skip weekends; crypto slots run every day. A run missed
while the machine slept still fires within the hour (misfire_grace_time)
instead of silently skipping the day.
"""

import logging

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.domain import Market
from app.models.base import session_factory
from app.repositories.schedule import ScheduleRepository
from app.services.core_holding import sweep_all_books
from app.services.paper_broker import check_stops
from app.services.pipeline import run_slot
from app.services.screener import run_screener
from app.services.tactical.engine import record_equity_snapshots, run_tactical

logger = logging.getLogger(__name__)

_SLOT_JOB_PREFIX = "slot_"
_MONITOR_JOB_ID = "stop_monitor"
# Positions are repriced every 60 seconds via ONE batched Yahoo request per
# pass (rate-limit-safe at ~1,440 requests/day regardless of position count).
# Breaches still need to persist ~3 minutes before the reflex acts — cadence
# buys reaction speed, the time window keeps the whipsaw filter honest.
_MONITOR_INTERVAL_SECONDS = 60


def parse_hhmm(value: str) -> tuple[int, int]:
    hour_str, _, minute_str = value.partition(":")
    hour, minute = int(hour_str), int(minute_str or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid HH:MM time: {value!r}")
    return hour, minute


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    # Price-only stop-loss tripwire for open positions — no LLM cost, so it
    # runs far more often than the analysis slots and is exempt from the
    # daily run budget.
    scheduler.add_job(
        check_stops,
        "interval",
        seconds=_MONITOR_INTERVAL_SECONDS,
        id=_MONITOR_JOB_ID,
        name="stop-loss monitor",
        coalesce=True,
        max_instances=1,
    )
    # Tactical layer: end-of-day rule evaluation (only trades when
    # TACTICAL_RULE is explicitly set) + daily equity snapshots for the
    # scoreboard. Neither touches the LLM budget.
    scheduler.add_job(
        run_tactical,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=50,
                    timezone=pytz.timezone("America/New_York")),
        id="tactical",
        name="tactical rule pass",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=1800,
    )
    # Index-core sweep: park idle cash in the benchmark before the close, so
    # uncommitted capital earns the equity risk premium instead of nothing.
    # Runs before the equity snapshot so the scoreboard reflects the swept
    # book. No LLM cost and no forecasting — it is an accounting fix for the
    # measured root cause of both books trailing SPY (90.1% / 47.7% cash).
    scheduler.add_job(
        sweep_all_books,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=55,
                    timezone=pytz.timezone("America/New_York")),
        id="core_sweep",
        name="index-core cash sweep",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=1800,
    )
    scheduler.add_job(
        record_equity_snapshots,
        CronTrigger(hour=16, minute=15, timezone=pytz.timezone("America/New_York")),
        id="equity_snapshots",
        name="equity snapshots",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    # Daily anomaly-screener pass before the US pre-market slot. Pure data
    # APIs — no LLM cost, exempt from the run budget.
    if get_settings().screener_enabled:
        scheduler.add_job(
            run_screener,
            CronTrigger(day_of_week="mon-fri", hour=6, minute=0,
                        timezone=pytz.timezone("America/Chicago")),
            id="screener",
            name="anomaly screener",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
    return scheduler


async def sync_slot_jobs(scheduler: AsyncIOScheduler) -> None:
    """Reconcile APScheduler jobs with the schedule_slots table."""
    async with session_factory()() as session:
        slots = await ScheduleRepository(session).list_all()

    for job in scheduler.get_jobs():
        if job.id.startswith(_SLOT_JOB_PREFIX):
            job.remove()

    for slot in slots:
        if not slot.enabled:
            continue
        try:
            hour, minute = parse_hhmm(slot.run_time)
            tz = pytz.timezone(slot.timezone)
        except (ValueError, pytz.UnknownTimeZoneError):
            logger.exception("Slot %r has invalid time/timezone; skipping", slot.label)
            continue
        # Equities don't trade weekends; don't burn quota on stale data.
        day_of_week = "*" if slot.market == Market.CRYPTO.value else "mon-fri"
        scheduler.add_job(
            run_slot,
            CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute, timezone=tz),
            args=[slot.id],
            id=f"{_SLOT_JOB_PREFIX}{slot.id}",
            name=slot.label,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        logger.info(
            "Scheduled slot %r at %s %s (%s, max %d ticker(s))",
            slot.label, slot.run_time, slot.timezone, day_of_week, slot.max_tickers,
        )
