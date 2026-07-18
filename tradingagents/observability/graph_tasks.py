"""LangGraph task wrappers that make state mutation candidates auditable."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.runtime import Runtime

from tradingagents.dataflows.config import get_config
from tradingagents.observability.canonical import (
    AGENT_STATE_SCHEMA_SHA256,
    BUSINESS_PROJECTION_VERSION,
    SERIALIZER_VERSION,
    business_delta_sha256,
    project_business_delta,
)
from tradingagents.observability.events import ArtifactRef, ObservationCommitV1, RunEventDraft
from tradingagents.observability.observer import DurableRunObserver
from tradingagents.observability.projections import (
    EvidenceConfigDrift,
    RoleProjectionRunContext,
    evidence_config_snapshot,
    project_role_input,
)
from tradingagents.observability.redaction import redact_recursive


TaskKind = Literal["input", "role", "tool", "maintenance"]


@dataclass(frozen=True)
class GraphObservationRunContext:
    observer: DurableRunObserver
    role_projection: RoleProjectionRunContext
    actual_config_getter: Callable[[], Mapping[str, Any]] = get_config


@dataclass(frozen=True)
class _PersistedCandidate:
    output: dict[str, Any]
    artifact: ArtifactRef


class ObservedGraphTask:
    """Wrap one application-state writer without changing legacy execution."""

    def __init__(self, node_id: str, task_kind: TaskKind, node: Any):
        self.node_id = node_id
        self.task_kind = task_kind
        self.node = node

    def __call__(
        self,
        state: Mapping[str, Any],
        config: RunnableConfig,
        runtime: Runtime[GraphObservationRunContext],
    ) -> dict[str, Any]:
        run_context = runtime.context
        if not isinstance(run_context, GraphObservationRunContext):
            return self._invoke(state, config)
        graph_task_id, graph_step = _task_identity(runtime, config)
        observer = run_context.observer
        _emit_task_started(observer, graph_task_id, graph_step, self.node_id)
        delta = self._invoke(state, config)
        return _persist_output_candidate(
            observer,
            delta,
            graph_task_id=graph_task_id,
            graph_step=graph_step,
            node_id=self.node_id,
            task_kind=self.task_kind,
        ).output

    def _invoke(self, state: Mapping[str, Any], config: RunnableConfig) -> dict[str, Any]:
        if isinstance(self.node, Runnable):
            result = self.node.invoke(state, config=config)
        else:
            result = self.node(state)
        if not isinstance(result, Mapping):
            raise TypeError(f"observed node {self.node_id} must return a mapping")
        return dict(result)


class ObservedNode(ObservedGraphTask):
    def __init__(self, actor_id: str, node_id: str, node: Any):
        super().__init__(node_id, "role", node)
        self.actor_id = actor_id

    def __call__(
        self,
        state: Mapping[str, Any],
        config: RunnableConfig,
        runtime: Runtime[GraphObservationRunContext],
    ) -> dict[str, Any]:
        run_context = runtime.context
        if not isinstance(run_context, GraphObservationRunContext):
            return self._invoke(state, config)
        graph_task_id, graph_step = _task_identity(runtime, config)
        observer = run_context.observer
        turn_ref = observer.open_turn_for_actor(self.actor_id)
        if turn_ref is None:
            turn_ref = observer.start_turn(
                actor_id=self.actor_id,
                graph_task_id=graph_task_id,
                graph_step=graph_step,
                turn_index=observer.next_turn_index(self.actor_id),
            )
        _emit_task_started(observer, graph_task_id, graph_step, self.node_id)
        with observer.invocation_scope(
            turn_ref,
            graph_task_id=graph_task_id,
            graph_step=graph_step,
        ) as observation_context:
            _capture_role_input(
                observer,
                turn_ref.turn_id,
                graph_task_id,
                graph_step,
                state,
                self.actor_id,
                run_context,
            )
            delta = self._invoke(state, config)
            tool_calls = _tool_calls_from_delta(delta)
            if tool_calls:
                attempt_id = observer.latest_attempt_id(turn_ref.turn_id, graph_task_id)
                if attempt_id is None:
                    raise AssertionError("tool-calling role output has no task-local model attempt")
                for call in tool_calls:
                    observer.request_tool(
                        turn_ref,
                        attempt_id=attempt_id,
                        tool_call_id=call["id"],
                        tool_name=call["name"],
                        arguments=call["args"],
                        context=observation_context,
                    )
            candidate = _persist_output_candidate(
                observer,
                delta,
                graph_task_id=graph_task_id,
                graph_step=graph_step,
                node_id=self.node_id,
                task_kind="role",
                turn_id=turn_ref.turn_id,
                tool_call_ids=tuple(call["id"] for call in tool_calls),
                actor_id=self.actor_id,
            )
            if not tool_calls:
                observer.mark_turn_output_ready(
                    turn_ref.turn_id,
                    artifact=candidate.artifact,
                    context=observation_context,
                )
            return candidate.output


class ObservedToolNode(ObservedGraphTask):
    def __init__(self, node_id: str, node: Any):
        super().__init__(node_id, "tool", node)

    def __call__(
        self,
        state: Mapping[str, Any],
        config: RunnableConfig,
        runtime: Runtime[GraphObservationRunContext],
    ) -> dict[str, Any]:
        run_context = runtime.context
        if not isinstance(run_context, GraphObservationRunContext):
            return self._invoke(state, config)
        graph_task_id, graph_step = _task_identity(runtime, config)
        tool_calls = _tool_calls_from_messages(state.get("messages"))
        if not tool_calls:
            raise AssertionError("observed ToolNode has no model tool request")
        observer = run_context.observer
        turn_refs = [observer.tool_turn_ref(call["id"]) for call in tool_calls]
        turn_ref = turn_refs[0]
        if any(ref != turn_ref for ref in turn_refs[1:]):
            raise AssertionError("one ToolNode task cannot span multiple logical turns")
        _emit_task_started(observer, graph_task_id, graph_step, self.node_id)
        with observer.invocation_scope(
            turn_ref,
            graph_task_id=graph_task_id,
            graph_step=graph_step,
            invocation_path="tool_node",
        ):
            delta = self._invoke(state, config)
        expected_ids = tuple(call["id"] for call in tool_calls)
        actual_ids = _tool_message_ids(delta.get("messages"))
        if set(actual_ids) != set(expected_ids) or len(actual_ids) != len(expected_ids):
            raise AssertionError("ToolNode output IDs do not match persisted model requests")
        return _persist_output_candidate(
            observer,
            delta,
            graph_task_id=graph_task_id,
            graph_step=graph_step,
            node_id=self.node_id,
            task_kind="tool",
            turn_id=turn_ref.turn_id,
            tool_call_ids=expected_ids,
            actor_id=turn_ref.actor_id,
        ).output


def observe_initial_input(
    state: Mapping[str, Any],
    run_context: GraphObservationRunContext,
) -> dict[str, Any]:
    graph_task_id = f"{run_context.observer.run_id}:input"
    _emit_task_started(run_context.observer, graph_task_id, 0, "__input__")
    return _persist_output_candidate(
        run_context.observer,
        dict(state),
        graph_task_id=graph_task_id,
        graph_step=0,
        node_id=None,
        task_kind="input",
    ).output


def _task_identity(
    runtime: Runtime[GraphObservationRunContext],
    config: RunnableConfig,
) -> tuple[str, int]:
    if runtime.execution_info is None or not runtime.execution_info.task_id:
        raise AssertionError("LangGraph runtime task_id is required for observation")
    metadata = config.get("metadata") or {}
    graph_step = metadata.get("langgraph_step")
    if not isinstance(graph_step, int) or graph_step < 0:
        raise AssertionError("LangGraph candidate step is required for observation")
    return runtime.execution_info.task_id, graph_step


def _emit_task_started(
    observer: DurableRunObserver,
    graph_task_id: str,
    graph_step: int,
    node_id: str,
) -> None:
    observer.emit(
        RunEventDraft(
            observer.run_id,
            "graph.task_started",
            {
                "graph_task_id": graph_task_id,
                "graph_step": graph_step,
                "node_id": node_id,
            },
            node_id=node_id,
            status="started",
        )
    )


def _capture_role_input(
    observer: DurableRunObserver,
    turn_id: str,
    graph_task_id: str,
    graph_step: int,
    state: Mapping[str, Any],
    actor_id: str,
    run_context: GraphObservationRunContext,
) -> None:
    projection = project_role_input(actor_id, state, run_context.role_projection)
    redacted = redact_recursive(projection.as_dict())
    artifact = observer.store_artifact("data", redacted.value)
    observer.emit(
        RunEventDraft(
            observer.run_id,
            "input.state_snapshot",
            {
                "turn_id": turn_id,
                "graph_task_id": graph_task_id,
                "graph_step": graph_step,
                "attempt_id": None,
                "capture_kind": "node_entry",
                "artifact_id": artifact.artifact_id,
                "content_sha256": artifact.content_sha256,
                "redaction_manifest": [record.path for record in redacted.manifest],
                "projection_version": projection.projection_version,
                "state_fields": list(projection.state_fields),
                "effective_config_artifact_id": projection.effective_config_artifact_id,
            },
            actor_id=actor_id,
            node_id=projection.node_id,
        )
    )
    if actor_id == "evidence.steward":
        _capture_and_verify_evidence_config(
            observer,
            turn_id,
            graph_task_id,
            graph_step,
            run_context,
            actor_id,
            projection.node_id,
        )


def _capture_and_verify_evidence_config(
    observer: DurableRunObserver,
    turn_id: str,
    graph_task_id: str,
    graph_step: int,
    run_context: GraphObservationRunContext,
    actor_id: str,
    node_id: str,
) -> None:
    expected = evidence_config_snapshot(run_context.role_projection.effective_config)
    actual = evidence_config_snapshot(run_context.actual_config_getter())
    keys = set(expected.values) | set(actual.values)
    differing_keys = tuple(
        sorted(key for key in keys if expected.values.get(key) != actual.values.get(key))
    )
    artifact = observer.store_artifact("data", actual.as_dict())
    observer.emit(
        RunEventDraft(
            observer.run_id,
            "input.config_snapshot",
            {
                "turn_id": turn_id,
                "graph_task_id": graph_task_id,
                "graph_step": graph_step,
                "attempt_id": None,
                "capture_kind": "evidence_config",
                "artifact_id": artifact.artifact_id,
                "content_sha256": artifact.content_sha256,
                "redaction_manifest": list(actual.redaction_manifest),
                "expected_sha256": expected.sha256,
                "actual_sha256": actual.sha256,
                "config_match": not differing_keys,
                "differing_keys": list(differing_keys),
            },
            actor_id=actor_id,
            node_id=node_id,
        )
    )
    if differing_keys:
        raise EvidenceConfigDrift(
            expected_sha256=expected.sha256,
            actual_sha256=actual.sha256,
            differing_keys=differing_keys,
        )


def _persist_output_candidate(
    observer: DurableRunObserver,
    delta: Mapping[str, Any],
    *,
    graph_task_id: str,
    graph_step: int,
    node_id: str | None,
    task_kind: TaskKind,
    turn_id: str | None = None,
    tool_call_ids: tuple[str, ...] = (),
    actor_id: str | None = None,
) -> _PersistedCandidate:
    business_delta = project_business_delta(delta)
    artifact = observer.store_artifact("data", business_delta)
    commit = ObservationCommitV1(
        serializer_version=SERIALIZER_VERSION,
        projection_version=BUSINESS_PROJECTION_VERSION,
        agent_state_schema_sha256=AGENT_STATE_SCHEMA_SHA256,
        task_kind=task_kind,
        graph_task_id=graph_task_id,
        graph_step=graph_step,
        business_delta_sha256=business_delta_sha256(delta),
        node_id=node_id,
        turn_id=turn_id,
        tool_call_ids=tool_call_ids,
    )
    observer.emit(
        RunEventDraft(
            observer.run_id,
            "graph.task_output_ready",
            {
                "observation_commit": commit.as_dict(),
                "graph_step": graph_step,
                "node_id": node_id or "__input__",
                "business_delta_artifact_id": artifact.artifact_id,
                "media_type": artifact.media_type,
                "content_sha256": artifact.content_sha256,
            },
            actor_id=actor_id,
            node_id=node_id,
            status="candidate",
        )
    )
    output = dict(delta)
    output["_observation_commits"] = {graph_task_id: commit.as_dict()}
    return _PersistedCandidate(output=output, artifact=artifact)


def _tool_calls_from_delta(delta: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _tool_calls_from_messages(delta.get("messages"))


def _tool_calls_from_messages(messages: Any) -> list[dict[str, Any]]:
    sequence = list(messages or [])
    for message in reversed(sequence):
        if isinstance(message, AIMessage):
            return [
                {"id": str(call["id"]), "name": str(call["name"]), "args": call.get("args", {})}
                for call in message.tool_calls
            ]
    return []


def _tool_message_ids(messages: Any) -> tuple[str, ...]:
    return tuple(
        str(message.tool_call_id)
        for message in list(messages or [])
        if isinstance(message, ToolMessage)
    )
