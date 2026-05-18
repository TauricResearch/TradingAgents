from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Callable

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Config

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")


def _is_trading_day(dt: datetime) -> bool:
    try:
        import pandas_market_calendars as mcal
        nyse = mcal.get_calendar("NYSE")
        schedule = nyse.schedule(
            start_date=dt.strftime("%Y-%m-%d"),
            end_date=dt.strftime("%Y-%m-%d"),
        )
        return not schedule.empty
    except Exception:
        return dt.weekday() < 5


def _is_first_trading_day_of_week(dt: datetime) -> bool:
    """True when dt is a trading day and no earlier day in its ISO week is also a trading day."""
    if not _is_trading_day(dt):
        return False
    for offset in range(1, dt.weekday() + 1):
        if _is_trading_day(dt - timedelta(days=offset)):
            return False
    return True


def build_scheduler(
    cfg: Config,
    run_intraday_fn: Callable,
    run_eod_fn: Callable,
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=ET)

    def _guarded_intraday() -> None:
        if _is_trading_day(datetime.now(ET)):
            run_intraday_fn()

    def _guarded_eod() -> None:
        if _is_trading_day(datetime.now(ET)):
            run_eod_fn()

    def _guarded_premarket() -> None:
        if _is_first_trading_day_of_week(datetime.now(ET)):
            run_eod_fn()

    for time_str in cfg.intraday_check_times:
        hour, minute = time_str.split(":")
        scheduler.add_job(
            _guarded_intraday,
            CronTrigger(
                day_of_week="mon-fri",
                hour=int(hour),
                minute=int(minute),
                timezone=ET,
            ),
            id=f"intraday_{time_str.replace(':', '')}",
            max_instances=1,
            coalesce=True,
        )

    eod_hour, eod_minute = cfg.eod_scan_time.split(":")
    scheduler.add_job(
        _guarded_eod,
        CronTrigger(
            day_of_week="mon-fri",
            hour=int(eod_hour),
            minute=int(eod_minute),
            timezone=ET,
        ),
        id="eod_scan",
        max_instances=1,
        coalesce=True,
    )

    pm_hour, pm_minute = cfg.premarket_scan_time.split(":")
    scheduler.add_job(
        _guarded_premarket,
        CronTrigger(
            day_of_week="mon-fri",
            hour=int(pm_hour),
            minute=int(pm_minute),
            timezone=ET,
        ),
        id="premarket_scan",
        max_instances=1,
        coalesce=True,
    )

    return scheduler
