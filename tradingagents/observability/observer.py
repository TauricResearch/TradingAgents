"""Durable callback observer joining prompts, attempts, tools, and role turns."""

from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Any, Iterator, Mapping

from langchain_core.callbacks import BaseCallbackHandler

from tradingagents.observability.events import ArtifactRef, PersistedEvent, RunEventDraft
from tradingagents.observability.redaction import redact_recursive
from tradingagents.observability.roles import ROLES_BY_ACTOR_ID, role_instance_id
from tradingagents.web.store import RunStore

from .context import (
    ObservationContext,
    RoleTurnRef,
    current_observation_context,
    observation_scope,
)


@dataclass(frozen=True)
class _ModelAttempt:
    context: ObservationContext
    attempt_id: str
    model_call_id: str
    provider: str
    model: str
    invocation_path: str
    started_at: float


@dataclass(frozen=True)
class _ToolExecution:
    turn_ref: RoleTurnRef
    context: ObservationContext
    attempt_id: str
    tool_call_id: str
    tool_execution_id: str
    tool_name: str
    started_at: float


@dataclass
class _LogicalTool:
    turn_ref: RoleTurnRef
    request_context: ObservationContext
    attempt_id: str
    tool_name: str
    execution_context: ObservationContext | None = None


class DurableRunObserver(BaseCallbackHandler):
    """Persist observations before any future live publisher sees them."""

    raise_error = True
    run_inline = True

    def __init__(
        self,
        store: RunStore,
        run_id: str,
        *,
        event_sink=None,
        development_assertions: bool = True,
        clock=time.monotonic,
        application_status_by_task: Mapping[str, str] | None = None,
    ):
        self.store = store
        self.run_id = run_id
        self._event_sink = event_sink or store.append_event
        self.development_assertions = development_assertions
        self._clock = clock
        self._role_statuses: dict[str, str] = {}
        self._turns: dict[str, RoleTurnRef] = {}
        self._turn_contexts: dict[str, ObservationContext] = {}
        self._open_turn_ids: set[str] = set()
        self._logical_tools: dict[str, _LogicalTool] = {}
        self._model_attempts: dict[str, _ModelAttempt] = {}
        self._tool_executions: dict[str, _ToolExecution] = {}
        self._application_status_by_task = dict(application_status_by_task or {})
        self._state_lock = threading.RLock()
        self._rebuild_from_events()

    def emit(self, draft: RunEventDraft) -> PersistedEvent:
        if draft.run_id != self.run_id:
            raise ValueError("observer cannot emit into another run")
        return self._event_sink(draft)

    def store_artifact(
        self,
        kind: str,
        value: Any,
        *,
        media_type: str = "application/json",
    ) -> ArtifactRef:
        artifact = self.store.store_artifact(
            self.run_id,
            kind=kind,
            value=value,
            media_type=media_type,
        )
        self.emit(
            RunEventDraft(
                self.run_id,
                "artifact.written",
                {
                    "artifact_id": artifact.artifact_id,
                    "kind": artifact.kind,
                    "media_type": artifact.media_type,
                    "content_sha256": artifact.content_sha256,
                    "byte_size": artifact.byte_size,
                    "locator": artifact.locator,
                },
            )
        )
        return artifact

    def start_turn(
        self,
        *,
        actor_id: str,
        graph_task_id: str,
        graph_step: int,
        turn_index: int,
        turn_id: str | None = None,
    ) -> RoleTurnRef:
        role = ROLES_BY_ACTOR_ID[actor_id]
        ref = RoleTurnRef(
            run_id=self.run_id,
            actor_id=actor_id,
            node_id=role.node_id,
            role_instance_id=role_instance_id(self.run_id, actor_id),
            turn_id=turn_id or f"turn_{uuid.uuid4().hex}",
            turn_index=turn_index,
        )
        context = self._context(ref, graph_task_id, graph_step)
        with self._state_lock:
            if ref.turn_id in self._open_turn_ids:
                raise ValueError(f"turn is already open: {ref.turn_id}")
            previous = self._role_statuses.get(actor_id, "pending")
            self.emit(
                RunEventDraft(
                    self.run_id,
                    "role.status_changed",
                    {
                        "role_instance_id": ref.role_instance_id,
                        "previous_status": previous,
                        "new_status": "running",
                        "reason": "turn_started",
                        "turn_id": ref.turn_id,
                    },
                    team_id=role.team_id,
                    actor_id=actor_id,
                    node_id=role.node_id,
                    status="running",
                )
            )
            self.emit(
                RunEventDraft(
                    self.run_id,
                    "turn.started",
                    self._turn_payload(ref, context, "started"),
                    team_id=role.team_id,
                    actor_id=actor_id,
                    node_id=role.node_id,
                    status="started",
                )
            )
            self._role_statuses[actor_id] = "running"
            self._turns[ref.turn_id] = ref
            self._turn_contexts[ref.turn_id] = context
            self._open_turn_ids.add(ref.turn_id)
        return ref

    def context_for_turn(
        self,
        turn_id: str,
        *,
        graph_task_id: str,
        graph_step: int,
        invocation_path: str = "role",
        attempt_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> ObservationContext:
        with self._state_lock:
            ref = self._turns[turn_id]
        return self._context(
            ref,
            graph_task_id,
            graph_step,
            invocation_path=invocation_path,
            attempt_id=attempt_id,
            tool_call_id=tool_call_id,
        )

    @contextmanager
    def invocation_scope(
        self,
        turn_ref: RoleTurnRef,
        *,
        graph_task_id: str,
        graph_step: int,
        invocation_path: str = "role",
        attempt_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> Iterator[ObservationContext]:
        context = self._context(
            turn_ref,
            graph_task_id,
            graph_step,
            invocation_path=invocation_path,
            attempt_id=attempt_id,
            tool_call_id=tool_call_id,
        )
        with self._state_lock:
            known = self._turns.get(turn_ref.turn_id)
            if known != turn_ref:
                raise ValueError("unknown or mismatched logical turn")
            self._turn_contexts[turn_ref.turn_id] = context
        with observation_scope(context):
            yield context

    def open_turn_for_actor(self, actor_id: str) -> RoleTurnRef | None:
        with self._state_lock:
            candidates = [
                self._turns[turn_id]
                for turn_id in self._open_turn_ids
                if self._turns[turn_id].actor_id == actor_id
            ]
        return max(candidates, key=lambda ref: ref.turn_index) if candidates else None

    def tool_turn_ref(self, tool_call_id: str) -> RoleTurnRef:
        with self._state_lock:
            return self._logical_tools[tool_call_id].turn_ref

    def resume_turn(
        self,
        turn_id: str,
        resumed_from_sequence: int,
        *,
        graph_task_id: str | None = None,
        graph_step: int | None = None,
    ) -> RoleTurnRef:
        with self._state_lock:
            ref = self._turns[turn_id]
            previous_context = self._turn_contexts[turn_id]
        context = self._context(
            ref,
            graph_task_id or previous_context.graph_task_id,
            previous_context.graph_step if graph_step is None else graph_step,
        )
        role = ROLES_BY_ACTOR_ID[ref.actor_id]
        previous = self._role_statuses.get(ref.actor_id, "interrupted")
        self.emit(
            RunEventDraft(
                self.run_id,
                "role.status_changed",
                {
                    "role_instance_id": ref.role_instance_id,
                    "previous_status": previous,
                    "new_status": "running",
                    "reason": "turn_resumed",
                    "turn_id": turn_id,
                },
                team_id=role.team_id,
                actor_id=ref.actor_id,
                node_id=ref.node_id,
                status="running",
            )
        )
        self.emit(
            RunEventDraft(
                self.run_id,
                "turn.resumed",
                {
                    **self._turn_payload(ref, context, "resumed"),
                    "resumed_from_sequence": resumed_from_sequence,
                },
                team_id=role.team_id,
                actor_id=ref.actor_id,
                node_id=ref.node_id,
                status="resumed",
            )
        )
        with self._state_lock:
            self._turn_contexts[turn_id] = context
            self._open_turn_ids.add(turn_id)
            self._role_statuses[ref.actor_id] = "running"
        return ref

    def mark_turn_output_ready(
        self,
        turn_id: str,
        output: Any,
        *,
        context: ObservationContext | None = None,
    ) -> ArtifactRef:
        with self._state_lock:
            ref = self._turns[turn_id]
            event_context = context or current_observation_context() or self._turn_contexts[turn_id]
        self._assert_context_matches_turn(event_context, ref)
        artifact = self.store_artifact("data", output)
        role = ROLES_BY_ACTOR_ID[ref.actor_id]
        self.emit(
            RunEventDraft(
                self.run_id,
                "turn.output_ready",
                {
                    **self._turn_payload(ref, event_context, "output_ready"),
                    "artifact_id": artifact.artifact_id,
                },
                team_id=role.team_id,
                actor_id=ref.actor_id,
                node_id=ref.node_id,
                status="output_ready",
            )
        )
        return artifact

    def complete_turn(
        self,
        turn_id: str,
        *,
        duration_ms: int,
        reason: str = "checkpoint_committed",
    ) -> None:
        self._terminalize_turn(turn_id, "completed", duration_ms, reason)

    def interrupt_turn(self, turn_id: str, *, duration_ms: int, reason: str) -> None:
        self._terminalize_turn(turn_id, "interrupted", duration_ms, reason)

    def request_tool(
        self,
        turn_ref: RoleTurnRef,
        *,
        attempt_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: Any,
        context: ObservationContext | None = None,
    ) -> PersistedEvent:
        with self._state_lock:
            request_context = (
                context
                or current_observation_context()
                or self._turn_contexts[turn_ref.turn_id]
            )
            if tool_call_id in self._logical_tools:
                raise ValueError(f"duplicate logical tool_call_id: {tool_call_id}")
        self._assert_context_matches_turn(request_context, turn_ref)
        event = self.emit(
            RunEventDraft(
                self.run_id,
                "tool.requested",
                {
                    "turn_id": turn_ref.turn_id,
                    "graph_task_id": request_context.graph_task_id,
                    "attempt_id": attempt_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                },
                actor_id=turn_ref.actor_id,
                node_id=turn_ref.node_id,
                status="requested",
            )
        )
        with self._state_lock:
            self._logical_tools[tool_call_id] = _LogicalTool(
                turn_ref=turn_ref,
                request_context=request_context,
                attempt_id=attempt_id,
                tool_name=tool_name,
            )
        return event

    def start_tool_execution(
        self,
        tool_call_id: str,
        *,
        tool_execution_id: str | None = None,
        context: ObservationContext | None = None,
    ) -> str:
        with self._state_lock:
            logical = self._logical_tools[tool_call_id]
        execution_context = context or current_observation_context(required=True)
        assert execution_context is not None
        self._assert_context_matches_turn(execution_context, logical.turn_ref)
        execution_id = tool_execution_id or f"tool_execution_{uuid.uuid4().hex}"
        with self._state_lock:
            if execution_id in self._tool_executions:
                raise ValueError(f"duplicate tool execution id: {execution_id}")
        self.emit(
            RunEventDraft(
                self.run_id,
                "tool.execution_started",
                self._tool_payload(
                    logical.turn_ref,
                    execution_context,
                    logical.attempt_id,
                    tool_call_id,
                    logical.tool_name,
                    execution_id,
                ),
                actor_id=logical.turn_ref.actor_id,
                node_id=logical.turn_ref.node_id,
                status="started",
            )
        )
        execution = _ToolExecution(
            turn_ref=logical.turn_ref,
            context=execution_context,
            attempt_id=logical.attempt_id,
            tool_call_id=tool_call_id,
            tool_execution_id=execution_id,
            tool_name=logical.tool_name,
            started_at=self._clock(),
        )
        with self._state_lock:
            logical.execution_context = execution_context
            self._tool_executions[execution_id] = execution
        return execution_id

    def complete_tool_execution(self, tool_execution_id: str, output: Any) -> ArtifactRef:
        with self._state_lock:
            execution = self._tool_executions[tool_execution_id]
        artifact = self.store_artifact("tool-result", output)
        self.emit(
            RunEventDraft(
                self.run_id,
                "tool.execution_completed",
                {
                    **self._tool_payload(
                        execution.turn_ref,
                        execution.context,
                        execution.attempt_id,
                        execution.tool_call_id,
                        execution.tool_name,
                        tool_execution_id,
                    ),
                    "duration_ms": self._duration_ms(execution.started_at),
                    "artifact_id": artifact.artifact_id,
                },
                actor_id=execution.turn_ref.actor_id,
                node_id=execution.turn_ref.node_id,
                status="completed",
            )
        )
        with self._state_lock:
            if self._tool_executions.get(tool_execution_id) is execution:
                self._tool_executions.pop(tool_execution_id)
        return artifact

    def fail_tool_execution(
        self,
        tool_execution_id: str,
        error: BaseException,
    ) -> ArtifactRef:
        with self._state_lock:
            execution = self._tool_executions[tool_execution_id]
        artifact = self.store_artifact(
            "tool-result",
            {"error_type": type(error).__name__, "message": str(error)},
        )
        self.emit(
            RunEventDraft(
                self.run_id,
                "tool.execution_failed",
                {
                    **self._tool_payload(
                        execution.turn_ref,
                        execution.context,
                        execution.attempt_id,
                        execution.tool_call_id,
                        execution.tool_name,
                        tool_execution_id,
                    ),
                    "duration_ms": self._duration_ms(execution.started_at),
                    "error_artifact_id": artifact.artifact_id,
                },
                actor_id=execution.turn_ref.actor_id,
                node_id=execution.turn_ref.node_id,
                status="failed",
            )
        )
        with self._state_lock:
            if self._tool_executions.get(tool_execution_id) is execution:
                self._tool_executions.pop(tool_execution_id)
        return artifact

    def commit_tool(self, tool_call_id: str, checkpoint_event_id: str) -> None:
        with self._state_lock:
            logical = self._logical_tools[tool_call_id]
        commit_context = logical.execution_context or logical.request_context
        self.emit(
            RunEventDraft(
                self.run_id,
                "tool.committed",
                {
                    "turn_id": logical.turn_ref.turn_id,
                    "graph_task_id": commit_context.graph_task_id,
                    "attempt_id": logical.attempt_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": logical.tool_name,
                    "checkpoint_event_id": checkpoint_event_id,
                },
                actor_id=logical.turn_ref.actor_id,
                node_id=logical.turn_ref.node_id,
                status="committed",
            )
        )
        with self._state_lock:
            if self._logical_tools.get(tool_call_id) is logical:
                self._logical_tools.pop(tool_call_id)

    def cancel_tool(self, tool_call_id: str, reason: str) -> None:
        with self._state_lock:
            logical = self._logical_tools[tool_call_id]
        self.emit(
            RunEventDraft(
                self.run_id,
                "tool.cancelled",
                {
                    "turn_id": logical.turn_ref.turn_id,
                    "graph_task_id": logical.request_context.graph_task_id,
                    "attempt_id": logical.attempt_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": logical.tool_name,
                    "reason": reason,
                },
                actor_id=logical.turn_ref.actor_id,
                node_id=logical.turn_ref.node_id,
                status="cancelled",
            )
        )
        with self._state_lock:
            if self._logical_tools.get(tool_call_id) is logical:
                self._logical_tools.pop(tool_call_id)

    @contextmanager
    def direct_call_scope(
        self,
        invocation_path: str,
        *,
        tool_call_id: str | None = None,
    ) -> Iterator[ObservationContext]:
        current = current_observation_context(required=True)
        assert current is not None
        context = replace(
            current,
            invocation_path=f"direct:{invocation_path}",
            tool_call_id=tool_call_id if tool_call_id is not None else current.tool_call_id,
        )
        with observation_scope(context):
            yield context

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: Any,
        parent_run_id: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._start_model(
            serialized,
            messages,
            run_id,
            "chat",
            {**kwargs, "metadata": metadata or {}},
        )

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: Any,
        parent_run_id: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._start_model(
            serialized,
            prompts,
            run_id,
            "llm",
            {**kwargs, "metadata": metadata or {}},
        )

    def on_llm_end(self, response: Any, *, run_id: Any, **kwargs: Any) -> None:
        call_id = str(run_id)
        with self._state_lock:
            attempt = self._model_attempts.get(call_id)
        if attempt is None:
            self._unattributed("model.completed", call_id)
            return
        artifact = self.store_artifact("data", self._safe_callback_value(response))
        self.emit(
            RunEventDraft(
                self.run_id,
                "model.completed",
                {
                    **self._model_payload(attempt),
                    "duration_ms": self._duration_ms(attempt.started_at),
                    "usage": self._usage(response),
                    "output_artifact_id": artifact.artifact_id,
                },
                actor_id=attempt.context.actor_id,
                node_id=attempt.context.node_id,
                status="completed",
            )
        )
        with self._state_lock:
            if self._model_attempts.get(call_id) is attempt:
                self._model_attempts.pop(call_id)

    def on_llm_error(self, error: BaseException, *, run_id: Any, **kwargs: Any) -> None:
        call_id = str(run_id)
        with self._state_lock:
            attempt = self._model_attempts.get(call_id)
        if attempt is None:
            self._unattributed("model.failed", call_id)
            return
        artifact = self.store_artifact(
            "data",
            {"error_type": type(error).__name__, "message": str(error)},
        )
        self.emit(
            RunEventDraft(
                self.run_id,
                "model.failed",
                {
                    **self._model_payload(attempt),
                    "duration_ms": self._duration_ms(attempt.started_at),
                    "usage": {},
                    "error_artifact_id": artifact.artifact_id,
                },
                actor_id=attempt.context.actor_id,
                node_id=attempt.context.node_id,
                status="failed",
            )
        )
        with self._state_lock:
            if self._model_attempts.get(call_id) is attempt:
                self._model_attempts.pop(call_id)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: Any,
        parent_run_id: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        execution_id = str(run_id)
        context = self._require_context("tool.execution_started", execution_id)
        if context is None:
            return
        tool_call_id = kwargs.get("tool_call_id")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            if self.development_assertions:
                raise AssertionError("tool callback is missing model-provided tool_call_id")
            self._unattributed("tool.execution_started.missing_tool_call_id", execution_id)
            return
        with self._state_lock:
            logical = self._logical_tools.get(tool_call_id)
        if logical is None:
            if self.development_assertions:
                raise AssertionError(f"tool callback has no persisted request: {tool_call_id}")
            self._unattributed("tool.execution_started.unregistered_request", execution_id)
            return
        self._assert_context_matches_turn(context, logical.turn_ref)
        serialized_name = serialized.get("name")
        if serialized_name and str(serialized_name) != logical.tool_name:
            raise AssertionError("tool callback name does not match persisted logical request")
        self.start_tool_execution(
            tool_call_id,
            tool_execution_id=execution_id,
            context=context,
        )

    def on_tool_end(self, output: Any, *, run_id: Any, **kwargs: Any) -> None:
        execution_id = str(run_id)
        with self._state_lock:
            execution = self._tool_executions.get(execution_id)
        if execution is None:
            self._unattributed("tool.execution_completed", execution_id)
            return
        output_tool_call_id = getattr(output, "tool_call_id", None)
        if output_tool_call_id and output_tool_call_id != execution.tool_call_id:
            raise AssertionError("ToolMessage tool_call_id does not match callback execution")
        self.complete_tool_execution(execution_id, output)

    def on_tool_error(self, error: BaseException, *, run_id: Any, **kwargs: Any) -> None:
        execution_id = str(run_id)
        with self._state_lock:
            execution = self._tool_executions.get(execution_id)
        if execution is None:
            self._unattributed("tool.execution_failed", execution_id)
            return
        self.fail_tool_execution(execution_id, error)

    def _start_model(
        self,
        serialized: dict[str, Any],
        model_input: Any,
        callback_run_id: Any,
        capture_kind: str,
        callback_kwargs: dict[str, Any],
    ) -> None:
        model_call_id = str(callback_run_id)
        context = self._require_context(f"model.{capture_kind}.started", model_call_id)
        if context is None:
            return
        with self._state_lock:
            if model_call_id in self._model_attempts:
                raise ValueError(f"duplicate model callback run_id: {model_call_id}")
        metadata = callback_kwargs.get("metadata") or {}
        invocation = callback_kwargs.get("invocation_params") or {}
        provider = str(metadata.get("ls_provider") or invocation.get("provider") or "unknown")
        model = str(
            metadata.get("ls_model_name")
            or invocation.get("model")
            or invocation.get("model_name")
            or (serialized.get("id") or ["unknown"])[-1]
        )
        invocation_path = str(metadata.get("invocation_path") or context.invocation_path)
        attempt_id = f"attempt_{uuid.uuid4().hex}"
        attempt_context = replace(context, attempt_id=attempt_id)
        redacted_input = redact_recursive(model_input)
        artifact = self.store_artifact("prompt", redacted_input.value)
        self.emit(
            RunEventDraft(
                self.run_id,
                "input.prompt_snapshot",
                {
                    "turn_id": context.turn_id,
                    "graph_task_id": context.graph_task_id,
                    "capture_kind": capture_kind,
                    "artifact_id": artifact.artifact_id,
                    "content_sha256": artifact.content_sha256,
                    "redaction_manifest": [record.path for record in redacted_input.manifest],
                    "attempt_id": attempt_id,
                    "model_call_id": model_call_id,
                },
                actor_id=context.actor_id,
                node_id=context.node_id,
            )
        )
        attempt = _ModelAttempt(
            context=attempt_context,
            attempt_id=attempt_id,
            model_call_id=model_call_id,
            provider=provider,
            model=model,
            invocation_path=invocation_path,
            started_at=self._clock(),
        )
        self.emit(
            RunEventDraft(
                self.run_id,
                "model.started",
                self._model_payload(attempt),
                actor_id=context.actor_id,
                node_id=context.node_id,
                status="started",
            )
        )
        with self._state_lock:
            self._model_attempts[model_call_id] = attempt

    def _require_context(
        self,
        callback_kind: str,
        callback_run_id: str,
    ) -> ObservationContext | None:
        context = current_observation_context()
        if context is not None and context.run_id == self.run_id:
            return context
        if self.development_assertions:
            raise AssertionError(f"unattributed callback: {callback_kind}")
        self._unattributed(callback_kind, callback_run_id)
        return None

    def _unattributed(self, callback_kind: str, callback_run_id: str) -> None:
        if self.development_assertions:
            raise AssertionError(f"unattributed callback: {callback_kind}")
        self.emit(
            RunEventDraft(
                self.run_id,
                "diagnostic.unattributed",
                {
                    "callback_kind": callback_kind,
                    "callback_run_id": callback_run_id,
                },
                status="diagnostic",
            )
        )

    def _terminalize_turn(
        self,
        turn_id: str,
        status: str,
        duration_ms: int,
        reason: str,
    ) -> None:
        with self._state_lock:
            ref = self._turns[turn_id]
            context = self._turn_contexts[turn_id]
        role = ROLES_BY_ACTOR_ID[ref.actor_id]
        self.emit(
            RunEventDraft(
                self.run_id,
                f"turn.{status}",
                {
                    **self._turn_payload(ref, context, status),
                    "reason": reason,
                    "duration_ms": duration_ms,
                },
                team_id=role.team_id,
                actor_id=ref.actor_id,
                node_id=ref.node_id,
                status=status,
            )
        )
        role_status = "completed" if status == "completed" else status
        self.emit(
            RunEventDraft(
                self.run_id,
                "role.status_changed",
                {
                    "role_instance_id": ref.role_instance_id,
                    "previous_status": self._role_statuses.get(ref.actor_id, "running"),
                    "new_status": role_status,
                    "reason": reason,
                    "turn_id": turn_id,
                },
                team_id=role.team_id,
                actor_id=ref.actor_id,
                node_id=ref.node_id,
                status=role_status,
            )
        )
        with self._state_lock:
            self._open_turn_ids.discard(turn_id)
            self._role_statuses[ref.actor_id] = role_status

    @staticmethod
    def _context(
        ref: RoleTurnRef,
        graph_task_id: str,
        graph_step: int,
        *,
        invocation_path: str = "role",
        attempt_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> ObservationContext:
        return ObservationContext(
            run_id=ref.run_id,
            actor_id=ref.actor_id,
            node_id=ref.node_id,
            role_instance_id=ref.role_instance_id,
            turn_id=ref.turn_id,
            graph_task_id=graph_task_id,
            graph_step=graph_step,
            invocation_path=invocation_path,
            attempt_id=attempt_id,
            tool_call_id=tool_call_id,
        )

    @staticmethod
    def _assert_context_matches_turn(context: ObservationContext, ref: RoleTurnRef) -> None:
        if (
            context.run_id != ref.run_id
            or context.turn_id != ref.turn_id
            or context.actor_id != ref.actor_id
            or context.node_id != ref.node_id
        ):
            raise AssertionError("observation context does not match logical turn")

    @staticmethod
    def _turn_payload(
        ref: RoleTurnRef,
        context: ObservationContext,
        status: str,
    ) -> dict[str, Any]:
        return {
            "role_instance_id": ref.role_instance_id,
            "turn_id": ref.turn_id,
            "graph_task_id": context.graph_task_id,
            "graph_step": context.graph_step,
            "turn_index": ref.turn_index,
            "turn_status": status,
        }

    @staticmethod
    def _tool_payload(
        ref: RoleTurnRef,
        context: ObservationContext,
        attempt_id: str,
        tool_call_id: str,
        tool_name: str,
        tool_execution_id: str,
    ) -> dict[str, Any]:
        return {
            "turn_id": ref.turn_id,
            "graph_task_id": context.graph_task_id,
            "attempt_id": attempt_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "tool_execution_id": tool_execution_id,
        }

    @staticmethod
    def _model_payload(attempt: _ModelAttempt) -> dict[str, Any]:
        return {
            "turn_id": attempt.context.turn_id,
            "graph_task_id": attempt.context.graph_task_id,
            "attempt_id": attempt.attempt_id,
            "model_call_id": attempt.model_call_id,
            "provider": attempt.provider,
            "model": attempt.model,
            "invocation_path": attempt.invocation_path,
        }

    def _duration_ms(self, started_at: float) -> int:
        return max(0, round((self._clock() - started_at) * 1000))

    @staticmethod
    def _usage(response: Any) -> dict[str, Any]:
        llm_output = getattr(response, "llm_output", None) or {}
        if isinstance(llm_output, dict):
            usage = llm_output.get("token_usage") or llm_output.get("usage")
            if isinstance(usage, dict):
                return dict(usage)
        generations = getattr(response, "generations", None) or []
        for generation_group in generations:
            group = generation_group if isinstance(generation_group, list) else [generation_group]
            for generation in group:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None)
                if isinstance(usage, dict):
                    return dict(usage)
        return {}

    @staticmethod
    def _safe_callback_value(value: Any) -> Any:
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return model_dump(mode="python")
        as_dict = getattr(value, "dict", None)
        if callable(as_dict):
            return as_dict()
        if isinstance(value, (dict, list, tuple, str, int, float, bool, type(None))):
            return value
        return {"type": type(value).__name__, "repr": repr(value)}

    @staticmethod
    def _task_id_from_output_ready(payload: dict[str, Any]) -> str | None:
        commit = payload.get("observation_commit")
        if isinstance(commit, dict):
            task_id = commit.get("graph_task_id")
            return str(task_id) if task_id else None
        return None

    def _rebuild_from_events(self) -> None:
        events = self.store.read_events(self.run_id)
        task_steps: dict[str, int] = {}
        for event in events:
            payload = event.payload
            if event.type == "graph.task_started":
                task_id = str(payload["graph_task_id"])
                task_steps[task_id] = int(payload["graph_step"])
                self._application_status_by_task.setdefault(task_id, "candidate")
            elif event.type == "graph.task_output_ready":
                task_id = self._task_id_from_output_ready(payload)
                if task_id:
                    task_steps[task_id] = int(payload["graph_step"])
                    self._application_status_by_task[task_id] = "pending_apply"
            elif event.type in {"graph.step_applied", "graph.checkpoint_committed"}:
                for task_id in payload["applied_task_ids"]:
                    self._application_status_by_task[str(task_id)] = "committed"
            elif event.type == "graph.task_abandoned":
                task_id = str(payload["graph_task_id"])
                task_steps[task_id] = int(payload["graph_step"])
                self._application_status_by_task[task_id] = "abandoned"

        for event in events:
            payload = event.payload
            if event.type == "role.status_changed" and event.actor_id:
                self._role_statuses[event.actor_id] = payload["new_status"]
            if event.type.startswith("turn.") and event.actor_id:
                turn_id = payload["turn_id"]
                ref = self._turns.get(turn_id)
                if ref is None:
                    ref = RoleTurnRef(
                        run_id=self.run_id,
                        actor_id=event.actor_id,
                        node_id=event.node_id or ROLES_BY_ACTOR_ID[event.actor_id].node_id,
                        role_instance_id=payload["role_instance_id"],
                        turn_id=turn_id,
                        turn_index=int(payload["turn_index"]),
                    )
                    self._turns[turn_id] = ref
                self._turn_contexts[turn_id] = self._context(
                    ref,
                    str(payload["graph_task_id"]),
                    int(payload["graph_step"]),
                )
                if event.type in {"turn.started", "turn.resumed"}:
                    self._open_turn_ids.add(turn_id)
                elif event.type in {
                    "turn.completed",
                    "turn.failed",
                    "turn.cancelled",
                    "turn.interrupted",
                }:
                    self._open_turn_ids.discard(turn_id)

        for event in events:
            payload = event.payload
            if event.type == "tool.requested":
                task_id = str(payload["graph_task_id"])
                if self._application_status_by_task.get(task_id) not in {
                    "committed",
                    "pending_apply",
                }:
                    continue
                ref = self._turns.get(payload["turn_id"])
                if ref is None:
                    continue
                latest = self._turn_contexts[ref.turn_id]
                request_context = self._context(
                    ref,
                    task_id,
                    task_steps.get(task_id, latest.graph_step),
                    attempt_id=str(payload["attempt_id"]),
                    tool_call_id=str(payload["tool_call_id"]),
                )
                self._logical_tools[str(payload["tool_call_id"])] = _LogicalTool(
                    turn_ref=ref,
                    request_context=request_context,
                    attempt_id=str(payload["attempt_id"]),
                    tool_name=str(payload["tool_name"]),
                )
            elif event.type in {"tool.committed", "tool.cancelled"}:
                self._logical_tools.pop(str(payload["tool_call_id"]), None)
