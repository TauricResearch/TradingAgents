import logging
import os
import sqlite3
import sys
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone

from tradingagents.automation import (
    AutomationCycleService,
    AutomationSettings,
    CycleResult,
    OptionCycleResult,
)
from tradingagents.automation_state import AutomationState
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.execution import AlpacaBroker
from tradingagents.graph.trading_graph import TradingAgentsGraph

logger = logging.getLogger(__name__)
MAX_HEARTBEAT_SECONDS = 60.0


class _LeaseHeartbeat:
    def __init__(
        self,
        path,
        task: str,
        owner: str,
        ttl_seconds: int,
        now: Callable[[], datetime],
    ) -> None:
        self._path = path
        self._task = task
        self._owner = owner
        self._ttl_seconds = ttl_seconds
        self._now = now
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> bool:
        self._stop.set()
        self._thread.join()
        if self._error is not None:
            raise self._error
        return self._lost.is_set()

    def _run(self) -> None:
        interval = min(MAX_HEARTBEAT_SECONDS, self._ttl_seconds / 3)
        try:
            with AutomationState(self._path) as state:
                while not self._stop.wait(interval):
                    if not state.renew_lease(
                        self._task,
                        self._owner,
                        self._now(),
                        self._ttl_seconds,
                    ):
                        self._lost.set()
                        logger.error("Automation %s lease ownership was lost", self._task)
                        return
        except sqlite3.Error:
            self._lost.set()
            logger.exception("Automation %s lease heartbeat failed", self._task)
        except Exception as error:
            self._lost.set()
            self._error = error


class AutomationScheduler:
    def __init__(
        self,
        service: AutomationCycleService,
        state: AutomationState,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.service = service
        self.state = state
        self._now = now
        self._sleep = sleep
        self._owner = f"{os.getpid()}-{uuid.uuid4().hex}"
        self._deferred_until: dict[str, datetime] = {}

    def run_once(self, now: datetime | None = None, force_analysis: bool = False) -> None:
        due_time = self._now() if now is None else now
        if due_time.tzinfo is None or due_time.utcoffset() is None:
            raise ValueError("scheduler timestamp must be timezone-aware")
        self._run_task(
            "analysis",
            self.service.settings.analysis_interval_minutes,
            self.service.run_analysis_cycle,
            due_time,
            force=force_analysis,
        )
        self._run_task(
            "positions",
            self.service.settings.position_interval_minutes,
            self.service.track_positions,
            due_time,
        )
        self._run_task(
            "options",
            15,
            self.service.manage_options,
            due_time,
            record_runtime=True,
        )

    def run_forever(self) -> None:
        try:
            while True:
                due_time = self._now()
                self.run_once(now=due_time)
                self._sleep(self._sleep_seconds(self._now()))
        except KeyboardInterrupt:
            logger.info("Automation stopped by operator")

    def _run_task(
        self,
        task: str,
        interval_minutes: int,
        operation: Callable[[datetime], object],
        due_time: datetime,
        force: bool = False,
        record_runtime: bool = False,
    ) -> None:
        runtime_now = self._now()
        if runtime_now.tzinfo is None or runtime_now.utcoffset() is None:
            raise ValueError("scheduler runtime timestamp must be timezone-aware")
        runtime_time = max(due_time, runtime_now)
        if not force and runtime_time < self._deadline(task, interval_minutes, runtime_time):
            return
        ttl_seconds = interval_minutes * 60
        lease_time = runtime_time
        try:
            if not self.state.try_acquire_lease(
                task,
                self._owner,
                lease_time,
                ttl_seconds,
            ):
                self._deferred_until[task] = lease_time + timedelta(seconds=60)
                return
        except sqlite3.Error:
            self._deferred_until[task] = lease_time + timedelta(minutes=interval_minutes)
            logger.exception("Automation %s lease acquisition failed", task)
            return

        heartbeat = _LeaseHeartbeat(
            self.state.path,
            task,
            self._owner,
            ttl_seconds,
            self._now,
        )
        operation_error: Exception | None = None
        suppression_reason: str | None = None
        try:
            heartbeat.start()
            result = operation(due_time)
            if isinstance(result, CycleResult):
                suppression_reason = result.trade_suppressed_reason
                logger.info(
                    "Automation %s result cycle=%s analyzed=%s failed=%s submitted=%s outcome=%s",
                    task,
                    result.cycle_id,
                    ",".join(result.analyzed_symbols) or "none",
                    ",".join(result.failed_symbols) or "none",
                    ",".join(result.submitted_order_ids) or "none",
                    result.trade_suppressed_reason or "completed",
                )
            elif isinstance(result, OptionCycleResult):
                suppression_reason = result.suppressed_reason
                logger.info(
                    "Automation %s result cycle=%s intents=%s submitted=%s outcome=%s",
                    task,
                    result.cycle_id,
                    len(result.intents),
                    ",".join(result.submitted_order_ids) or "none",
                    result.suppressed_reason or "completed",
                )
        except Exception as error:
            operation_error = error
        finally:
            ownership_lost = heartbeat.stop()

        if operation_error is not None:
            failed_at = max(lease_time, self._now())
            self._deferred_until[task] = failed_at + timedelta(minutes=interval_minutes)
            logger.error(
                "Automation %s task failed",
                task,
                exc_info=(
                    type(operation_error),
                    operation_error,
                    operation_error.__traceback__,
                ),
            )
            return

        completed_at = max(lease_time, self._now())
        if ownership_lost:
            self._deferred_until[task] = completed_at + timedelta(minutes=interval_minutes)
            logger.error("Automation %s completion skipped after lease loss", task)
            return

        try:
            completed = self.state.complete_task_run(
                task,
                self._owner,
                ran_at=lease_time if record_runtime else due_time,
                completed_at=completed_at,
                suppression_reason=suppression_reason,
            )
        except sqlite3.Error:
            self._deferred_until[task] = completed_at + timedelta(minutes=interval_minutes)
            logger.exception("Automation %s completion failed", task)
            return
        if not completed:
            self._deferred_until[task] = completed_at + timedelta(minutes=interval_minutes)
            logger.error("Automation %s stale completion was rejected", task)
            return
        self._deferred_until.pop(task, None)

    def _deadline(self, task: str, interval_minutes: int, now: datetime) -> datetime:
        try:
            last_run = self.state.last_task_run(task)
        except sqlite3.Error:
            deferred_until = now + timedelta(minutes=interval_minutes)
            self._deferred_until[task] = deferred_until
            logger.exception("Automation %s deadline read failed", task)
            return deferred_until
        deadline = now if last_run is None else last_run + timedelta(minutes=interval_minutes)
        deferred_until = self._deferred_until.get(task)
        if deferred_until is not None and deferred_until > deadline:
            return deferred_until
        return deadline

    def _sleep_seconds(self, now: datetime) -> float:
        deadlines = (
            self._deadline("analysis", self.service.settings.analysis_interval_minutes, now),
            self._deadline("positions", self.service.settings.position_interval_minutes, now),
            self._deadline("options", 15, now),
        )
        seconds = min((deadline - now).total_seconds() for deadline in deadlines)
        return min(60, max(1, seconds))


def build_service_from_config(
    config: Mapping[str, object] | None = None,
) -> AutomationCycleService:
    resolved_config = DEFAULT_CONFIG if config is None else config
    settings = AutomationSettings.from_config(resolved_config)
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_SECRET_KEY")
    missing = [
        name
        for name, value in (
            ("ALPACA_API_KEY", key),
            ("ALPACA_SECRET_KEY", secret),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"missing required environment variables: {', '.join(missing)}")

    broker = AlpacaBroker(
        key,
        secret,
        settings.alpaca_mode,
        live_ack=settings.live_trading_ack,
        live_options_ack=settings.live_options_ack,
    )
    state = AutomationState(settings.state_path)

    def graph_factory(analysts: tuple[str, ...]):
        return TradingAgentsGraph(
            selected_analysts=analysts,
            config=dict(resolved_config),
        )

    return AutomationCycleService(settings, state, broker, graph_factory)


def run_batch_from_config() -> None:
    service = _build_service_with_error_output()
    try:
        AutomationScheduler(service, service.state).run_once(force_analysis=True)
    finally:
        service.state.close()


def run_automation_from_config() -> None:
    service = _build_service_with_error_output()
    try:
        AutomationScheduler(service, service.state).run_forever()
    finally:
        service.state.close()


def _build_service_with_error_output() -> AutomationCycleService:
    try:
        return build_service_from_config()
    except (RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise
