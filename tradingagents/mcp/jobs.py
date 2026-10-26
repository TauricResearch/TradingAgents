"""Background jobs for the MCP server.

An analysis takes minutes, longer than many MCP clients allow one tool call to
block. Tools therefore start a job and return its id at once; the client polls
``get_job_status`` and fetches ``get_job_result`` when the job finishes.

Workers are daemon threads rather than a ``ThreadPoolExecutor``: a client can
close the server while a job is still running, and the process should not wait
for a paid-for analysis nobody is listening to. Cancellation is cooperative:
a running job checks the flag between graph steps.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


class JobCancelled(Exception):
    """Raised inside a job when its cancellation was requested."""


class JobNotFound(KeyError):
    """Raised when a job id is unknown to this server process."""


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("Ignoring %s=%r; expected a positive integer", name, raw)
        return default


def _iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


@dataclass
class Job:
    """One unit of background work and everything a client may ask about it."""

    id: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"
    stage: str = "queued"
    detail: str = ""
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_requested: bool = False
    _done: threading.Event = field(default_factory=threading.Event, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **fields: Any) -> None:
        with self._lock:
            for key, value in fields.items():
                setattr(self, key, value)

    def start(self) -> None:
        with self._lock:
            self.status = "running"
            self.stage = "starting"
            self.started_at = time.time()

    def finish(
        self,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            if self.status in TERMINAL_STATUSES:
                return
            self.status = status
            self.result = result
            self.error = error
            self.finished_at = time.time()
            if status == "succeeded":
                self.stage = "finished"
                self.progress = 100.0
            elif status == "cancelled":
                self.stage = "cancelled"
            else:
                self.stage = "failed"
            self._done.set()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            end = self.finished_at or (time.time() if self.started_at else None)
            duration = (end - self.started_at) if self.started_at and end else None
            data = {
                "job_id": self.id,
                "kind": self.kind,
                "status": self.status,
                "stage": self.stage,
                "detail": self.detail,
                "progress_percent": round(self.progress, 1),
                "created_at": _iso(self.created_at),
                "started_at": _iso(self.started_at),
                "finished_at": _iso(self.finished_at),
                "duration_seconds": round(duration, 1) if duration is not None else None,
                "error": self.error,
                "result_ready": self.status == "succeeded",
                "cancel_requested": self.cancel_requested,
            }
            for key in (
                "ticker",
                "trade_date",
                "asset_type",
                "analysts",
                "tickers",
                "start_date",
                "end_date",
                "every_n_days",
                "run_id",
            ):
                if key in self.params:
                    value = self.params[key]
                    data[key] = list(value) if isinstance(value, tuple) else value
            if self.result is not None:
                data["result"] = dict(self.result)
            return data


class JobManager:
    """A small FIFO worker pool holding job state in this process."""

    def __init__(self, max_workers: int | None = None, max_jobs: int | None = None):
        self.max_workers = max_workers or _env_int("TRADINGAGENTS_MCP_MAX_WORKERS", 1)
        self.max_jobs = max_jobs or _env_int("TRADINGAGENTS_MCP_MAX_JOBS", 20)
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()
        self._queue: queue.Queue[tuple[Job, Callable[[Job], dict[str, Any]]] | None] = queue.Queue()
        for index in range(self.max_workers):
            threading.Thread(
                target=self._worker,
                name=f"tradingagents-mcp-worker-{index}",
                daemon=True,
            ).start()

    def submit(
        self,
        kind: str,
        runner: Callable[[Job], dict[str, Any]],
        **params: Any,
    ) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, params=params)
        with self._lock:
            active = sum(
                1 for existing in self._jobs.values() if existing.status not in TERMINAL_STATUSES
            )
            if active >= self.max_jobs:
                raise RuntimeError(
                    f"too many active jobs (max {self.max_jobs}); wait for one to finish"
                )
            self._jobs[job.id] = job
            self._prune_locked()
        self._queue.put((job, runner))
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFound(job_id)
        return job

    def list(self, limit: int = 20, status: str | None = None) -> list[Job]:
        with self._lock:
            jobs = list(reversed(self._jobs.values()))
        if status:
            jobs = [job for job in jobs if job.status == status]
        return jobs[: max(1, limit)]

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        with job._lock:
            if job.status in TERMINAL_STATUSES:
                return job
            job.cancel_requested = True
            if job.status == "queued":
                job.status = "cancelled"
                job.stage = "cancelled"
                job.error = "Cancelled before it started."
                job.finished_at = time.time()
                job._done.set()
        return job

    def wait(self, job_id: str, timeout: float | None = None) -> bool:
        return self.get(job_id)._done.wait(timeout)

    def stats(self) -> dict[str, int]:
        with self._lock:
            jobs = list(self._jobs.values())
        counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0, "cancelled": 0}
        for job in jobs:
            counts[job.status] = counts.get(job.status, 0) + 1
        counts["retained"] = len(jobs)
        return counts

    def shutdown(self) -> None:
        """Wake the workers so a clean shutdown does not wait on the queue."""
        for _ in range(self.max_workers):
            self._queue.put(None)

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            job, runner = item
            try:
                if job.cancel_requested:
                    job.finish("cancelled", error="Cancelled before it started.")
                    continue
                job.start()
                try:
                    result = runner(job)
                except JobCancelled:
                    job.finish("cancelled", error="Cancelled by the client.")
                except Exception as exc:
                    logger.exception("Job %s (%s) failed", job.id, job.kind)
                    job.finish("failed", error=f"{type(exc).__name__}: {exc}")
                else:
                    job.finish("succeeded", result=result)
            finally:
                self._queue.task_done()
                with self._lock:
                    self._prune_locked()

    def _prune_locked(self) -> None:
        """Keep the most recent terminal jobs; running jobs are never dropped."""
        terminal = [job for job in self._jobs.values() if job.status in TERMINAL_STATUSES]
        excess = len(terminal) - self.max_jobs
        for job in terminal[: max(0, excess)]:
            self._jobs.pop(job.id, None)
