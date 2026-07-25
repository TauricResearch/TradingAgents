"""Restart-safe analysis jobs with persisted SSE replay."""

from __future__ import annotations

import json
import logging
import re
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tradingagents.dataflows.errors import ProviderRateLimitedError
from tradingagents.domain import AnalysisJob, JobStatus, UsageRecord
from tradingagents.persistence import Database, Repository
from tradingagents.services.analysis_service import (
    AnalysisCancelledError,
    AnalysisService,
    discard_checkpoint,
)
from tradingagents.trust import assess_provider_rate_limited
from tradingagents.usage import BudgetExhaustedError, BudgetTracker

SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|token|secret|password)\s*[:=]?\s*\S+"
)
LOCAL_PATH_RE = re.compile(
    r"(?:(?:[A-Za-z]:\\\\)|/(?:home|Users|tmp|var|etc)/)[^\s,;]+"
)
logger = logging.getLogger(__name__)
TERMINAL_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
    JobStatus.INTERRUPTED,
    JobStatus.BUDGET_EXHAUSTED,
    JobStatus.PROVIDER_RATE_LIMITED,
}


class JobBusyError(RuntimeError):
    pass


class JobResumeError(RuntimeError):
    pass


class JobRetryError(RuntimeError):
    pass


class Job:
    def __init__(self, manager: JobManager, job_id: str):
        self.manager = manager
        self.id = job_id
        self.condition = threading.Condition()

    @property
    def record(self) -> AnalysisJob:
        record = self.manager.repository.get_job(self.id)
        if record is None:
            raise KeyError(self.id)
        return record

    @property
    def request(self) -> dict[str, Any]:
        return self.record.request

    @property
    def status(self) -> str:
        return self.record.status

    @property
    def result(self) -> dict[str, Any] | None:
        return self.record.result

    @property
    def error(self) -> dict[str, Any] | None:
        return self.record.error

    @property
    def cancel_requested(self) -> bool:
        return self.record.cancel_requested

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        self.manager.repository.append_event(self.id, event_type, data)
        self.manager.repository.trim_events(self.id, keep=self.manager.event_retention)
        with self.condition:
            self.condition.notify_all()

    def public(self) -> dict[str, Any]:
        record = self.record
        return {
            "job_id": record.id,
            "status": record.status,
            "result": record.result,
            "error": record.error,
            "report_id": record.report_id,
            "advice_id": record.advice_id,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "resumable": record.resumable,
            "retry_of_job_id": record.retry_of_job_id,
            "retry_attempt": record.retry_attempt,
            "request": record.request,
        }


class JobManager:
    def __init__(
        self,
        service: AnalysisService,
        max_active: int = 1,
        *,
        repository: Repository | None = None,
        event_retention: int = 512,
        checkpoint_validator: Callable[[AnalysisJob], bool] | None = None,
        completion_handler: Callable[[Job, dict[str, Any]], dict[str, str]] | None = None,
        budget_factory: Callable[[Job], BudgetTracker] | None = None,
        preflight: Callable[[Job, dict[str, Any]], dict[str, Any]] | None = None,
    ):
        self.service = service
        self.max_active = max_active
        self.event_retention = event_retention
        self.checkpoint_validator = checkpoint_validator or (lambda _job: False)
        self.completion_handler = completion_handler
        self.budget_factory = budget_factory
        self.preflight = preflight
        self._tempdir: tempfile.TemporaryDirectory[str] | None = None
        if repository is None:
            self._tempdir = tempfile.TemporaryDirectory(prefix="tradingagents-tests-")
            repository = Repository(Database(Path(self._tempdir.name) / "workspace.sqlite3"))
        self.repository = repository
        self.lock = threading.Lock()
        self.threads: dict[str, threading.Thread] = {}
        self._resume_requested: set[str] = set()
        self._shutdown_requested: set[str] = set()
        stale = [job for job in self.repository.list_jobs() if job.status in {"queued", "running", "cancelling"}]
        for record in stale:
            resumable = bool(self.checkpoint_validator(record))
            self.repository.update_job(
                record.id,
                JobStatus.INTERRUPTED,
                finished_at=datetime.now(UTC).isoformat(),
                resumable=resumable,
            )
            self.repository.append_event(
                record.id,
                "analysis.interrupted",
                {"status": "interrupted", "resumable": resumable},
            )
            logger.info(
                "analysis job recovered",
                extra={"job_id": record.id, "event": "analysis.interrupted"},
            )
        self.jobs = {record.id: Job(self, record.id) for record in self.repository.list_jobs()}

    def create(self, request: dict[str, Any]) -> Job:
        with self.lock:
            if self.repository.active_count() >= self.max_active:
                raise JobBusyError("Another analysis is already running")
            record = self.repository.create_job(request)
            job = Job(self, record.id)
            self.jobs[job.id] = job
            self._start(job)
        return job

    def _start(self, job: Job) -> None:
        thread = threading.Thread(
            target=self._run,
            args=(job,),
            daemon=True,
            name=f"analysis-{job.id[:8]}",
        )
        self.threads[job.id] = thread
        thread.start()

    def _run(self, job: Job) -> None:
        started = time.monotonic()
        now = datetime.now(UTC).isoformat()
        self.repository.update_job(job.id, JobStatus.RUNNING, started_at=now, resumable=False)
        try:
            execution_request = dict(job.request)
            execution_request["_resume_checkpoint"] = job.id in self._resume_requested
            if self.preflight:
                execution_request = self.preflight(job, execution_request)
            tracker = self.budget_factory(job) if self.budget_factory else None
            if tracker:
                tracker.validate_depth(int(job.request.get("research_depth", 1)))
                with tracker.activate():
                    result = self.service.execute(execution_request, job.emit, lambda: job.cancel_requested)
            else:
                result = self.service.execute(execution_request, job.emit, lambda: job.cancel_requested)
            if job.cancel_requested:
                raise AnalysisCancelledError
            artifacts = self.completion_handler(job, result) if self.completion_handler else {}
            self.repository.update_job(
                job.id,
                JobStatus.COMPLETED,
                result=result,
                report_id=artifacts.get("report_id"),
                advice_id=artifacts.get("advice_id"),
                finished_at=datetime.now(UTC).isoformat(),
            )
            job.emit("analysis.completed", {"status": "completed", "result": result, **artifacts})
            logger.info(
                "analysis completed",
                extra={
                    "job_id": job.id,
                    "advice_id": artifacts.get("advice_id"),
                    "event": "analysis.completed",
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "provider": job.request.get("llm_provider"),
                    "model": job.request.get("deep_model"),
                },
            )
        except AnalysisCancelledError:
            if job.id in self._shutdown_requested:
                resumable = bool(self.checkpoint_validator(job.record))
                self.repository.update_job(
                    job.id,
                    JobStatus.INTERRUPTED,
                    finished_at=datetime.now(UTC).isoformat(),
                    resumable=resumable,
                )
                job.emit(
                    "analysis.interrupted",
                    {"status": "interrupted", "resumable": resumable},
                )
            else:
                discard_checkpoint(job.request)
                self.repository.update_job(
                    job.id,
                    JobStatus.CANCELLED,
                    finished_at=datetime.now(UTC).isoformat(),
                )
                job.emit("analysis.cancelled", {"status": "cancelled"})
        except BudgetExhaustedError as exc:
            result = exc.partial_result
            artifacts = self.completion_handler(job, result) if self.completion_handler else {}
            error = {"code": exc.code, "message": exc.reason}
            self.repository.update_job(
                job.id,
                JobStatus.BUDGET_EXHAUSTED,
                result=result,
                error=error,
                report_id=artifacts.get("report_id"),
                advice_id=artifacts.get("advice_id"),
                finished_at=datetime.now(UTC).isoformat(),
            )
            job.emit(
                "analysis.budget_exhausted",
                {"status": "budget_exhausted", "error": error, "result": result, **artifacts},
            )
            logger.warning(
                "analysis budget exhausted",
                extra={
                    "job_id": job.id,
                    "event": "analysis.budget_exhausted",
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "safe_error_code": exc.code,
                },
            )
        except ProviderRateLimitedError as exc:
            error = exc.public_detail()
            self.repository.add_usage(
                UsageRecord(
                    str(uuid.uuid4()),
                    job.id,
                    None,
                    str(job.request.get("llm_provider") or "unknown"),
                    str(job.request.get("deep_model") or "unknown"),
                    0,
                    0,
                    0,
                    0,
                    int((time.monotonic() - started) * 1000),
                    JobStatus.PROVIDER_RATE_LIMITED,
                    "Yahoo Finance was rate limited before any CIII request was made.",
                    datetime.now(UTC).isoformat(),
                )
            )
            self.repository.add_trust(
                assess_provider_rate_limited(job_id=job.id, observed_at=exc.observed_at)
            )
            self.repository.update_job(
                job.id,
                JobStatus.PROVIDER_RATE_LIMITED,
                error=error,
                finished_at=datetime.now(UTC).isoformat(),
            )
            job.emit("analysis.provider_rate_limited", {"status": "provider_rate_limited", "error": error})
            logger.warning(
                "analysis provider rate limited",
                extra={
                    "job_id": job.id,
                    "event": "analysis.provider_rate_limited",
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "provider": exc.provider,
                    "cache_status": exc.cache_status,
                },
            )
        except Exception as exc:  # noqa: BLE001 - application boundary redacts failures
            safe = LOCAL_PATH_RE.sub("[local path]", SECRET_RE.sub("[redacted]", str(exc)))[:300]
            error = {"code": "ANALYSIS_FAILED", "message": safe or "Analysis failed"}
            self.repository.update_job(
                job.id,
                JobStatus.FAILED,
                error=error,
                finished_at=datetime.now(UTC).isoformat(),
            )
            job.emit("analysis.failed", error)
            logger.error(
                "analysis failed",
                extra={
                    "job_id": job.id,
                    "event": "analysis.failed",
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "safe_error_code": error["code"],
                },
            )
        finally:
            self._resume_requested.discard(job.id)
            self._shutdown_requested.discard(job.id)
            with job.condition:
                job.condition.notify_all()

    def get(self, job_id: str) -> Job | None:
        if self.repository.get_job(job_id) is None:
            return None
        return self.jobs.setdefault(job_id, Job(self, job_id))

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return [self.get(record.id).public() for record in self.repository.list_jobs(limit=limit)]

    def cancel(self, job: Job) -> None:
        if job.status in TERMINAL_STATUSES:
            return
        self.repository.update_job(job.id, JobStatus.CANCELLING, cancel_requested=True)
        with job.condition:
            job.condition.notify_all()

    def resume(self, job: Job) -> None:
        record = job.record
        if record.status != JobStatus.INTERRUPTED:
            raise JobResumeError("Only interrupted jobs can be resumed")
        if not record.resumable or not self.checkpoint_validator(record):
            raise JobResumeError("No valid checkpoint matches this run signature")
        with self.lock:
            if self.repository.active_count() >= self.max_active:
                raise JobBusyError("Another analysis is already running")
            self.repository.update_job(
                job.id,
                JobStatus.QUEUED,
                cancel_requested=False,
                finished_at=None,
                error=None,
                resumable=False,
            )
            self._resume_requested.add(job.id)
            job.emit("analysis.resumed", {"status": "queued"})
            self._start(job)

    def retry(self, job: Job) -> Job:
        record = job.record
        if record.status != JobStatus.PROVIDER_RATE_LIMITED:
            raise JobRetryError("Only provider-rate-limited jobs can be retried")
        with self.lock:
            if self.repository.active_count() >= self.max_active:
                raise JobBusyError("Another analysis is already running")
            child_record = self.repository.create_job(
                record.request,
                retry_of_job_id=record.id,
                retry_attempt=record.retry_attempt + 1,
            )
            child = Job(self, child_record.id)
            self.jobs[child.id] = child
            self._start(child)
        return child

    def event_stream(self, job: Job, last_id: int = 0):
        cursor = last_id
        while True:
            available = self.repository.list_events(job.id, after=cursor)
            if not available and job.status not in TERMINAL_STATUSES:
                with job.condition:
                    job.condition.wait(timeout=15)
                available = self.repository.list_events(job.id, after=cursor)
            if not available:
                if job.status in TERMINAL_STATUSES:
                    return
                yield ": heartbeat\n\n"
                continue
            for event in available:
                cursor = event.event_id
                payload = json.dumps(
                    {
                        "id": event.event_id,
                        "job_id": event.job_id,
                        "type": event.event_type,
                        "timestamp": event.timestamp,
                        "data": event.data,
                    },
                    ensure_ascii=False,
                    default=str,
                )
                yield f"id: {cursor}\nevent: {event.event_type}\ndata: {payload}\n\n"

    def shutdown(self, timeout: float = 5.0) -> None:
        for record in self.repository.list_jobs():
            if record.status in {"queued", "running", "cancelling"}:
                self._shutdown_requested.add(record.id)
                self.repository.update_job(record.id, JobStatus.CANCELLING, cancel_requested=True)
        deadline = datetime.now().timestamp() + timeout
        for thread in list(self.threads.values()):
            thread.join(max(0.0, deadline - datetime.now().timestamp()))
        for record in self.repository.list_jobs():
            if record.status in {"queued", "running", "cancelling"}:
                self.repository.update_job(
                    record.id,
                    JobStatus.INTERRUPTED,
                    finished_at=datetime.now(UTC).isoformat(),
                )
