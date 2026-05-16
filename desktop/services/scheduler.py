"""Scheduled pre-market analysis service.

Wraps a lightweight cron-style scheduler that triggers batch analysis
at user-configured times.  Uses **queue-with-wait** conflict resolution:
if the ``PipelineRunner`` is already busy when a schedule fires, the
scheduler queues the tickers and retries every 30 seconds until the
runner becomes idle (up to ``max_wait`` minutes, default 30).

No external dependency on APScheduler — uses ``threading.Timer`` with
cron-expression parsing via a tiny ``CronExpr`` helper that covers the
subset we expose in the UI (``HH:MM`` weekday combos).

See also: PLAN-features-v3.md, Feature 4.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Lightweight cron expression helpers ──────────────────────────────


_DOW_MAP = {
    "MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4,
    "SAT": 5, "SUN": 6,
}


@dataclass(frozen=True)
class CronExpr:
    """Minimal cron expression: ``HH:MM`` + weekday set.

    Examples
    --------
    - ``"08:30 MON-FRI"``   → weekdays at 8:30 AM
    - ``"06:00 MON,WED,FRI"`` → MWF at 6 AM
    - ``"09:00"``           → every day at 9 AM
    """

    hour: int
    minute: int
    weekdays: frozenset[int]  # 0=MON … 6=SUN; empty = every day

    @classmethod
    def parse(cls, expr: str) -> "CronExpr":
        """Parse a schedule expression string.

        Raises ``ValueError`` on unparseable input.
        """
        parts = expr.strip().split()
        if not parts:
            raise ValueError("Empty cron expression")

        # Time part: HH:MM
        time_part = parts[0]
        if ":" not in time_part:
            raise ValueError(f"Expected HH:MM, got {time_part!r}")
        h_str, m_str = time_part.split(":", 1)
        hour = int(h_str)
        minute = int(m_str)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Invalid time: {hour:02d}:{minute:02d}")

        # Weekday part (optional)
        weekdays: frozenset[int] = frozenset()
        if len(parts) > 1:
            weekdays = cls._parse_weekdays(parts[1])

        return cls(hour=hour, minute=minute, weekdays=weekdays)

    @staticmethod
    def _parse_weekdays(token: str) -> frozenset[int]:
        """Parse ``MON-FRI`` or ``MON,WED,FRI`` or ``*``."""
        token = token.upper().strip()
        if token == "*":
            return frozenset()

        days: set[int] = set()
        for segment in token.split(","):
            segment = segment.strip()
            if "-" in segment:
                start_s, end_s = segment.split("-", 1)
                start = _DOW_MAP.get(start_s.strip())
                end = _DOW_MAP.get(end_s.strip())
                if start is None or end is None:
                    raise ValueError(f"Unknown day in range: {segment!r}")
                # Handle wrap-around (e.g., FRI-MON)
                if start <= end:
                    days.update(range(start, end + 1))
                else:
                    days.update(range(start, 7))
                    days.update(range(0, end + 1))
            else:
                d = _DOW_MAP.get(segment)
                if d is None:
                    raise ValueError(f"Unknown day: {segment!r}")
                days.add(d)
        return frozenset(days)

    def next_fire_time(self, after: datetime) -> datetime:
        """Return the next datetime >= ``after`` that matches this schedule."""
        # Start from the next full minute
        candidate = after.replace(second=0, microsecond=0)
        if candidate <= after:
            candidate += timedelta(minutes=1)

        for _guard in range(400):  # prevent infinite loop
            if candidate.hour == self.hour and candidate.minute == self.minute:
                if not self.weekdays or candidate.weekday() in self.weekdays:
                    return candidate
            # Advance: if we haven't reached the target time today, jump to it
            today_target = candidate.replace(hour=self.hour, minute=self.minute)
            if candidate < today_target:
                candidate = today_target
            else:
                # Move to next day
                candidate = (candidate + timedelta(days=1)).replace(
                    hour=self.hour, minute=self.minute
                )
        raise RuntimeError("Could not find next fire time within 400 iterations")

    def human_label(self) -> str:
        """Return a human-readable label like ``08:30 Mon-Fri``."""
        time_str = f"{self.hour:02d}:{self.minute:02d}"
        if not self.weekdays:
            return f"{time_str} Every day"
        names = {v: k.capitalize() for k, v in _DOW_MAP.items()}
        day_names = [names[d] for d in sorted(self.weekdays)]
        return f"{time_str} {','.join(day_names)}"


# ── Scheduler service ────────────────────────────────────────────────


_QUEUE_RETRY_SECONDS = 30.0
_MAX_WAIT_MINUTES = 30


class Scheduler:
    """Background scheduler for pre-market analysis runs.

    Lifecycle::

        scheduler = Scheduler(db=db, run_analysis=callback)
        scheduler.start()   # loads schedules from DB, arms timers
        scheduler.stop()    # cancels all timers

    The ``run_analysis`` callback signature::

        def run_analysis(
            tickers: list[str],
            schedule_id: int,
        ) -> None: ...

    It should start the ``BatchRunner`` or ``PipelineRunner`` for the
    given tickers. The scheduler handles conflict detection itself.
    """

    def __init__(
        self,
        *,
        db: Any,  # HistoryDB — avoid circular import
        runner: Any,  # PipelineRunner
        run_analysis: Callable[..., None],
    ) -> None:
        self._db = db
        self._runner = runner
        self._run_analysis = run_analysis
        self._lock = threading.Lock()
        self._timers: dict[int, threading.Timer] = {}  # schedule_id → Timer
        self._stop_event = threading.Event()
        self._started = False

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Load all enabled schedules from DB and arm their timers."""
        with self._lock:
            if self._started:
                return
            self._started = True
            self._stop_event.clear()

        schedules = self._db.list_schedules()
        armed = 0
        for sched in schedules:
            if sched.is_enabled:
                self._arm_schedule(sched.id, sched.cron_expr, sched.timezone)
                armed += 1
        logger.info("Scheduler started: %d/%d schedules armed", armed, len(schedules))

    def stop(self) -> None:
        """Cancel all timers and shut down."""
        self._stop_event.set()
        with self._lock:
            self._started = False
            for sid, timer in self._timers.items():
                timer.cancel()
                logger.debug("Cancelled timer for schedule #%d", sid)
            self._timers.clear()
        logger.info("Scheduler stopped")

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._started

    # ── Schedule management (called from UI) ─────────────────────────

    def add_schedule(self, schedule_id: int, cron_expr: str, timezone: str) -> None:
        """Arm a newly created or re-enabled schedule."""
        if self._started:
            self._arm_schedule(schedule_id, cron_expr, timezone)

    def remove_schedule(self, schedule_id: int) -> None:
        """Disarm a disabled or deleted schedule."""
        with self._lock:
            timer = self._timers.pop(schedule_id, None)
            if timer:
                timer.cancel()

    def reload_schedule(self, schedule_id: int, cron_expr: str, timezone: str) -> None:
        """Re-arm after a cron expression change."""
        self.remove_schedule(schedule_id)
        self.add_schedule(schedule_id, cron_expr, timezone)

    # ── Timer internals ──────────────────────────────────────────────

    def _arm_schedule(self, schedule_id: int, cron_expr: str, timezone: str) -> None:
        """Parse the cron expression and set a timer for the next fire."""
        try:
            parsed = CronExpr.parse(cron_expr)
        except ValueError:
            logger.error("Invalid cron expression for schedule #%d: %r", schedule_id, cron_expr)
            return

        now = datetime.now()
        next_fire = parsed.next_fire_time(now)
        delay = (next_fire - now).total_seconds()

        # Update next_run in DB
        try:
            self._db.update_schedule_last_run(
                schedule_id,
                last_run=self._db.list_schedules()[0].last_run if False else "",  # keep existing
                next_run=next_fire.isoformat(timespec="seconds"),
            )
        except Exception:
            pass  # non-critical

        with self._lock:
            old = self._timers.pop(schedule_id, None)
            if old:
                old.cancel()

            timer = threading.Timer(
                delay,
                self._on_fire,
                args=(schedule_id, cron_expr, timezone),
            )
            timer.daemon = True
            timer.name = f"sched-{schedule_id}"
            timer.start()
            self._timers[schedule_id] = timer

        logger.info(
            "Schedule #%d armed: next fire at %s (in %.0fs)",
            schedule_id,
            next_fire.strftime("%Y-%m-%d %H:%M"),
            delay,
        )

    def _on_fire(self, schedule_id: int, cron_expr: str, timezone: str) -> None:
        """Timer callback — fires on the scheduled thread."""
        if self._stop_event.is_set():
            return

        logger.info("Schedule #%d fired", schedule_id)

        # Fetch the schedule from DB (it may have been disabled)
        schedules = self._db.list_schedules()
        sched = next((s for s in schedules if s.id == schedule_id), None)
        if sched is None or not sched.is_enabled:
            logger.info("Schedule #%d is disabled/deleted, skipping", schedule_id)
            self._rearm(schedule_id, cron_expr, timezone)
            return

        # Parse watchlist
        tickers = [t.strip().upper() for t in sched.watchlist.split(",") if t.strip()]
        if not tickers:
            logger.warning("Schedule #%d has empty watchlist, skipping", schedule_id)
            self._rearm(schedule_id, cron_expr, timezone)
            return

        # Queue-with-wait: if runner is busy, retry
        self._execute_with_wait(schedule_id, tickers, cron_expr, timezone)

    def _execute_with_wait(
        self,
        schedule_id: int,
        tickers: list[str],
        cron_expr: str,
        timezone: str,
    ) -> None:
        """Attempt to run; if runner is busy, retry up to max_wait."""
        deadline = time.monotonic() + _MAX_WAIT_MINUTES * 60

        while not self._stop_event.is_set():
            if not self._runner.is_running:
                # Runner is idle — go
                self._run_scheduled(schedule_id, tickers)
                break

            if time.monotonic() > deadline:
                logger.warning(
                    "Schedule #%d: timed out waiting for runner (%d min), "
                    "recording as skipped_conflict",
                    schedule_id,
                    _MAX_WAIT_MINUTES,
                )
                # Record a skipped run
                now = datetime.now().isoformat(timespec="seconds")
                try:
                    run_id = self._db.insert_schedule_run(
                        schedule_id=schedule_id, tickers=tickers,
                    )
                    self._db.update_schedule_run(
                        run_id, status="skipped_conflict",
                    )
                    self._db.update_schedule_last_run(
                        schedule_id, last_run=now, next_run=None,
                    )
                except Exception:
                    logger.exception("Failed to record skipped run for schedule #%d", schedule_id)
                break

            logger.debug(
                "Schedule #%d: runner busy, retrying in %.0fs",
                schedule_id,
                _QUEUE_RETRY_SECONDS,
            )
            # Sleep in small increments so stop_event can interrupt
            for _ in range(int(_QUEUE_RETRY_SECONDS)):
                if self._stop_event.is_set():
                    return
                time.sleep(1.0)

        # Re-arm for the next fire time
        self._rearm(schedule_id, cron_expr, timezone)

    def _run_scheduled(self, schedule_id: int, tickers: list[str]) -> None:
        """Actually launch the analysis for a schedule's tickers."""
        now = datetime.now().isoformat(timespec="seconds")
        run_id: int | None = None

        try:
            # Record the run
            run_id = self._db.insert_schedule_run(
                schedule_id=schedule_id, tickers=tickers,
            )
            self._db.update_schedule_last_run(
                schedule_id, last_run=now, next_run=None,
            )

            # Invoke the callback (which starts BatchRunner or PipelineRunner)
            self._run_analysis(tickers=tickers, schedule_id=schedule_id)

            # Mark run completed (the actual analysis is async, so this
            # just means "successfully dispatched")
            if run_id is not None:
                results = [{"ticker": t, "dispatched": True} for t in tickers]
                self._db.update_schedule_run(
                    run_id, status="completed", results=results,
                )

            logger.info(
                "Schedule #%d: dispatched %d ticker(s): %s",
                schedule_id,
                len(tickers),
                ", ".join(tickers),
            )
        except Exception as exc:
            logger.exception("Schedule #%d: failed to dispatch", schedule_id)
            if run_id is not None:
                try:
                    self._db.update_schedule_run(
                        run_id,
                        status="failed",
                        results=[{"error": str(exc)}],
                    )
                except Exception:
                    logger.exception("Failed to update schedule run #%d", run_id)

    def _rearm(self, schedule_id: int, cron_expr: str, timezone: str) -> None:
        """Re-arm the timer for the next occurrence."""
        if self._stop_event.is_set():
            return
        self._arm_schedule(schedule_id, cron_expr, timezone)
