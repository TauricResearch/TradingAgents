from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from tradingagents_service.runner.types import ShadowRunRequest, ShadowRunResult
from tradingagents_service.worker.loop import run_worker_loop
from tradingagents_service.worker.types import QueuedShadowJob


@dataclass
class _RepoStub:
    job: QueuedShadowJob
    stop_event: asyncio.Event
    marked_succeeded: int = 0
    marked_failed: int = 0
    marked_running: int = 0
    claim_failures_remaining: int = 0

    async def claim_next(self, *, worker_id: str) -> QueuedShadowJob | None:
        if self.claim_failures_remaining > 0:
            self.claim_failures_remaining -= 1
            raise RuntimeError("temporary database pressure")
        if self.marked_running == 0:
            return self.job
        self.stop_event.set()
        return None

    async def mark_running(self, *, job_id: str, worker_id: str) -> None:
        self.marked_running += 1

    async def mark_succeeded(self, *, job_id: str, result: ShadowRunResult) -> None:
        self.marked_succeeded += 1

    async def mark_failed(self, *, job_id: str, error_message: str) -> None:
        self.marked_failed += 1


@dataclass
class _EventSinkStub:
    fail_on_event_type: str | None = None
    emitted: list[str] | None = None
    payloads: list[dict | None] | None = None

    def __post_init__(self) -> None:
        if self.emitted is None:
            self.emitted = []
        if self.payloads is None:
            self.payloads = []

    async def emit(self, *, job_id: str, event_type: str, payload: dict | None = None) -> None:
        self.emitted.append(event_type)
        self.payloads.append(payload)
        if self.fail_on_event_type == event_type:
            raise RuntimeError(f"emit failed: {event_type}")


def _make_job() -> QueuedShadowJob:
    return QueuedShadowJob(
        job_id="11111111-1111-1111-1111-111111111111",
        request=ShadowRunRequest(
            ticker="NVDA",
            trade_date="2026-01-15",
            selected_analysts=["market"],
            provider="ollama",
            deep_model="llama3.2:latest",
            quick_model="llama3.2:latest",
        ),
    )


def _make_result() -> ShadowRunResult:
    return ShadowRunResult(
        ticker="NVDA",
        trade_date="2026-01-15",
        decision="Hold",
        final_trade_decision="hold",
        state_log_dir="output/logs/r1",
        memory_log_path="output/memory/trading_memory.md",
        provider="ollama",
        deep_model="llama3.2:latest",
        quick_model="llama3.2:latest",
        artifacts=[],
        quality={"status": "passed", "findings": [], "source_summary": {}},
    )


def test_succeeded_event_emit_failure_does_not_mark_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    stop_event = asyncio.Event()
    repo = _RepoStub(job=_make_job(), stop_event=stop_event)
    sink = _EventSinkStub(fail_on_event_type="succeeded")

    monkeypatch.setattr(
        "tradingagents_service.worker.loop.run_shadow_job",
        lambda request, artifact_store, progress_callback=None: _make_result(),
    )

    asyncio.run(
        run_worker_loop(
            repository=repo,
            event_sink=sink,
            worker_id="worker-1",
            poll_interval_seconds=0.01,
            stop_event=stop_event,
        )
    )

    assert repo.marked_succeeded == 1
    assert repo.marked_failed == 0
    assert "succeeded" in sink.emitted


def test_failed_event_emit_failure_does_not_crash_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    stop_event = asyncio.Event()
    repo = _RepoStub(job=_make_job(), stop_event=stop_event)
    sink = _EventSinkStub(fail_on_event_type="failed")

    def _raise_job_error(request, artifact_store, progress_callback=None):
        raise RuntimeError("runner exploded")

    monkeypatch.setattr("tradingagents_service.worker.loop.run_shadow_job", _raise_job_error)

    asyncio.run(
        run_worker_loop(
            repository=repo,
            event_sink=sink,
            worker_id="worker-1",
            poll_interval_seconds=0.01,
            stop_event=stop_event,
        )
    )

    assert repo.marked_succeeded == 0
    assert repo.marked_failed == 1
    assert "failed" in sink.emitted


def test_claim_failure_retries_without_exiting_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    stop_event = asyncio.Event()
    repo = _RepoStub(job=_make_job(), stop_event=stop_event, claim_failures_remaining=1)
    sink = _EventSinkStub()

    monkeypatch.setattr(
        "tradingagents_service.worker.loop.run_shadow_job",
        lambda request, artifact_store, progress_callback=None: _make_result(),
    )

    asyncio.run(
        run_worker_loop(
            repository=repo,
            event_sink=sink,
            worker_id="worker-1",
            poll_interval_seconds=0.01,
            stop_event=stop_event,
        )
    )

    assert repo.marked_succeeded == 1
    assert repo.marked_failed == 0
    assert "running" in sink.emitted


def test_runtime_progress_callback_emits_stage_events(monkeypatch: pytest.MonkeyPatch) -> None:
    stop_event = asyncio.Event()
    repo = _RepoStub(job=_make_job(), stop_event=stop_event)
    sink = _EventSinkStub()

    def _run_job(request, artifact_store, progress_callback=None):
        progress_callback({"stage": "market_analyst", "status": "completed", "chars": 120})
        return _make_result()

    monkeypatch.setattr("tradingagents_service.worker.loop.run_shadow_job", _run_job)

    asyncio.run(
        run_worker_loop(
            repository=repo,
            event_sink=sink,
            worker_id="worker-1",
            poll_interval_seconds=0.01,
            stop_event=stop_event,
        )
    )

    assert "stage_progress" in sink.emitted
    payload = sink.payloads[sink.emitted.index("stage_progress")]
    assert payload["stage"] == "market_analyst"
    assert payload["status"] == "completed"
    assert payload["worker_id"] == "worker-1"
