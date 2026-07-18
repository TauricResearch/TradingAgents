from types import SimpleNamespace
from uuid import UUID

import pytest
from langchain_core.callbacks import CallbackManager
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tradingagents.observability.context import (
    current_observation_context,
    observation_scope,
)
from tradingagents.observability.observer import DurableRunObserver
from tradingagents.web.run_models import RunSnapshot
from tradingagents.web.store import RunStore


class Clock:
    def __init__(self):
        self.value = 10.0

    def __call__(self):
        value = self.value
        self.value += 0.025
        return value


def _observer(tmp_path, *, development_assertions=True):
    store = RunStore(tmp_path)
    snapshot = RunSnapshot.create(ticker="AAPL", analysis_date="2026-07-17")
    store.create_run(snapshot)
    observer = DurableRunObserver(
        store,
        snapshot.run_id,
        development_assertions=development_assertions,
        clock=Clock(),
    )
    return store, snapshot, observer


def test_observation_scope_restores_previous_context(tmp_path):
    _store, _snapshot, observer = _observer(tmp_path)
    ref = observer.start_turn(
        actor_id="analyst.market",
        graph_task_id="task-1",
        graph_step=1,
        turn_index=1,
    )

    assert current_observation_context() is None
    context = observer.context_for_turn(
        ref.turn_id,
        graph_task_id="task-1",
        graph_step=1,
    )
    with observation_scope(context):
        assert current_observation_context(required=True) == context
    assert current_observation_context() is None


def test_model_prompt_attempt_and_usage_join_to_the_same_turn(tmp_path):
    store, snapshot, observer = _observer(tmp_path)
    ref = observer.start_turn(
        actor_id="analyst.fundamentals",
        graph_task_id="task-fundamentals",
        graph_step=2,
        turn_index=1,
    )
    response = SimpleNamespace(llm_output={"token_usage": {"total_tokens": 42}})

    with observer.invocation_scope(
        ref,
        graph_task_id="task-fundamentals",
        graph_step=2,
    ):
        observer.on_chat_model_start(
            {"id": ["langchain", "ChatOpenAI"]},
            [[HumanMessage(content="Analyze", additional_kwargs={"api_key": "fake"})]],
            run_id="model-call-1",
            metadata={
                "ls_provider": "openai",
                "ls_model_name": "gpt-test",
                "invocation_path": "structured",
            },
        )
    observer.on_llm_end(response, run_id="model-call-1")

    events = store.read_events(snapshot.run_id)
    prompt = next(event for event in events if event.type == "input.prompt_snapshot")
    started = next(event for event in events if event.type == "model.started")
    completed = next(event for event in events if event.type == "model.completed")
    assert prompt.payload["turn_id"] == ref.turn_id
    assert prompt.payload["redaction_manifest"]
    assert prompt.payload["attempt_id"] == started.payload["attempt_id"]
    assert completed.payload["attempt_id"] == started.payload["attempt_id"]
    assert completed.payload["model_call_id"] == "model-call-1"
    assert completed.payload["usage"] == {"total_tokens": 42}
    assert completed.payload["duration_ms"] == 25
    prompt_bytes = store.read_artifact(snapshot.run_id, prompt.payload["artifact_id"])
    assert b"fake" not in prompt_bytes


def test_retries_get_new_attempt_ids_without_new_turn(tmp_path):
    store, snapshot, observer = _observer(tmp_path)
    ref = observer.start_turn(
        actor_id="researcher.bull",
        graph_task_id="task-bull",
        graph_step=3,
        turn_index=2,
    )

    for call_id in ("model-retry-1", "model-retry-2"):
        with observer.invocation_scope(
            ref,
            graph_task_id="task-bull",
            graph_step=3,
        ):
            observer.on_llm_start(
                {"id": ["provider", "model"]},
                ["prompt"],
                run_id=call_id,
            )
        observer.on_llm_error(RuntimeError("retry"), run_id=call_id)

    failures = [event for event in store.read_events(snapshot.run_id) if event.type == "model.failed"]
    assert len(failures) == 2
    assert {event.payload["turn_id"] for event in failures} == {ref.turn_id}
    assert len({event.payload["attempt_id"] for event in failures}) == 2


def test_unattributed_callback_asserts_in_development_and_diagnoses_in_production(tmp_path):
    _store, _snapshot, development = _observer(tmp_path / "development")
    with pytest.raises(AssertionError, match="unattributed callback"):
        development.on_llm_start({}, ["prompt"], run_id="missing")

    store, snapshot, production = _observer(
        tmp_path / "production",
        development_assertions=False,
    )
    production.on_llm_start({}, ["prompt"], run_id="missing")

    diagnostic = store.read_events(snapshot.run_id)[0]
    assert diagnostic.type == "diagnostic.unattributed"
    assert diagnostic.payload == {
        "callback_kind": "model.llm.started",
        "callback_run_id": "missing",
    }


def test_logical_tool_and_execution_rebuild_by_ids_not_callback_order(tmp_path):
    store, snapshot, observer = _observer(tmp_path)
    ref = observer.start_turn(
        actor_id="analyst.market",
        graph_task_id="task-market",
        graph_step=1,
        turn_index=1,
    )
    observer.request_tool(
        ref,
        attempt_id="attempt-1",
        tool_call_id="call-price",
        tool_name="get_stock_data",
        arguments={"symbol": "AAPL"},
    )
    observer.request_tool(
        ref,
        attempt_id="attempt-1",
        tool_call_id="call-indicator",
        tool_name="get_indicators",
        arguments={"indicator": "macd"},
    )

    restarted = DurableRunObserver(
        store,
        snapshot.run_id,
        clock=Clock(),
        application_status_by_task={"task-market": "pending_apply"},
    )
    with restarted.invocation_scope(
        ref,
        graph_task_id="task-tools",
        graph_step=2,
        invocation_path="tool_node",
    ):
        indicator_execution = restarted.start_tool_execution(
            "call-indicator",
            tool_execution_id="execution-indicator",
        )
        price_execution = restarted.start_tool_execution(
            "call-price",
            tool_execution_id="execution-price",
        )
    restarted.complete_tool_execution(price_execution, {"close": 210})
    restarted.complete_tool_execution(indicator_execution, {"macd": 2.1})
    restarted.commit_tool("call-price", "checkpoint-event-10")

    events = store.read_events(snapshot.run_id)
    completed = [event for event in events if event.type == "tool.execution_completed"]
    assert [event.payload["tool_call_id"] for event in completed] == [
        "call-price",
        "call-indicator",
    ]
    assert all(event.payload["turn_id"] == ref.turn_id for event in completed)
    committed = next(event for event in events if event.type == "tool.committed")
    assert committed.payload["checkpoint_event_id"] == "checkpoint-event-10"


def test_tool_callbacks_use_tool_call_id_and_execution_uuid_not_order(tmp_path):
    store, snapshot, observer = _observer(tmp_path)
    assert observer.raise_error is True
    assert observer.run_inline is True
    ref = observer.start_turn(
        actor_id="analyst.market",
        graph_task_id="task-market",
        graph_step=1,
        turn_index=1,
    )
    observer.request_tool(
        ref,
        attempt_id="attempt-1",
        tool_call_id="call-a",
        tool_name="get_stock_data",
        arguments={"symbol": "AAPL"},
    )
    observer.request_tool(
        ref,
        attempt_id="attempt-1",
        tool_call_id="call-b",
        tool_name="get_indicators",
        arguments={"indicator": "macd"},
    )

    with observer.invocation_scope(
        ref,
        graph_task_id="task-tools",
        graph_step=2,
        invocation_path="tool_node",
    ):
        observer.on_tool_start(
            {"name": "get_indicators"},
            "macd",
            run_id="execution-b",
            tool_call_id="call-b",
        )
        observer.on_tool_start(
            {"name": "get_stock_data"},
            "AAPL",
            run_id="execution-a",
            tool_call_id="call-a",
        )
    observer.on_tool_end(
        ToolMessage(content="price", tool_call_id="call-a"),
        run_id="execution-a",
    )
    observer.on_tool_error(RuntimeError("indicator failed"), run_id="execution-b")

    terminal = [
        event
        for event in store.read_events(snapshot.run_id)
        if event.type in {"tool.execution_completed", "tool.execution_failed"}
    ]
    assert [(event.type, event.payload["tool_call_id"]) for event in terminal] == [
        ("tool.execution_completed", "call-a"),
        ("tool.execution_failed", "call-b"),
    ]
    assert {event.payload["tool_execution_id"] for event in terminal} == {
        "execution-a",
        "execution-b",
    }


def test_direct_call_scope_uses_the_existing_role_turn(tmp_path):
    _store, _snapshot, observer = _observer(tmp_path)
    ref = observer.start_turn(
        actor_id="evidence.steward",
        graph_task_id="task-evidence",
        graph_step=4,
        turn_index=1,
    )

    with observer.invocation_scope(
        ref,
        graph_task_id="task-evidence",
        graph_step=4,
    ):
        with observer.direct_call_scope("fundamentals.get_balance_sheet") as context:
            assert context.turn_id == ref.turn_id
            assert context.graph_task_id == "task-evidence"
            assert context.invocation_path == "direct:fundamentals.get_balance_sheet"
            assert current_observation_context(required=True).actor_id == "evidence.steward"
    assert current_observation_context() is None


def test_same_logical_turn_tracks_each_graph_reentry_task(tmp_path):
    store, snapshot, observer = _observer(tmp_path)
    ref = observer.start_turn(
        actor_id="analyst.market",
        graph_task_id="task-role-1",
        graph_step=1,
        turn_index=1,
    )

    with observer.invocation_scope(
        ref,
        graph_task_id="task-role-1",
        graph_step=1,
    ):
        observer.request_tool(
            ref,
            attempt_id="attempt-1",
            tool_call_id="call-price",
            tool_name="get_stock_data",
            arguments={"symbol": "AAPL"},
        )
    with observer.invocation_scope(
        ref,
        graph_task_id="task-tool-2",
        graph_step=2,
        invocation_path="tool_node",
        tool_call_id="call-price",
    ):
        execution_id = observer.start_tool_execution(
            "call-price",
            tool_execution_id="execution-price",
        )
    observer.complete_tool_execution(execution_id, {"close": 210})
    with observer.invocation_scope(
        ref,
        graph_task_id="task-role-3",
        graph_step=3,
        invocation_path="role_reentry",
    ):
        observer.on_llm_start({}, ["Summarize"], run_id="model-reentry")
    observer.on_llm_end(SimpleNamespace(llm_output={}), run_id="model-reentry")

    events = store.read_events(snapshot.run_id)
    requested = next(event for event in events if event.type == "tool.requested")
    executed = next(event for event in events if event.type == "tool.execution_started")
    model = next(event for event in events if event.type == "model.started")
    assert requested.payload["graph_task_id"] == "task-role-1"
    assert executed.payload["graph_task_id"] == "task-tool-2"
    assert model.payload["graph_task_id"] == "task-role-3"
    assert {requested.payload["turn_id"], executed.payload["turn_id"], model.payload["turn_id"]} == {
        ref.turn_id
    }


def test_llm_usage_reads_ai_message_usage_metadata(tmp_path):
    store, snapshot, observer = _observer(tmp_path)
    ref = observer.start_turn(
        actor_id="researcher.bear",
        graph_task_id="task-bear",
        graph_step=4,
        turn_index=1,
    )
    response = SimpleNamespace(
        llm_output=None,
        generations=[
            [
                SimpleNamespace(
                    message=AIMessage(
                        content="Bear case",
                        usage_metadata={
                            "input_tokens": 12,
                            "output_tokens": 8,
                            "total_tokens": 20,
                        },
                    )
                )
            ]
        ],
    )

    with observer.invocation_scope(
        ref,
        graph_task_id="task-bear",
        graph_step=4,
    ):
        observer.on_llm_start({}, ["Analyze downside"], run_id="model-usage")
    observer.on_llm_end(response, run_id="model-usage")

    completed = next(
        event for event in store.read_events(snapshot.run_id) if event.type == "model.completed"
    )
    assert completed.payload["usage"] == {
        "input_tokens": 12,
        "output_tokens": 8,
        "total_tokens": 20,
    }


def test_restart_only_restores_applied_or_pending_tool_requests(tmp_path):
    store, snapshot, observer = _observer(tmp_path)
    ref = observer.start_turn(
        actor_id="analyst.news",
        graph_task_id="task-candidate",
        graph_step=5,
        turn_index=1,
    )
    observer.request_tool(
        ref,
        attempt_id="attempt-candidate",
        tool_call_id="call-candidate",
        tool_name="get_news",
        arguments={"symbol": "AAPL"},
    )
    with observer.invocation_scope(
        ref,
        graph_task_id="task-pending",
        graph_step=6,
    ):
        observer.request_tool(
            ref,
            attempt_id="attempt-pending",
            tool_call_id="call-pending",
            tool_name="get_news",
            arguments={"symbol": "AAPL"},
        )

    restarted = DurableRunObserver(
        store,
        snapshot.run_id,
        application_status_by_task={
            "task-candidate": "candidate",
            "task-pending": "pending_apply",
        },
    )

    assert restarted.tool_turn_ref("call-pending").turn_id == ref.turn_id
    with pytest.raises(KeyError):
        restarted.tool_turn_ref("call-candidate")


def test_callback_manager_propagates_unattributed_assertion(tmp_path):
    _store, _snapshot, observer = _observer(tmp_path)
    manager = CallbackManager(handlers=[observer])

    with pytest.raises(AssertionError, match="unattributed callback"):
        manager.on_llm_start(
            {},
            ["prompt"],
            run_id=UUID("00000000-0000-0000-0000-000000000001"),
        )


def test_model_attempt_is_not_forgotten_before_terminal_event_is_durable(tmp_path):
    store = RunStore(tmp_path)
    snapshot = RunSnapshot.create(ticker="AAPL", analysis_date="2026-07-17")
    store.create_run(snapshot)
    fail_terminal = True

    def event_sink(draft):
        nonlocal fail_terminal
        if draft.type == "model.completed" and fail_terminal:
            raise OSError("simulated event durability failure")
        return store.append_event(draft)

    observer = DurableRunObserver(
        store,
        snapshot.run_id,
        event_sink=event_sink,
        clock=Clock(),
    )
    ref = observer.start_turn(
        actor_id="manager.portfolio",
        graph_task_id="task-portfolio",
        graph_step=9,
        turn_index=1,
    )
    with observer.invocation_scope(
        ref,
        graph_task_id="task-portfolio",
        graph_step=9,
    ):
        observer.on_llm_start({}, ["Decide"], run_id="model-durable")

    with pytest.raises(OSError, match="durability failure"):
        observer.on_llm_end(SimpleNamespace(llm_output={}), run_id="model-durable")
    fail_terminal = False
    observer.on_llm_end(SimpleNamespace(llm_output={}), run_id="model-durable")

    completed = [
        event for event in store.read_events(snapshot.run_id) if event.type == "model.completed"
    ]
    assert len(completed) == 1


def test_turn_output_only_completes_after_explicit_commit_boundary(tmp_path):
    store, snapshot, observer = _observer(tmp_path)
    ref = observer.start_turn(
        actor_id="manager.research",
        graph_task_id="task-manager",
        graph_step=7,
        turn_index=1,
    )

    observer.mark_turn_output_ready(ref.turn_id, {"decision": "hold"})
    before_commit = store.read_events(snapshot.run_id)
    assert not any(event.type == "turn.completed" for event in before_commit)

    observer.complete_turn(ref.turn_id, duration_ms=120)
    after_commit = store.read_events(snapshot.run_id)
    assert any(event.type == "turn.completed" for event in after_commit)
    status_events = [event for event in after_commit if event.type == "role.status_changed"]
    assert status_events[-1].payload["new_status"] == "completed"


def test_interrupted_turn_resume_reuses_id_and_reopens_aggregate_role(tmp_path):
    store, snapshot, observer = _observer(tmp_path)
    ref = observer.start_turn(
        actor_id="risk.neutral",
        graph_task_id="task-risk",
        graph_step=8,
        turn_index=1,
    )
    observer.interrupt_turn(ref.turn_id, duration_ms=50, reason="process_restart")

    restarted = DurableRunObserver(store, snapshot.run_id, clock=Clock())
    resumed = restarted.resume_turn(ref.turn_id, resumed_from_sequence=4)

    assert resumed.turn_id == ref.turn_id
    events = store.read_events(snapshot.run_id)
    assert [event.type for event in events if event.type == "turn.resumed"] == ["turn.resumed"]
    role_events = [event for event in events if event.type == "role.status_changed"]
    assert role_events[-1].payload["previous_status"] == "interrupted"
    assert role_events[-1].payload["new_status"] == "running"
