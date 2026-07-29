"""Single-process lifecycle contracts for the localhost run manager."""

from __future__ import annotations

import asyncio
import hashlib
import threading
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import pytest

import tradingagents.dataflows.interface as interface_module
import tradingagents.dataflows.progress as progress_module
from tradingagents.dataflows.config import get_config, set_config
from tradingagents.execution.models import AnalysisRequest, AnalysisResult
from tradingagents.observability.events import RunEventDraft
from tradingagents.observability.provenance import current_provenance_observer
from tradingagents.observability.roles import ROLE_REGISTRY
from tradingagents.web.broker import EventBroker
from tradingagents.web.manager import (
    ActiveRunConflict,
    RunNotResumable,
    SingleRunManager,
)
from tradingagents.web.run_models import RunSnapshot
from tradingagents.web.store import RunStore

pytestmark = pytest.mark.unit


def _request(ticker: str = "AAPL", **overrides: Any) -> AnalysisRequest:
    values: dict[str, Any] = {
        "ticker": ticker,
        "analysis_date": "2026-07-18",
        "asset_type": "stock",
        "selected_analysts": ("market", "fundamentals"),
        "max_debate_rounds": 2,
        "max_risk_discuss_rounds": 1,
        "effective_config": {
            "checkpoint_enabled": False,
            "llm_provider": "openai",
            "quick_think_llm": "quick-model",
            "deep_think_llm": "deep-model",
            "output_language": "Chinese",
            "manager_scope_marker": ticker,
        },
    }
    values.update(overrides)
    return AnalysisRequest(**values)


def _final_state(ticker: str = "AAPL") -> dict[str, Any]:
    return {
        "company_of_interest": ticker,
        "market_report": f"market report for {ticker}",
        "final_trade_decision": "Rating: Buy",
    }


class _ScriptedRunner:
    """A controllable AnalysisRunner stand-in with no timing-based polling."""

    def __init__(
        self,
        *,
        outcome: str = "success",
        release_immediately: bool = False,
        error: BaseException | None = None,
        on_enter=None,
        complete_roles: bool = True,
    ) -> None:
        self.outcome = outcome
        self.error = error or RuntimeError("provider failed")
        self.on_enter = on_enter
        self.complete_roles = complete_roles
        self.entered = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()
        self.calls: list[dict[str, Any]] = []
        self.scope_observations: list[dict[str, Any]] = []
        if release_immediately:
            self.release.set()

    def run(self, request: AnalysisRequest, **kwargs: Any) -> AnalysisResult:
        observation_context = kwargs["observation_context"]
        callbacks = kwargs["callbacks"]
        cancellation_token = kwargs["cancellation_token"]
        observer = observation_context.observer
        self.calls.append({"request": request, **kwargs})
        self.scope_observations.append(
            {
                "config": get_config(),
                "progress_sink": progress_module._progress_sink,
                "provenance_observer": current_provenance_observer(),
                "cache_namespace": interface_module._news_cache_namespace.get(),
                "context_observer": observer,
                "callback_observer": callbacks[0],
            }
        )
        if self.on_enter is not None:
            self.on_enter(observer)
        self.entered.set()
        try:
            assert self.release.wait(3), "test did not release the fake runner"
            if self.outcome == "cancel":
                cancellation_token.raise_if_cancelled(
                    {"market_report": "durable partial report"}
                )
                raise AssertionError("cancel outcome requires a cancelled token")
            if self.outcome == "failure":
                raise self.error
            if self.complete_roles:
                self._complete_role_cards(observer)
            return AnalysisResult(
                final_state=_final_state(request.ticker),
                final_signal="BUY",
            )
        finally:
            self.finished.set()

    @staticmethod
    def _complete_role_cards(observer: Any) -> None:
        latest: dict[str, str] = {}
        for event in observer.store.read_events(observer.run_id):
            if event.type == "role.status_changed" and event.actor_id:
                latest[event.actor_id] = event.payload["new_status"]
        for role in ROLE_REGISTRY:
            status = latest.get(role.actor_id)
            if status not in {"pending", "running"}:
                continue
            transitions = (
                (("pending", "running"), ("running", "completed"))
                if status == "pending"
                else (("running", "completed"),)
            )
            for previous, new in transitions:
                observer.emit(
                    RunEventDraft(
                        observer.run_id,
                        "role.status_changed",
                        {
                            "role_instance_id": f"{observer.run_id}:{role.actor_id}",
                            "previous_status": previous,
                            "new_status": new,
                            "reason": "scripted_success",
                        },
                        team_id=role.team_id,
                        actor_id=role.actor_id,
                        node_id=role.node_id,
                        status=new,
                    )
                )


class _RunnerFactory:
    def __init__(self, *runners: _ScriptedRunner) -> None:
        self.runners = deque(runners)
        self.calls: list[tuple[AnalysisRequest, Any]] = []
        self._lock = threading.Lock()

    def __call__(self, request: AnalysisRequest, observer: Any) -> _ScriptedRunner:
        with self._lock:
            self.calls.append((request, observer))
            if not self.runners:
                raise AssertionError("runner factory called more often than expected")
            return self.runners.popleft()


def _manager(tmp_path, *runners: _ScriptedRunner, **kwargs: Any):
    store = RunStore(tmp_path)
    broker = EventBroker(store)
    factory = _RunnerFactory(*runners)
    manager = SingleRunManager(
        store,
        broker,
        factory,
        **kwargs,
    )
    return manager, store, broker, factory


def _wait_for_entry(runner: _ScriptedRunner) -> None:
    assert runner.entered.wait(3), "background worker did not enter the runner"


def _event_types(store: RunStore, run_id: str) -> list[str]:
    return [event.type for event in store.read_events(run_id)]


def _persisted_run(
    store: RunStore,
    *,
    status: str,
    checkpoint_available: bool = False,
) -> RunSnapshot:
    snapshot = RunSnapshot.create(
        ticker="MSFT",
        analysis_date="2026-07-17",
        selected_analysts=("market", "fundamentals"),
        max_debate_rounds=2,
        max_risk_discuss_rounds=1,
        output_language="Chinese",
        llm_provider="openai",
        quick_think_llm="quick-model",
        deep_think_llm="deep-model",
        resume_fingerprint={"fingerprint_version": 1}
        if checkpoint_available
        else None,
        metadata={
            "checkpoint_available": checkpoint_available,
            "effective_config": {
                "checkpoint_enabled": checkpoint_available,
                "llm_provider": "openai",
                "quick_think_llm": "quick-model",
                "deep_think_llm": "deep-model",
                "output_language": "Chinese",
                "manager_scope_marker": "MSFT",
            },
        },
    )
    store.create_run(snapshot)
    if status == "created":
        return snapshot
    if status in {"running", "cancel_requested", "completed", "failed", "cancelled"}:
        store.append_event(
            RunEventDraft(
                snapshot.run_id,
                "run.started",
                {"run_status": "running"},
            )
        )
    if status == "cancel_requested":
        store.append_event(
            RunEventDraft(
                snapshot.run_id,
                "run.cancel_requested",
                {"run_status": "cancel_requested"},
            )
        )
    elif status == "failed":
        store.append_event(
            RunEventDraft(
                snapshot.run_id,
                "run.failed",
                {"run_status": "failed", "summary": "provider failure"},
            )
        )
    elif status == "cancelled":
        store.append_event(
            RunEventDraft(
                snapshot.run_id,
                "run.cancelled",
                {"run_status": "cancelled", "summary": "cancelled"},
            )
        )
    elif status == "completed":
        run_dir = store._run_dir(snapshot.run_id)
        reports = run_dir / "reports"
        reports.mkdir()
        (reports / "complete_report.md").write_text("complete", encoding="utf-8")
        timestamp = datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc)
        store.append_event(
            RunEventDraft(
                snapshot.run_id,
                "run.completed",
                {
                    "run_status": "completed",
                    "summary": "complete",
                    "final_signal": "Hold",
                    "final_report_artifact_id": (
                        "report-final:"
                        + hashlib.sha256(b"complete").hexdigest()
                    ),
                    "completed_at": "2026-07-22T09:30:00.000Z",
                    "degraded_data_sources": [],
                },
                timestamp=timestamp,
            )
        )
    return store.read_snapshot(snapshot.run_id)


def _emit_open_lifecycles(emit, run_id: str) -> None:
    relationships = {
        "turn_id": "turn_open",
        "graph_task_id": "task_open",
    }
    emit(
        RunEventDraft(
            run_id,
            "role.status_changed",
            {
                "role_instance_id": f"{run_id}:analyst.market",
                "previous_status": "pending",
                "new_status": "running",
                "reason": "turn_started",
                "turn_id": "turn_open",
            },
            actor_id="analyst.market",
            node_id="Market Analyst",
            status="running",
        )
    )
    emit(
        RunEventDraft(
            run_id,
            "turn.started",
            {
                **relationships,
                "role_instance_id": f"{run_id}:analyst.market",
                "graph_step": 1,
                "turn_index": 1,
                "turn_status": "started",
            },
            actor_id="analyst.market",
            node_id="Market Analyst",
            status="started",
        )
    )
    tool = {
        **relationships,
        "attempt_id": "attempt_open",
        "tool_call_id": "tool_open",
        "tool_name": "get_stock_data",
    }
    emit(
        RunEventDraft(
            run_id,
            "tool.requested",
            {**tool, "arguments": {"symbol": "AAPL"}},
            actor_id="analyst.market",
            node_id="Market Analyst",
            status="requested",
        )
    )
    emit(
        RunEventDraft(
            run_id,
            "tool.execution_started",
            {**tool, "tool_execution_id": "tool_execution_open"},
            actor_id="analyst.market",
            node_id="Market Analyst",
            status="started",
        )
    )
    emit(
        RunEventDraft(
            run_id,
            "data.progress",
            {
                **relationships,
                "tool_call_id": "tool_open",
                "vendor_call_id": "vendor_open",
                "method": "get_stock_data",
                "vendor": "yfinance",
                "stage": "request",
                "data_status": "progress",
            },
            actor_id="analyst.market",
            node_id="Market Analyst",
            status="progress",
        )
    )


def test_start_emits_run_then_all_13_role_cards_in_registry_order(tmp_path):
    runner = _ScriptedRunner()
    manager, store, _broker, _factory = _manager(tmp_path, runner)

    started = manager.start(_request())
    _wait_for_entry(runner)
    events = store.read_events(started.run_id)

    assert events[0].type == "run.started"
    role_events = events[1:14]
    assert len(role_events) == 13
    assert [event.type for event in role_events] == ["role.status_changed"] * 13
    assert [event.actor_id for event in role_events] == [
        role.actor_id for role in ROLE_REGISTRY
    ]
    assert {event.payload["previous_status"] for event in role_events} == {
        "uninitialized"
    }
    assert [event.payload["new_status"] for event in role_events] == [
        "pending",
        "skipped",
        "skipped",
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
    ]
    assert role_events[1].payload["reason"] == "not_selected"
    assert role_events[2].payload["reason"] == "not_selected"

    runner.release.set()
    assert manager.wait(started.run_id, timeout=3).status == "completed"


def test_two_concurrent_submissions_have_exactly_one_atomic_winner(tmp_path):
    runner = _ScriptedRunner()
    manager, store, _broker, factory = _manager(tmp_path, runner)
    barrier = threading.Barrier(3)
    results: list[RunSnapshot] = []
    conflicts: list[ActiveRunConflict] = []

    def submit(ticker: str) -> None:
        barrier.wait()
        try:
            results.append(manager.start(_request(ticker)))
        except ActiveRunConflict as exc:
            conflicts.append(exc)

    first = threading.Thread(target=submit, args=("AAPL",))
    second = threading.Thread(target=submit, args=("MSFT",))
    first.start()
    second.start()
    barrier.wait()
    first.join(timeout=3)
    second.join(timeout=3)

    assert not first.is_alive() and not second.is_alive()
    assert len(results) == 1
    assert len(conflicts) == 1
    _wait_for_entry(runner)
    assert conflicts[0].active_run_id == results[0].run_id
    assert manager.active_run_id == results[0].run_id
    assert len(factory.calls) == 1
    assert len(store.list_runs()) == 1

    runner.release.set()
    terminal = manager.wait(results[0].run_id, timeout=3)
    assert terminal.status == "completed"


def test_success_publishes_report_then_terminalizes_and_cleans_worker(tmp_path):
    first = _ScriptedRunner()
    second = _ScriptedRunner(release_immediately=True)
    manager, store, broker, _factory = _manager(tmp_path, first, second)
    terminal_snapshots: list[RunSnapshot] = []
    real_publish = broker.publish

    def capture_terminal_snapshot(draft: RunEventDraft):
        if draft.type == "run.completed":
            terminal_snapshots.append(store.read_snapshot(draft.run_id))
        return real_publish(draft)

    broker.publish = capture_terminal_snapshot  # type: ignore[method-assign]

    started = manager.start(_request())
    _wait_for_entry(first)
    assert manager.active_run_id == started.run_id
    first.release.set()

    completed = manager.wait(started.run_id, timeout=3)

    assert completed.status == "completed"
    assert completed.final_signal == "BUY"
    assert manager.active_run_id is None
    assert _event_types(store, started.run_id)[-1] == "run.completed"
    assert (tmp_path / started.run_id / "reports" / "complete_report.md").is_file()
    assert terminal_snapshots[0].status == "running"
    assert terminal_snapshots[0].final_signal == "BUY"
    assert terminal_snapshots[0].artifacts

    follow_up = manager.start(_request("MSFT"))
    assert manager.wait(follow_up.run_id, timeout=3).status == "completed"


def test_failure_terminalizes_run_and_cleans_worker_without_false_report(tmp_path):
    original = RuntimeError("provider exploded with OPENAI_API_KEY=secret")
    runner = _ScriptedRunner(outcome="failure", error=original)
    manager, store, broker, _factory = _manager(tmp_path, runner)
    terminal_snapshots: list[RunSnapshot] = []
    real_publish = broker.publish

    def capture_terminal_snapshot(draft: RunEventDraft):
        if draft.type == "run.failed":
            terminal_snapshots.append(store.read_snapshot(draft.run_id))
        return real_publish(draft)

    broker.publish = capture_terminal_snapshot  # type: ignore[method-assign]

    started = manager.start(_request())
    _wait_for_entry(runner)
    runner.release.set()
    failed = manager.wait(started.run_id, timeout=3)

    assert failed.status == "failed"
    assert failed.error_category == "unexpected_internal_failure"
    assert failed.summary
    assert "secret" not in failed.summary
    assert _event_types(store, started.run_id)[-1] == "run.failed"
    assert not (tmp_path / started.run_id / "reports").exists()
    assert manager.active_run_id is None
    assert terminal_snapshots[0].status == "running"
    assert terminal_snapshots[0].error_category == "unexpected_internal_failure"
    assert terminal_snapshots[0].summary == failed.summary


def test_failure_compensates_open_vendor_tool_turn_role_then_pending_roles(tmp_path):
    runner = _ScriptedRunner(
        outcome="failure",
        on_enter=lambda observer: _emit_open_lifecycles(
            observer.emit,
            observer.run_id,
        ),
    )
    manager, store, _broker, _factory = _manager(tmp_path, runner)

    started = manager.start(_request())
    _wait_for_entry(runner)
    runner.release.set()
    assert manager.wait(started.run_id, timeout=3).status == "failed"

    events = store.read_events(started.run_id)
    open_sequence = next(
        event.sequence for event in events if event.type == "data.progress"
    )
    tail = [event for event in events if event.sequence > open_sequence]
    lifecycle_tail = [
        event
        for event in tail
        if event.type
        in {
            "data.failed",
            "tool.execution_failed",
            "tool.cancelled",
            "turn.failed",
            "role.status_changed",
            "run.failed",
        }
    ]

    assert [event.type for event in lifecycle_tail[:4]] == [
        "data.failed",
        "tool.execution_failed",
        "tool.cancelled",
        "turn.failed",
    ]
    role_terminal_events = [
        event for event in lifecycle_tail if event.type == "role.status_changed"
    ]
    assert role_terminal_events[0].actor_id == "analyst.market"
    assert role_terminal_events[0].payload["new_status"] == "failed"
    assert [event.actor_id for event in role_terminal_events[1:]] == [
        role.actor_id
        for role in ROLE_REGISTRY
        if role.actor_id not in {"analyst.market", "analyst.sentiment", "analyst.news"}
    ]
    assert {
        event.payload["new_status"] for event in role_terminal_events[1:]
    } == {"not_reached"}
    assert lifecycle_tail[-1].type == "run.failed"


def test_cancel_is_cooperative_terminal_and_worker_is_cleaned(tmp_path):
    runner = _ScriptedRunner(outcome="cancel")
    manager, store, _broker, _factory = _manager(tmp_path, runner)

    started = manager.start(_request())
    _wait_for_entry(runner)
    requested = manager.cancel(started.run_id)

    assert requested.status == "cancel_requested"
    assert manager.active_run_id == started.run_id
    assert runner.calls[0]["cancellation_token"].is_cancelled

    runner.release.set()
    cancelled = manager.wait(started.run_id, timeout=3)

    assert cancelled.status == "cancelled"
    events = store.read_events(started.run_id)
    cancel_requested_index = next(
        index for index, event in enumerate(events) if event.type == "run.cancel_requested"
    )
    assert events[-1].type == "run.cancelled"
    pending_compensation = [
        event
        for event in events[cancel_requested_index + 1 : -1]
        if event.type == "role.status_changed"
    ]
    assert [event.actor_id for event in pending_compensation] == [
        role.actor_id
        for role in ROLE_REGISTRY
        if role.actor_id not in {"analyst.sentiment", "analyst.news"}
    ]
    assert {
        event.payload["new_status"] for event in pending_compensation
    } == {"not_reached"}
    assert manager.active_run_id is None
    assert not (tmp_path / started.run_id / "reports").exists()


def test_cancel_wins_if_persisted_before_success_terminalization_begins(tmp_path):
    runner = _ScriptedRunner()
    manager, store, _broker, _factory = _manager(tmp_path, runner)
    terminalization_entered = threading.Event()
    release_terminalization = threading.Event()
    real_begin = manager._begin_terminalization

    def gated_begin(run_id: str) -> str:
        terminalization_entered.set()
        assert release_terminalization.wait(3), "test did not release terminalization"
        return real_begin(run_id)

    manager._begin_terminalization = gated_begin  # type: ignore[method-assign]
    started = manager.start(_request())
    _wait_for_entry(runner)
    runner.release.set()
    assert terminalization_entered.wait(3)

    assert manager.cancel(started.run_id).status == "cancel_requested"
    release_terminalization.set()

    terminal = manager.wait(started.run_id, timeout=3)
    assert terminal.status == "cancelled"
    assert _event_types(store, started.run_id)[-1] == "run.cancelled"
    assert not (tmp_path / started.run_id / "reports").exists()


def test_success_is_rejected_if_a_role_lifecycle_is_still_open(tmp_path):
    runner = _ScriptedRunner(
        release_immediately=True,
        complete_roles=False,
        on_enter=lambda observer: _emit_open_lifecycles(
            observer.emit,
            observer.run_id,
        ),
    )
    manager, store, _broker, _factory = _manager(tmp_path, runner)

    started = manager.start(_request())
    terminal = manager.wait(started.run_id, timeout=3)

    assert terminal.status == "failed"
    assert terminal.error_category == "unexpected_internal_failure"
    assert _event_types(store, started.run_id)[-1] == "run.failed"
    assert not (tmp_path / started.run_id / "reports").exists()


def test_worker_installs_and_restores_all_process_run_scopes_on_failure(tmp_path):
    import tradingagents.dataflows.config as config_module

    original_config = get_config()
    set_config({"manager_outer_marker": "preserve-me"})
    expected_restored_config = get_config()

    def outer_sink(_event):
        return None

    progress_module.set_progress_sink(outer_sink)
    runner = _ScriptedRunner(outcome="failure")
    manager, _store, _broker, _factory = _manager(tmp_path, runner)

    started = manager.start(_request())
    _wait_for_entry(runner)
    observed = runner.scope_observations[0]

    assert observed["config"]["manager_scope_marker"] == "AAPL"
    assert observed["progress_sink"] is not None
    assert observed["progress_sink"] is not outer_sink
    assert observed["provenance_observer"] is observed["context_observer"]
    assert observed["callback_observer"] is observed["context_observer"]
    assert observed["cache_namespace"] == started.run_id

    runner.release.set()
    assert manager.wait(started.run_id, timeout=3).status == "failed"
    assert get_config() == expected_restored_config
    assert progress_module._progress_sink is outer_sink

    progress_module.set_progress_sink(None)
    config_module._config = original_config


def test_scope_context_managers_exit_in_reverse_order_even_when_runner_raises(
    tmp_path,
    monkeypatch,
):
    """The ContextVar scopes must be exited, not merely installed in a fresh thread."""
    import tradingagents.web.manager as manager_module

    transitions: list[str] = []
    real_provenance_scope = manager_module.provenance_scope
    real_news_cache_scope = manager_module.news_cache_scope

    @contextmanager
    def tracked_provenance_scope(observer):
        transitions.append("observer.enter")
        try:
            with real_provenance_scope(observer):
                yield
        finally:
            transitions.append("observer.exit")

    @contextmanager
    def tracked_news_cache_scope(run_id):
        transitions.append(f"cache.enter:{run_id}")
        try:
            with real_news_cache_scope(run_id):
                yield
        finally:
            transitions.append(f"cache.exit:{run_id}")

    monkeypatch.setattr(manager_module, "provenance_scope", tracked_provenance_scope)
    monkeypatch.setattr(manager_module, "news_cache_scope", tracked_news_cache_scope)
    runner = _ScriptedRunner(outcome="failure", release_immediately=True)
    manager, _store, _broker, _factory = _manager(tmp_path, runner)

    started = manager.start(_request())
    assert manager.wait(started.run_id, timeout=3).status == "failed"

    assert transitions == [
        "cache.enter:" + started.run_id,
        "observer.enter",
        "observer.exit",
        "cache.exit:" + started.run_id,
    ]


def test_startup_reconciles_frontier_before_interrupted_lifecycle(tmp_path):
    store = RunStore(tmp_path)
    abandoned = _persisted_run(store, status="running", checkpoint_available=True)
    broker = EventBroker(store)
    _emit_open_lifecycles(broker.publish, abandoned.run_id)
    order: list[str] = []

    def reconcile(snapshot: RunSnapshot, observer: Any) -> None:
        order.append(f"reconcile:{snapshot.run_id}")
        observer.emit(
            RunEventDraft(
                snapshot.run_id,
                "graph.checkpoint_committed",
                {
                    "graph_step": 7,
                    "applied_task_ids": [],
                    "state_sha256": "0" * 64,
                    "next_nodes": ["Market Analyst"],
                    "checkpoint_id": "checkpoint-7",
                    "reconciled": True,
                },
            )
        )

    manager = SingleRunManager(
        store,
        broker,
        _RunnerFactory(),
        startup_reconciler=reconcile,
    )

    recovered = manager.recover_startup()

    assert [item.run_id for item in recovered] == [abandoned.run_id]
    assert recovered[0].status == "interrupted"
    assert order == [f"reconcile:{abandoned.run_id}"]
    events = store.read_events(abandoned.run_id)
    types = [event.type for event in events]
    marker = next(
        event for event in events if event.type == "graph.checkpoint_committed"
    )
    assert types.index("graph.checkpoint_committed") < types.index("run.interrupted")
    first_interrupted = next(
        index
        for index, event_type in enumerate(types)
        if event_type.endswith(".interrupted")
    )
    assert types.index("graph.checkpoint_committed") < first_interrupted
    assert [
        event_type
        for event_type in types[first_interrupted:]
        if event_type
        in {
            "data.interrupted",
            "tool.execution_interrupted",
            "tool.cancelled",
            "turn.interrupted",
            "run.interrupted",
        }
    ] == [
        "data.interrupted",
        "tool.execution_interrupted",
        "turn.interrupted",
        "run.interrupted",
    ]
    interrupted = store.read_events(abandoned.run_id)[-1]
    assert interrupted.payload["checkpoint_sequence"] == marker.sequence
    assert manager.active_run_id is None


def test_startup_without_checkpoint_abandons_tail_and_closes_logical_tool(tmp_path):
    store = RunStore(tmp_path)
    orphan = _persisted_run(store, status="running", checkpoint_available=False)
    broker = EventBroker(store)
    broker.publish(
        RunEventDraft(
            orphan.run_id,
            "graph.task_started",
            {
                "graph_task_id": "task_open",
                "graph_step": 1,
                "node_id": "Market Analyst",
            },
            actor_id="analyst.market",
            node_id="Market Analyst",
            status="started",
        )
    )
    _emit_open_lifecycles(broker.publish, orphan.run_id)
    manager = SingleRunManager(store, broker, _RunnerFactory())

    recovered = manager.recover_startup()

    assert recovered[0].status == "interrupted"
    events = store.read_events(orphan.run_id)
    abandoned = next(event for event in events if event.type == "graph.task_abandoned")
    cancelled = next(event for event in events if event.type == "tool.cancelled")
    interrupted = next(event for event in events if event.type == "turn.interrupted")
    assert abandoned.payload["reason"] == "process_interrupted_without_checkpoint"
    assert abandoned.sequence < cancelled.sequence < interrupted.sequence
    assert events[-1].type == "run.interrupted"


def test_retry_copies_safe_request_but_creates_new_run_and_namespace(tmp_path):
    runner = _ScriptedRunner(release_immediately=True)
    manager, store, _broker, factory = _manager(tmp_path, runner)
    original = _persisted_run(store, status="failed")

    retried = manager.retry(original.run_id)
    terminal = manager.wait(retried.run_id, timeout=3)

    assert retried.run_id != original.run_id
    assert retried.retry_of == original.run_id
    assert terminal.status == "completed"
    request, _observer = factory.calls[0]
    assert request.ticker == original.ticker
    assert request.analysis_date == original.analysis_date
    assert request.selected_analysts == original.selected_analysts
    assert request.effective_config["manager_scope_marker"] == "MSFT"
    assert request.effective_config["llm_provider"] == original.llm_provider
    assert runner.calls[0]["checkpoint_run_id"] == retried.run_id
    assert runner.scope_observations[0]["cache_namespace"] == retried.run_id


def test_resume_reuses_only_same_compatible_interrupted_run(tmp_path):
    guard = object()
    runner = _ScriptedRunner(release_immediately=True)
    compatible_calls: list[tuple[str, AnalysisRequest]] = []

    def resume_preflight(snapshot: RunSnapshot, request: AnalysisRequest):
        compatible_calls.append((snapshot.run_id, request))
        return guard

    manager, store, _broker, _factory = _manager(
        tmp_path,
        runner,
        resume_preflight=resume_preflight,
    )
    interrupted = _persisted_run(
        store,
        status="running",
        checkpoint_available=True,
    )
    checkpoint_marker = store.append_event(
        RunEventDraft(
            interrupted.run_id,
            "graph.checkpoint_committed",
            {
                "graph_step": 3,
                "applied_task_ids": [],
                "state_sha256": "0" * 64,
                "next_nodes": ["Market Analyst"],
                "checkpoint_id": "checkpoint-resume",
            },
        )
    )
    _emit_open_lifecycles(manager.broker.publish, interrupted.run_id)
    manager.recover_startup()
    before_resume = store.read_snapshot(interrupted.run_id)

    resumed = manager.resume(interrupted.run_id)
    terminal = manager.wait(interrupted.run_id, timeout=3)

    assert resumed.run_id == interrupted.run_id
    assert resumed.resumed_from_sequence == before_resume.latest_sequence
    assert terminal.status == "completed"
    assert compatible_calls[0][0] == interrupted.run_id
    assert runner.calls[0]["checkpoint_run_id"] == interrupted.run_id
    assert runner.calls[0]["checkpoint_guard"] is guard
    resumed_event = next(
        event
        for event in store.read_events(interrupted.run_id)
        if event.type == "run.resumed"
    )
    assert resumed_event.payload["checkpoint_sequence"] == checkpoint_marker.sequence
    resumed_turn = next(
        event
        for event in store.read_events(interrupted.run_id)
        if event.type == "turn.resumed"
    )
    assert resumed_turn.payload["resumed_from_sequence"] == before_resume.latest_sequence

    failed = _persisted_run(store, status="failed", checkpoint_available=True)
    with pytest.raises(RunNotResumable, match="status failed"):
        manager.resume(failed.run_id)


def test_resume_rejects_incompatible_checkpoint_without_mutating_run(tmp_path):
    runner = _ScriptedRunner(release_immediately=True)

    class IncompatibleCheckpoint(RuntimeError):
        def __init__(self):
            self.fields = ("runtime_semantics_hash",)
            super().__init__("checkpoint_incompatible")

    def incompatible(_snapshot: RunSnapshot, _request: AnalysisRequest):
        raise IncompatibleCheckpoint

    manager, store, _broker, factory = _manager(
        tmp_path,
        runner,
        resume_preflight=incompatible,
    )
    interrupted = _persisted_run(
        store,
        status="running",
        checkpoint_available=True,
    )
    manager.recover_startup()
    before = store.read_snapshot(interrupted.run_id)

    with pytest.raises(IncompatibleCheckpoint) as exc_info:
        manager.resume(interrupted.run_id)

    assert exc_info.value.fields == ("runtime_semantics_hash",)
    assert store.read_snapshot(interrupted.run_id) == before
    assert factory.calls == []
    assert manager.active_run_id is None


def test_browser_subscription_disconnect_never_cancels_active_run(tmp_path):
    async def scenario() -> None:
        runner = _ScriptedRunner()
        manager, _store, broker, _factory = _manager(tmp_path, runner)
        started = manager.start(_request())
        _wait_for_entry(runner)
        token = runner.calls[0]["cancellation_token"]

        subscription = await broker.subscribe(started.run_id)
        await subscription.close()

        assert broker.subscriber_count(started.run_id) == 0
        assert manager.active_run_id == started.run_id
        assert not token.is_cancelled

        runner.release.set()
        assert manager.wait(started.run_id, timeout=3).status == "completed"

    asyncio.run(scenario())
