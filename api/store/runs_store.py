import uuid
from datetime import datetime, timezone
from threading import Lock
from api.models.run import RunConfig, RunResult, RunStatus
from typing import Optional, Literal


class RunsStore:
    def __init__(self):
        self._runs: dict[str, RunResult] = {}
        self._lock = Lock()

    def create(self, config: RunConfig) -> RunResult:
        run_id = str(uuid.uuid4())[:8]
        run = RunResult(
            id=run_id,
            ticker=config.ticker,
            date=config.date,
            status=RunStatus.QUEUED,
            created_at=datetime.now(timezone.utc).isoformat(),
            config=config,
        )
        with self._lock:
            self._runs[run_id] = run
        return run

    def get(self, run_id: str) -> Optional[RunResult]:
        return self._runs.get(run_id)

    def list_all(self) -> list[RunResult]:
        return list(self._runs.values())

    def update_status(self, run_id: str, status: RunStatus) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id] = self._runs[run_id].model_copy(
                    update={"status": status}
                )

    def update_decision(
        self, run_id: str, decision: Literal["BUY", "SELL", "HOLD"]
    ) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id] = self._runs[run_id].model_copy(
                    update={"decision": decision}
                )

    def add_report(self, run_id: str, step: str, report: str) -> None:
        with self._lock:
            if run_id in self._runs:
                reports = dict(self._runs[run_id].reports)
                reports[step] = report
                self._runs[run_id] = self._runs[run_id].model_copy(
                    update={"reports": reports}
                )

    def set_error(self, run_id: str, error: str) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id] = self._runs[run_id].model_copy(
                    update={"status": RunStatus.ERROR, "error": error}
                )
