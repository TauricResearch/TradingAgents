"""Observed AnalysisRunner contracts against a real LangGraph checkpoint saver.

These tests deliberately keep the graph tiny while retaining the two durable
surfaces a web run must join: LangGraph SQLite checkpoints and append-only
observation candidates.  Stream argument assertions are made at the compiled
graph boundary, rather than by mocking ``StateGraph.stream``.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.execution.models import (
    AnalysisCancelled,
    AnalysisRequest,
    CancellationToken,
)
from tradingagents.execution.runner import AnalysisRunner
from tradingagents.graph.propagation import Propagator
from tradingagents.observability.canonical import (
    AGENT_STATE_SCHEMA_SHA256,
    BUSINESS_PROJECTION_VERSION,
    RESERVED_OBSERVATION_FIELD,
    SERIALIZER_VERSION,
    canonical_sha256,
)
from tradingagents.observability.events import ObservationCommitV1, RunEventDraft
from tradingagents.observability.graph_tasks import (
    GraphObservationRunContext,
    ObservedGraphTask,
    ObservedNode,
    ObservedToolNode,
)
from tradingagents.observability.observer import DurableRunObserver
from tradingagents.observability.projections import RoleProjectionRunContext
from tradingagents.web.fingerprint import (
    FingerprintCheckpointGuard,
    ResumeFingerprintV1,
)
from tradingagents.web.reconciliation import (
    apply_reconciliation_plan,
    reconcile_checkpoint_frontier,
)
from tradingagents.web.run_models import RunSnapshot
from tradingagents.web.store import RunStore


@dataclass
class _GraphControl:
    fail_second: bool = False
    first_calls: int = 0
    second_calls: int = 0


@tool
def lookup_price(symbol: str) -> str:
    """Return a stable test price."""
    return f"{symbol}=210"


@tool
def lookup_volume(symbol: str) -> str:
    """Return a stable test volume."""
    return f"{symbol}=1000000"


class _ObservedPropagator:
    """Use the production initial-state observer while recording its calls."""

    def __init__(
        self,
        cancellation_token: CancellationToken | None = None,
        *,
        cancel_after_create: bool = False,
    ) -> None:
        self.delegate = Propagator(max_recur_limit=20)
        self.created_states: list[dict[str, Any]] = []
        self.cancellation_token = cancellation_token
        self.cancel_after_create = cancel_after_create

    def create_initial_state(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        state = self.delegate.create_initial_state(*args, **kwargs)
        self.created_states.append(state)
        if self.cancel_after_create:
            assert self.cancellation_token is not None
            self.cancellation_token.cancel()
            self.cancel_after_create = False
        return state

    def get_graph_args(self, callbacks=None) -> dict[str, Any]:
        # This legacy scalar value is intentionally overridden by the observed
        # runner contract at the compiled graph boundary.
        return self.delegate.get_graph_args(callbacks=callbacks)


class _RecordingGraph:
    def __init__(
        self,
        delegate: Any,
        records: list[dict[str, Any]],
        *,
        cancellation_token: CancellationToken | None,
        cancel_after_update: bool,
        cancel_after_bootstrap: bool,
    ) -> None:
        self._delegate = delegate
        self._records = records
        self._cancellation_token = cancellation_token
        self._cancel_after_update = cancel_after_update
        self._cancel_after_bootstrap = cancel_after_bootstrap
        self._cancelled = False

    def stream(self, input_value: Any, *args: Any, **kwargs: Any):
        recorded_kwargs = dict(kwargs)
        if isinstance(recorded_kwargs.get("stream_mode"), list):
            recorded_kwargs["stream_mode"] = list(recorded_kwargs["stream_mode"])
        if isinstance(recorded_kwargs.get("config"), dict):
            recorded_kwargs["config"] = deepcopy(recorded_kwargs["config"])
        record = {
            "input": input_value,
            "args": args,
            # GraphObservationRunContext owns an observer with an RLock and is
            # intentionally not deepcopy-able.  A shallow boundary snapshot is
            # sufficient: LangGraph may enrich nested config during execution,
            # while the stream contract fields themselves are immutable here.
            "kwargs": recorded_kwargs,
            "events": [],
        }
        self._records.append(record)
        for event in self._delegate.stream(input_value, *args, **kwargs):
            record["events"].append(event)
            mode = event[0] if isinstance(event, tuple) and len(event) == 2 else None
            if (
                self._cancel_after_update
                and not self._cancelled
                and mode == "updates"
            ):
                assert self._cancellation_token is not None
                self._cancellation_token.cancel()
                self._cancelled = True
            if (
                self._cancel_after_bootstrap
                and not self._cancelled
                and mode == "checkpoints"
                and event[1].get("metadata", {}).get("step") == -1
            ):
                assert self._cancellation_token is not None
                self._cancellation_token.cancel()
                self._cancelled = True
            yield event

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class _ObservedWorkflow:
    def __init__(
        self,
        control: _GraphControl,
        *,
        cancellation_token: CancellationToken | None = None,
        cancel_after_update: bool = False,
        role_first: bool = False,
        tool_cycle: bool = False,
        observer: DurableRunObserver | None = None,
        cancel_after_bootstrap: bool = False,
    ) -> None:
        self.control = control
        self.cancellation_token = cancellation_token
        self.cancel_after_update = cancel_after_update
        self.role_first = role_first
        self.tool_cycle = tool_cycle
        self.observer = observer
        self.cancel_after_bootstrap = cancel_after_bootstrap
        self.stream_records: list[dict[str, Any]] = []

    def compile(self, checkpointer=None) -> _RecordingGraph:
        control = self.control

        def first_node(state):
            control.first_calls += 1
            if self.tool_cycle and isinstance(state["messages"][-1], ToolMessage):
                return {
                    "messages": [AIMessage(content="tool-backed conclusion")],
                    "market_report": "tool-backed report",
                }
            if self.tool_cycle:
                assert self.observer is not None
                self.observer.on_llm_start(
                    {},
                    ["tool request prompt"],
                    run_id="model-tool-request",
                )
                self.observer.on_llm_end(
                    SimpleNamespace(llm_output={}),
                    run_id="model-tool-request",
                )
                return {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "lookup_price",
                                    "args": {"symbol": "AAPL"},
                                    "id": "call-price",
                                    "type": "tool_call",
                                },
                                {
                                    "name": "lookup_volume",
                                    "args": {"symbol": "AAPL"},
                                    "id": "call-volume",
                                    "type": "tool_call",
                                },
                            ],
                        )
                    ],
                    "market_report": "",
                }
            return {
                "messages": [AIMessage(content="first applied message")],
                "market_report": "first applied report",
            }

        def second_node(_state):
            control.second_calls += 1
            if control.fail_second:
                raise RuntimeError("simulated second-node crash")
            return {
                "messages": [AIMessage(content="second applied message")],
                "final_trade_decision": "Rating: Buy",
            }

        builder = StateGraph(
            AgentState,
            context_schema=GraphObservationRunContext,
        )
        first_name = "Market Analyst" if self.role_first or self.tool_cycle else "First"
        first_task = (
            ObservedNode("analyst.market", first_name, first_node)
            if self.role_first or self.tool_cycle
            else ObservedGraphTask(first_name, "maintenance", first_node)
        )
        builder.add_node(first_name, first_task)
        builder.add_node(
            "Second",
            ObservedGraphTask("Second", "maintenance", second_node),
        )
        builder.add_edge(START, first_name)
        if self.tool_cycle:
            builder.add_node(
                "tools_market",
                ObservedToolNode(
                    "tools_market",
                    ToolNode([lookup_price, lookup_volume]),
                ),
            )

            def route(state):
                last = state["messages"][-1]
                return (
                    "tools"
                    if isinstance(last, AIMessage) and last.tool_calls
                    else "done"
                )

            builder.add_conditional_edges(
                first_name,
                route,
                {"tools": "tools_market", "done": "Second"},
            )
            builder.add_edge("tools_market", first_name)
        else:
            builder.add_edge(first_name, "Second")
        builder.add_edge("Second", END)
        compiled = builder.compile(checkpointer=checkpointer)
        return _RecordingGraph(
            compiled,
            self.stream_records,
            cancellation_token=self.cancellation_token,
            cancel_after_update=self.cancel_after_update,
            cancel_after_bootstrap=self.cancel_after_bootstrap,
        )


def _fixed_fingerprint() -> ResumeFingerprintV1:
    document = {
        "fingerprint_version": 1,
        "request": {"ticker": "AAPL"},
        "effective_config": {"test": "runner-contract"},
        "runtime_semantics_hash": "a" * 64,
        "runtime_environment": {"python": "test"},
        "observation_schema": {
            "agent_state_schema_sha256": "b" * 64,
        },
        "event_schema_version": 1,
        "initial_context_hash": "c" * 64,
    }
    return ResumeFingerprintV1(
        document=document,
        sha256=canonical_sha256(document),
        resumable=True,
    )


def _case(
    tmp_path,
    monkeypatch,
    *,
    checkpoint_enabled: bool,
    control: _GraphControl | None = None,
    cancellation_token: CancellationToken | None = None,
    cancel_after_update: bool = False,
    role_first: bool = False,
    tool_cycle: bool = False,
    cancel_after_bootstrap: bool = False,
    cancel_after_create: bool = False,
):
    control = control or _GraphControl()
    data_cache_dir = tmp_path / "cache"
    config = {
        "checkpoint_enabled": checkpoint_enabled,
        "data_cache_dir": str(data_cache_dir),
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "llm_provider": "openai",
        "quick_think_llm": "quick",
        "deep_think_llm": "deep",
    }
    request = AnalysisRequest(
        ticker="AAPL",
        analysis_date="2026-07-18",
        selected_analysts=("market",),
        effective_config=deepcopy(config),
    )
    store = RunStore(tmp_path / "runs")
    snapshot = RunSnapshot.create(
        ticker=request.ticker,
        analysis_date=request.analysis_date,
        selected_analysts=request.selected_analysts,
        llm_provider="openai",
        quick_think_llm="quick",
        deep_think_llm="deep",
    )
    store.create_run(snapshot)
    observer = DurableRunObserver(store, snapshot.run_id)
    observation_context = GraphObservationRunContext(
        observer=observer,
        role_projection=RoleProjectionRunContext(
            effective_config=config,
            effective_config_artifact_id="config:frozen",
        ),
    )
    workflow = _ObservedWorkflow(
        control,
        cancellation_token=cancellation_token,
        cancel_after_update=cancel_after_update,
        role_first=role_first,
        tool_cycle=tool_cycle,
        observer=observer,
        cancel_after_bootstrap=cancel_after_bootstrap,
    )
    propagator = _ObservedPropagator(
        cancellation_token,
        cancel_after_create=cancel_after_create,
    )
    owner = SimpleNamespace(
        config=config,
        selected_analysts=("market",),
        callbacks=[],
        debug=False,
        curr_state=None,
        ticker=None,
        _checkpointer_ctx=None,
        workflow=workflow,
        graph=workflow.compile(),
        propagator=propagator,
        memory_log=MagicMock(),
        signal_processor=MagicMock(),
        _resolve_pending_entries=MagicMock(),
        resolve_instrument_context=MagicMock(
            return_value="Ticker: AAPL; Apple Inc."
        ),
        _run_signature=MagicMock(return_value="observed-two-node-v1"),
        _log_state=MagicMock(),
        process_signal=MagicMock(return_value="BUY"),
    )
    owner.memory_log.get_past_context.return_value = "prior lesson"
    monkeypatch.setattr(
        "tradingagents.web.fingerprint.build_resume_fingerprint",
        lambda *args, **kwargs: _fixed_fingerprint(),
    )
    guard = FingerprintCheckpointGuard(
        store,
        snapshot.run_id,
        request,
        config,
    )
    return SimpleNamespace(
        owner=owner,
        request=request,
        store=store,
        snapshot=snapshot,
        context=observation_context,
        guard=guard,
        workflow=workflow,
        propagator=propagator,
        control=control,
    )


def _stream_kwargs(case) -> dict[str, Any]:
    assert len(case.workflow.stream_records) == 1
    return case.workflow.stream_records[0]["kwargs"]


def _message_texts(state: Any) -> list[str]:
    return [getattr(message, "content", str(message)) for message in state["messages"]]


def _modes(case) -> list[str]:
    return [event[0] for event in case.workflow.stream_records[0]["events"]]


def test_checkpointed_fresh_observed_run_uses_sync_v1_and_checkpoint_values(
    tmp_path,
    monkeypatch,
):
    case = _case(tmp_path, monkeypatch, checkpoint_enabled=True)

    result = AnalysisRunner(case.owner).run(
        case.request,
        observation_context=case.context,
        checkpoint_guard=case.guard,
    )

    record = case.workflow.stream_records[0]
    kwargs = _stream_kwargs(case)
    assert record["input"] is case.propagator.created_states[0]
    assert kwargs["stream_mode"] == ["tasks", "updates", "checkpoints"]
    assert kwargs["durability"] == "sync"
    assert kwargs["version"] == "v1"
    assert "checkpoints" in _modes(case)

    updates = [payload for mode, payload in record["events"] if mode == "updates"]
    assert _message_texts(next(iter(updates[-1].values()))) == [
        "second applied message"
    ]
    assert _message_texts(result.final_state) == [
        "AAPL",
        "first applied message",
        "second applied message",
    ]
    assert result.final_state["market_report"] == "first applied report"


def test_checkpointed_resume_passes_none_and_does_not_recreate_initial_state(
    tmp_path,
    monkeypatch,
):
    control = _GraphControl(fail_second=True)
    case = _case(
        tmp_path,
        monkeypatch,
        checkpoint_enabled=True,
        control=control,
    )

    with pytest.raises(RuntimeError, match="simulated second-node crash"):
        AnalysisRunner(case.owner).run(
            case.request,
            observation_context=case.context,
            checkpoint_guard=case.guard,
        )

    assert control.first_calls == 1
    assert len(case.propagator.created_states) == 1
    control.fail_second = False

    result = AnalysisRunner(case.owner).run(
        case.request,
        observation_context=case.context,
        checkpoint_guard=case.guard,
    )

    assert len(case.workflow.stream_records) == 2
    assert case.workflow.stream_records[1]["input"] is None
    assert len(case.propagator.created_states) == 1
    assert control.first_calls == 1
    assert control.second_calls == 2
    assert _message_texts(result.final_state) == [
        "AAPL",
        "first applied message",
        "second applied message",
    ]


def test_resume_from_bootstrap_checkpoint_does_not_abandon_synthetic_input(
    tmp_path,
    monkeypatch,
):
    token = CancellationToken()
    case = _case(
        tmp_path,
        monkeypatch,
        checkpoint_enabled=True,
        cancellation_token=token,
        cancel_after_bootstrap=True,
    )

    with pytest.raises(AnalysisCancelled):
        AnalysisRunner(case.owner).run(
            case.request,
            observation_context=case.context,
            checkpoint_guard=case.guard,
            cancellation_token=token,
        )

    assert case.control.first_calls == 0
    result = AnalysisRunner(case.owner).run(
        case.request,
        observation_context=case.context,
        checkpoint_guard=case.guard,
    )

    input_task_id = f"{case.snapshot.run_id}:input"
    assert result.final_state["_observation_commits"][input_task_id]["task_kind"] == "input"
    assert not any(
        event.type == "graph.task_abandoned"
        and event.payload["graph_task_id"] == input_task_id
        for event in case.store.read_events(case.snapshot.run_id)
    )


def test_fresh_retry_reuses_exact_input_candidate_before_any_checkpoint(
    tmp_path,
    monkeypatch,
):
    token = CancellationToken()
    case = _case(
        tmp_path,
        monkeypatch,
        checkpoint_enabled=True,
        cancellation_token=token,
        cancel_after_create=True,
    )

    with pytest.raises(AnalysisCancelled):
        AnalysisRunner(case.owner).run(
            case.request,
            observation_context=case.context,
            checkpoint_guard=case.guard,
            cancellation_token=token,
        )

    assert case.workflow.stream_records == []
    result = AnalysisRunner(case.owner).run(
        case.request,
        observation_context=case.context,
        checkpoint_guard=case.guard,
    )

    input_task_id = f"{case.snapshot.run_id}:input"
    candidates = [
        event
        for event in case.store.read_events(case.snapshot.run_id)
        if event.type == "graph.task_output_ready"
        and event.payload["observation_commit"]["graph_task_id"] == input_task_id
    ]
    assert len(candidates) == 1
    assert result.final_state["_observation_commits"][input_task_id]["task_kind"] == "input"


def test_role_state_report_and_completion_are_promoted_after_checkpoint(
    tmp_path,
    monkeypatch,
):
    case = _case(
        tmp_path,
        monkeypatch,
        checkpoint_enabled=True,
        role_first=True,
    )

    AnalysisRunner(case.owner).run(
        case.request,
        observation_context=case.context,
        checkpoint_guard=case.guard,
    )

    events = case.store.read_events(case.snapshot.run_id)
    candidate = next(
        event
        for event in events
        if event.type == "graph.task_output_ready"
        and event.payload["observation_commit"]["task_kind"] == "role"
    )
    task_id = candidate.payload["observation_commit"]["graph_task_id"]
    marker = next(
        event
        for event in events
        if event.type == "graph.checkpoint_committed"
        and task_id in event.payload["applied_task_ids"]
    )
    promoted = [
        event
        for event in events
        if event.type
        in {"state.updated", "report.updated", "turn.completed"}
        and event.payload.get("graph_task_id") == task_id
    ]

    assert {event.type for event in promoted} == {
        "state.updated",
        "report.updated",
        "turn.completed",
    }
    assert all(event.sequence > marker.sequence for event in promoted)
    report = next(event for event in promoted if event.type == "report.updated")
    assert case.store.read_artifact(
        case.snapshot.run_id,
        report.payload["artifact_id"],
    ) == b"first applied report"


def test_checkpoint_disabled_role_promotes_only_after_values_barrier(
    tmp_path,
    monkeypatch,
):
    case = _case(
        tmp_path,
        monkeypatch,
        checkpoint_enabled=False,
        role_first=True,
    )

    AnalysisRunner(case.owner).run(
        case.request,
        observation_context=case.context,
    )

    events = case.store.read_events(case.snapshot.run_id)
    candidate = next(
        event
        for event in events
        if event.type == "graph.task_output_ready"
        and event.payload["observation_commit"]["task_kind"] == "role"
    )
    task_id = candidate.payload["observation_commit"]["graph_task_id"]
    marker = next(
        event
        for event in events
        if event.type == "graph.step_applied"
        and task_id in event.payload["applied_task_ids"]
    )
    promoted = [
        event
        for event in events
        if event.type in {"state.updated", "report.updated", "turn.completed"}
        and event.payload.get("graph_task_id") == task_id
    ]

    assert {event.type for event in promoted} == {
        "state.updated",
        "report.updated",
        "turn.completed",
    }
    assert all(event.sequence > marker.sequence for event in promoted)


def test_multi_tool_callbacks_are_committed_in_token_order_after_tool_checkpoint(
    tmp_path,
    monkeypatch,
):
    case = _case(
        tmp_path,
        monkeypatch,
        checkpoint_enabled=True,
        tool_cycle=True,
    )

    AnalysisRunner(case.owner).run(
        case.request,
        observation_context=case.context,
        checkpoint_guard=case.guard,
    )

    events = case.store.read_events(case.snapshot.run_id)
    tool_candidate = next(
        event
        for event in events
        if event.type == "graph.task_output_ready"
        and event.payload["observation_commit"]["task_kind"] == "tool"
    )
    commit = tool_candidate.payload["observation_commit"]
    assert commit["tool_call_ids"] == ["call-price", "call-volume"]
    marker = next(
        event
        for event in events
        if event.type == "graph.checkpoint_committed"
        and commit["graph_task_id"] in event.payload["applied_task_ids"]
    )
    committed = [event for event in events if event.type == "tool.committed"]

    assert [event.payload["tool_call_id"] for event in committed] == [
        "call-price",
        "call-volume",
    ]
    assert all(event.sequence > marker.sequence for event in committed)
    assert all(event.payload["checkpoint_event_id"] == marker.event_id for event in committed)


def test_observed_run_without_checkpoint_omits_durability_and_uses_values_barrier(
    tmp_path,
    monkeypatch,
):
    case = _case(tmp_path, monkeypatch, checkpoint_enabled=False)

    result = AnalysisRunner(case.owner).run(
        case.request,
        observation_context=case.context,
    )

    kwargs = _stream_kwargs(case)
    assert kwargs["stream_mode"] == ["tasks", "updates", "values"]
    assert kwargs["version"] == "v1"
    assert "durability" not in kwargs
    assert "values" in _modes(case)
    assert _message_texts(result.final_state) == [
        "AAPL",
        "first applied message",
        "second applied message",
    ]


@pytest.mark.parametrize("checkpoint_enabled", [True, False])
def test_cancellation_is_observed_only_after_the_next_durable_state_barrier(
    tmp_path,
    monkeypatch,
    checkpoint_enabled,
):
    token = CancellationToken()
    case = _case(
        tmp_path,
        monkeypatch,
        checkpoint_enabled=checkpoint_enabled,
        cancellation_token=token,
        cancel_after_update=True,
    )
    kwargs = {
        "observation_context": case.context,
        "cancellation_token": token,
    }
    if checkpoint_enabled:
        kwargs["checkpoint_guard"] = case.guard

    with pytest.raises(AnalysisCancelled) as cancelled:
        AnalysisRunner(case.owner).run(case.request, **kwargs)

    modes = _modes(case)
    update_index = modes.index("updates")
    barrier_mode = "checkpoints" if checkpoint_enabled else "values"
    assert barrier_mode in modes[update_index + 1 :]
    assert cancelled.value.partial_state is not None
    assert cancelled.value.partial_state["market_report"] == "first applied report"
    assert _message_texts(cancelled.value.partial_state) == [
        "AAPL",
        "first applied message",
    ]
    case.owner._log_state.assert_not_called()
    case.owner.memory_log.store_decision.assert_not_called()


def test_db_ahead_recovery_only_appends_and_second_reconciliation_is_noop(tmp_path):
    store = RunStore(tmp_path / "runs")
    snapshot = RunSnapshot.create(ticker="AAPL", analysis_date="2026-07-18")
    store.create_run(snapshot)
    artifact = store.store_artifact(
        snapshot.run_id,
        kind="data",
        value={"market_report": "durable"},
    )
    commit = ObservationCommitV1(
        SERIALIZER_VERSION,
        BUSINESS_PROJECTION_VERSION,
        AGENT_STATE_SCHEMA_SHA256,
        "maintenance",
        "task-durable",
        0,
        artifact.content_sha256,
        "First",
    )
    store.append_event(
        RunEventDraft(
            snapshot.run_id,
            "graph.task_output_ready",
            {
                "observation_commit": commit.as_dict(),
                "graph_step": 0,
                "node_id": "First",
                "business_delta_artifact_id": artifact.artifact_id,
                "media_type": artifact.media_type,
                "content_sha256": artifact.content_sha256,
            },
        )
    )
    latest = SimpleNamespace(
        config={"configurable": {"checkpoint_id": "cp-durable"}},
        checkpoint={
            "id": "cp-durable",
            "channel_values": {
                "market_report": "durable",
                RESERVED_OBSERVATION_FIELD: {
                    commit.graph_task_id: commit.as_dict()
                },
            },
        },
        metadata={"step": 0},
        pending_writes=[],
    )
    event_path = tmp_path / "runs" / snapshot.run_id / "events.jsonl"
    before = event_path.read_bytes()

    plan = reconcile_checkpoint_frontier(
        store.read_events(snapshot.run_id),
        latest,
        None,
        read_artifact=lambda artifact_id: store.read_artifact(
            snapshot.run_id,
            artifact_id,
        ),
    )
    persisted = apply_reconciliation_plan(
        store,
        snapshot.run_id,
        plan,
        current_checkpoint_id=lambda: "cp-durable",
    )

    after_first = event_path.read_bytes()
    assert after_first.startswith(before)
    assert [event.type for event in persisted] == ["graph.checkpoint_committed"]

    retry = reconcile_checkpoint_frontier(
        store.read_events(snapshot.run_id),
        latest,
        None,
        read_artifact=lambda artifact_id: store.read_artifact(
            snapshot.run_id,
            artifact_id,
        ),
    )
    assert apply_reconciliation_plan(
        store,
        snapshot.run_id,
        retry,
        current_checkpoint_id=lambda: "cp-durable",
    ) == ()
    assert event_path.read_bytes() == after_first
