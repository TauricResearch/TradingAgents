from copy import deepcopy
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import ExecutionInfo, Runtime

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import GraphSetup
from tradingagents.observability.graph_tasks import (
    GraphObservationRunContext,
    ObservedGraphTask,
    ObservedNode,
    ObservedToolNode,
)
from tradingagents.observability.observer import DurableRunObserver
from tradingagents.observability.projections import (
    EvidenceConfigDrift,
    RoleProjectionRunContext,
)
from tradingagents.web.run_models import RunSnapshot
from tradingagents.web.store import RunStore


def _run_context(tmp_path, *, effective_config=None, actual_config_getter=None):
    store = RunStore(tmp_path)
    snapshot = RunSnapshot.create(ticker="AAPL", analysis_date="2026-07-17")
    store.create_run(snapshot)
    observer = DurableRunObserver(store, snapshot.run_id)
    projection = RoleProjectionRunContext(
        effective_config=effective_config or DEFAULT_CONFIG,
        effective_config_artifact_id="config:frozen",
    )
    kwargs = {}
    if actual_config_getter is not None:
        kwargs["actual_config_getter"] = actual_config_getter
    context = GraphObservationRunContext(observer, projection, **kwargs)
    return store, snapshot, observer, context


def _initial_state(context=None):
    return Propagator().create_initial_state(
        "AAPL",
        "2026-07-17",
        instrument_context="Ticker: AAPL; Apple Inc.",
        observation_context=context,
    )


def _runtime(context, task_id="task-1"):
    return Runtime(
        context=context,
        execution_info=ExecutionInfo(
            checkpoint_id="checkpoint-parent",
            checkpoint_ns="node:test",
            task_id=task_id,
        ),
    )


def _config(step=1, node="test"):
    return {"metadata": {"langgraph_step": step, "langgraph_node": node}}


def test_synthetic_input_has_deterministic_task_and_evidence_channels(tmp_path):
    store, snapshot, _observer, context = _run_context(tmp_path)

    state = _initial_state(context)

    task_id = f"{snapshot.run_id}:input"
    assert state["canonical_company_profile"] == {}
    assert state["evidence_status"] == ""
    assert state["evidence_report"] == ""
    assert state["_observation_commits"][task_id]["task_kind"] == "input"
    assert state["_observation_commits"][task_id]["graph_step"] == 0
    output_ready = next(
        event for event in store.read_events(snapshot.run_id) if event.type == "graph.task_output_ready"
    )
    assert output_ready.payload["observation_commit"]["graph_task_id"] == task_id


def test_runtime_task_stream_id_is_the_commit_token_key(tmp_path):
    store, snapshot, _observer, context = _run_context(tmp_path)

    def market_node(_state):
        return {
            "messages": [AIMessage(content="Market is stable")],
            "market_report": "Market is stable",
        }

    workflow = StateGraph(AgentState, context_schema=GraphObservationRunContext)
    workflow.add_node(
        "Market Analyst",
        ObservedNode("analyst.market", "Market Analyst", market_node),
    )
    workflow.add_edge(START, "Market Analyst")
    workflow.add_edge("Market Analyst", END)
    graph = workflow.compile()

    task_events = [
        payload
        for mode, payload in graph.stream(
            _initial_state(),
            context=context,
            stream_mode=["tasks", "updates"],
        )
        if mode == "tasks" and "input" in payload
    ]

    assert len(task_events) == 1
    runtime_task_id = task_events[0]["id"]
    candidate = next(
        event
        for event in store.read_events(snapshot.run_id)
        if event.type == "graph.task_output_ready"
    )
    assert candidate.payload["observation_commit"]["graph_task_id"] == runtime_task_id
    assert candidate.payload["observation_commit"]["task_kind"] == "role"
    snapshot_event = next(
        event for event in store.read_events(snapshot.run_id) if event.type == "input.state_snapshot"
    )
    assert snapshot_event.payload["state_fields"] == [
        "instrument_context",
        "trade_date",
        "messages",
    ]
    turn_ready = next(
        event for event in store.read_events(snapshot.run_id) if event.type == "turn.output_ready"
    )
    assert turn_ready.payload["artifact_id"] == candidate.payload["business_delta_artifact_id"]


@tool
def lookup_price(symbol: str) -> str:
    """Return a deterministic test price."""
    return f"{symbol}=210"


def test_role_tool_role_reentry_keeps_turn_and_uses_three_runtime_task_ids(tmp_path):
    store, snapshot, observer, context = _run_context(tmp_path)

    def market_node(state):
        last = state["messages"][-1]
        callback_id = "model-final" if isinstance(last, ToolMessage) else "model-request"
        observer.on_llm_start({}, ["market prompt"], run_id=callback_id)
        observer.on_llm_end(SimpleNamespace(llm_output={}), run_id=callback_id)
        if isinstance(last, ToolMessage):
            return {
                "messages": [AIMessage(content="Final market report")],
                "market_report": "Final market report",
            }
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
                        }
                    ],
                )
            ],
            "market_report": "",
        }

    workflow = StateGraph(AgentState, context_schema=GraphObservationRunContext)
    workflow.add_node(
        "Market Analyst",
        ObservedNode("analyst.market", "Market Analyst", market_node),
    )
    workflow.add_node(
        "tools_market",
        ObservedToolNode("tools_market", ToolNode([lookup_price])),
    )

    def route(state):
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else "done"

    workflow.add_edge(START, "Market Analyst")
    workflow.add_conditional_edges(
        "Market Analyst",
        route,
        {"tools": "tools_market", "done": END},
    )
    workflow.add_edge("tools_market", "Market Analyst")
    graph = workflow.compile()

    list(
        graph.stream(
            _initial_state(),
            {"callbacks": [observer]},
            context=context,
            stream_mode=["tasks", "updates"],
        )
    )

    events = store.read_events(snapshot.run_id)
    role_candidates = [
        event
        for event in events
        if event.type == "graph.task_output_ready"
        and event.payload["observation_commit"]["task_kind"] == "role"
    ]
    tool_candidate = next(
        event
        for event in events
        if event.type == "graph.task_output_ready"
        and event.payload["observation_commit"]["task_kind"] == "tool"
    )
    requested = next(event for event in events if event.type == "tool.requested")
    executed = next(event for event in events if event.type == "tool.execution_started")
    snapshots = [event for event in events if event.type == "input.state_snapshot"]

    assert len(role_candidates) == 2
    task_ids = {
        role_candidates[0].payload["observation_commit"]["graph_task_id"],
        tool_candidate.payload["observation_commit"]["graph_task_id"],
        role_candidates[1].payload["observation_commit"]["graph_task_id"],
    }
    assert len(task_ids) == 3
    assert requested.payload["graph_task_id"] == role_candidates[0].payload["observation_commit"][
        "graph_task_id"
    ]
    assert executed.payload["graph_task_id"] == tool_candidate.payload["observation_commit"][
        "graph_task_id"
    ]
    assert len({event.payload["turn_id"] for event in snapshots}) == 1
    assert requested.payload["turn_id"] == snapshots[0].payload["turn_id"]
    assert tool_candidate.payload["observation_commit"]["tool_call_ids"] == ["call-price"]


def test_evidence_config_drift_fails_before_evaluator_runs(tmp_path):
    expected = deepcopy(DEFAULT_CONFIG)
    actual = deepcopy(DEFAULT_CONFIG)
    actual["news_min_company_items"] += 1
    store, snapshot, _observer, context = _run_context(
        tmp_path,
        effective_config=expected,
        actual_config_getter=lambda: actual,
    )
    called = False

    def evidence_node(_state):
        nonlocal called
        called = True
        return {"evidence_status": "PASS"}

    observed = ObservedNode("evidence.steward", "Evidence Steward", evidence_node)

    with pytest.raises(EvidenceConfigDrift):
        observed(
            _initial_state(),
            _config(5, "Evidence Steward"),
            _runtime(context, "task-evidence"),
        )

    assert called is False
    config_event = next(
        event for event in store.read_events(snapshot.run_id) if event.type == "input.config_snapshot"
    )
    assert config_event.payload["config_match"] is False
    assert config_event.payload["differing_keys"] == ["news_min_company_items"]
    assert not any(
        event.type == "graph.task_output_ready" for event in store.read_events(snapshot.run_id)
    )


def test_evidence_outputs_are_declared_checkpointed_business_fields(tmp_path):
    effective = deepcopy(DEFAULT_CONFIG)
    store, snapshot, _observer, context = _run_context(
        tmp_path,
        effective_config=effective,
        actual_config_getter=lambda: effective,
    )
    observed = ObservedNode(
        "evidence.steward",
        "Evidence Steward",
        lambda _state: {
            "canonical_company_profile": {"ticker": "AAPL", "name": "Apple Inc."},
            "evidence_status": "PASS",
            "evidence_report": "Sufficient coverage",
        },
    )

    output = observed(
        _initial_state(),
        _config(5, "Evidence Steward"),
        _runtime(context, "task-evidence-pass"),
    )

    assert output["evidence_status"] == "PASS"
    assert output["evidence_report"] == "Sufficient coverage"
    assert output["canonical_company_profile"]["name"] == "Apple Inc."
    assert output["_observation_commits"]["task-evidence-pass"]["task_kind"] == "role"
    candidate = next(
        event
        for event in store.read_events(snapshot.run_id)
        if event.type == "graph.task_output_ready"
    )
    assert candidate.payload["observation_commit"]["graph_task_id"] == "task-evidence-pass"


def test_node_exception_has_no_false_output_or_abandoned_candidate(tmp_path):
    store, snapshot, _observer, context = _run_context(tmp_path)

    def fail(_state):
        raise RuntimeError("provider failed before output")

    observed = ObservedNode("analyst.market", "Market Analyst", fail)

    with pytest.raises(RuntimeError, match="provider failed"):
        observed(
            _initial_state(),
            _config(1, "Market Analyst"),
            _runtime(context, "task-failed"),
        )

    event_types = [event.type for event in store.read_events(snapshot.run_id)]
    assert "graph.task_started" in event_types
    assert "graph.task_output_ready" not in event_types
    assert "graph.task_abandoned" not in event_types


def test_maintenance_task_gets_its_own_commit_token(tmp_path):
    store, snapshot, _observer, context = _run_context(tmp_path)
    observed = ObservedGraphTask(
        "Msg Clear Market",
        "maintenance",
        lambda _state: {"market_report": "cleared"},
    )

    output = observed(
        _initial_state(),
        _config(4, "Msg Clear Market"),
        _runtime(context, "task-clear"),
    )

    assert output["_observation_commits"]["task-clear"]["task_kind"] == "maintenance"
    candidate = next(
        event for event in store.read_events(snapshot.run_id) if event.type == "graph.task_output_ready"
    )
    assert candidate.payload["observation_commit"]["graph_task_id"] == "task-clear"


def test_observed_graph_registers_only_selected_analyst_and_keeps_all_fixed_roles():
    class DummyConditional:
        def should_continue_news(self, _state):
            return "Msg Clear News"

        def should_continue_debate(self, _state):
            return "Research Manager"

        def should_continue_risk_analysis(self, _state):
            return "Portfolio Manager"

    workflow = GraphSetup(
        None,
        None,
        {"news": lambda state: state},
        DummyConditional(),
    ).setup_graph(["news"], observation_enabled=True)
    graph = workflow.compile()

    assert "News Analyst" in graph.nodes
    assert "Market Analyst" not in graph.nodes
    assert "Sentiment Analyst" not in graph.nodes
    assert "Fundamentals Analyst" not in graph.nodes
    assert "Evidence Steward" in graph.nodes
    assert "Portfolio Manager" in graph.nodes
