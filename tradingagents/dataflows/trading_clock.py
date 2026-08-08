"""Trading-hours gate for the poller.

The poller should run only around market hours, not 24/7: hourly across the
extended US-equity session (pre-market 04:00 → after-hours 20:00 ET), and the
first poll after an overnight/weekend/holiday gap sweeps the whole gap so the
pre-open decision sees everything that accumulated while markets were shut.

Session boundaries come from the NYSE calendar (via ``exchange_calendars`` when
installed — part of the ``poller`` extra), which gives exact holidays and
half-day early closes. The extended window is derived from each session's
regular open/close by fixed offsets, so half-days shift correctly:

    poll_start = regular_open  - 5h30m   (09:30 → 04:00 ET; same on half-days)
    poll_end   = regular_close + 4h00m   (16:00 → 20:00 ET; 13:00 → 17:00 on half-days)

If the calendar library isn't installed the gate degrades to a weekends-only
approximation with fixed 04:00–20:00 ET hours (no holiday awareness) and logs a
warning — the poller still runs, just slightly over-eager on the ~10 market
holidays a year.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tradingagents.logging_utils import safe_exception_type

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_PRE_OPEN = timedelta(hours=5, minutes=30)   # regular open  - 5h30m → 04:00 ET
_POST_CLOSE = timedelta(hours=4)             # regular close + 4h    → 20:00 ET
_FALLBACK_START_H = 4                         # 04:00 ET
_FALLBACK_END_H = 20                          # 20:00 ET


class TradingClock:
    """Decides whether the poller should be active and, if not, when to wake."""

    def __init__(self, calendar_name: str = "XNYS"):
        self._cal = None
        try:
            import exchange_calendars as xcals

            self._cal = xcals.get_calendar(calendar_name)
        except Exception as exc:  # noqa: BLE001 — fall back, never hard-fail
            logger.warning(
                "exchange_calendars unavailable (%s) — trading gate falls back to "
                "weekends-only with fixed 04:00–20:00 ET hours (no holidays). "
                "Install the 'poller' extra for the full NYSE calendar.",
                safe_exception_type(exc),
            )

    # -- session bounds for a given ET calendar date --------------------------
    def _session_bounds(self, day_et) -> tuple[datetime, datetime] | None:
        """Extended-session [start, end] in UTC for the ET date ``day_et``,
        or None if it isn't a trading day."""
        if self._cal is not None:
            import pandas as pd

            ts = pd.Timestamp(day_et)
            if not self._cal.is_session(ts):
                return None
            o = self._cal.session_open(ts).to_pydatetime().astimezone(timezone.utc)
            c = self._cal.session_close(ts).to_pydatetime().astimezone(timezone.utc)
            return o - _PRE_OPEN, c + _POST_CLOSE
        # Fallback: Mon–Fri, fixed hours.
        if day_et.weekday() >= 5:
            return None
        start = datetime(day_et.year, day_et.month, day_et.day,
                         _FALLBACK_START_H, 0, tzinfo=_ET).astimezone(timezone.utc)
        end = datetime(day_et.year, day_et.month, day_et.day,
                       _FALLBACK_END_H, 0, tzinfo=_ET).astimezone(timezone.utc)
        return start, end

    def is_polling_time(self, now_utc: datetime | None = None) -> bool:
        now_utc = now_utc or datetime.now(timezone.utc)
        bounds = self._session_bounds(now_utc.astimezone(_ET).date())
        return bounds is not None and bounds[0] <= now_utc <= bounds[1]

    def next_open(self, now_utc: datetime | None = None) -> datetime:
        """UTC time of the next extended-session start at or after ``now_utc``."""
        now_utc = now_utc or datetime.now(timezone.utc)
        day = now_utc.astimezone(_ET).date()
        for _ in range(10):  # scan forward at most ~10 days (covers long holidays)
            bounds = self._session_bounds(day)
            if bounds is not None and now_utc < bounds[1]:
                # Today's session hasn't ended: wake at its start (or now if mid-session).
                return max(bounds[0], now_utc) if now_utc < bounds[0] else now_utc
            day = day + timedelta(days=1)
        return now_utc  # pathological; poll rather than hang
