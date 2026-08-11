import logging
import os
import sys
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone

from tradingagents.automation import AutomationCycleService, AutomationSettings
from tradingagents.automation_state import AutomationState
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.execution import AlpacaBroker
from tradingagents.graph.trading_graph import TradingAgentsGraph

logger = logging.getLogger(__name__)


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
    ) -> None:
        if not force and due_time < self._deadline(task, interval_minutes, due_time):
            return
        try:
            if not self.state.try_acquire_lease(
                task,
                self._owner,
                due_time,
                interval_minutes * 60,
            ):
                self._deferred_until[task] = due_time + timedelta(seconds=60)
                return
            operation(due_time)
            self.state.mark_task_run(task, due_time)
        except Exception:
            self._deferred_until[task] = due_time + timedelta(minutes=interval_minutes)
            logger.exception("Automation %s task failed", task)
        else:
            self._deferred_until.pop(task, None)

    def _deadline(self, task: str, interval_minutes: int, now: datetime) -> datetime:
        last_run = self.state.last_task_run(task)
        deadline = now if last_run is None else last_run + timedelta(minutes=interval_minutes)
        deferred_until = self._deferred_until.get(task)
        if deferred_until is not None and deferred_until > deadline:
            return deferred_until
        return deadline

    def _sleep_seconds(self, now: datetime) -> float:
        deadlines = (
            self._deadline("analysis", self.service.settings.analysis_interval_minutes, now),
            self._deadline("positions", self.service.settings.position_interval_minutes, now),
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
