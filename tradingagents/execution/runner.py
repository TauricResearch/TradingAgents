"""One authoritative execution path for CLI, web, and programmatic callers."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from tradingagents.execution.config_identity import prepare_effective_config
from tradingagents.execution.models import (
    ANALYST_WIRE_KEYS,
    AnalysisRequest,
    AnalysisResult,
    CancellationToken,
)

logger = logging.getLogger(__name__)


def get_checkpointer(*args, **kwargs):
    from tradingagents.graph.checkpointer import get_checkpointer as implementation

    return implementation(*args, **kwargs)


def checkpoint_step(*args, **kwargs):
    from tradingagents.graph.checkpointer import checkpoint_step as implementation

    return implementation(*args, **kwargs)


def checkpoint_access(*args, **kwargs):
    from tradingagents.graph.checkpointer import checkpoint_access as implementation

    return implementation(*args, **kwargs)


def clear_checkpoint(*args, **kwargs):
    from tradingagents.graph.checkpointer import clear_checkpoint as implementation

    return implementation(*args, **kwargs)


def thread_id(*args, **kwargs):
    from tradingagents.graph.checkpointer import thread_id as implementation

    return implementation(*args, **kwargs)


@dataclass(frozen=True)
class PreparedInitialContext:
    """Resolved values that determine the graph's exact initial state."""

    values: Mapping[str, Any]


@dataclass(frozen=True)
class PreparedAnalysis:
    """The exact initial state and its already-authorized source context."""

    initial_state: Mapping[str, Any] | None
    initial_context: PreparedInitialContext


_CHECKPOINT_AUTHORIZATION_ISSUER = object()


@dataclass(frozen=True, init=False)
class CheckpointAuthorization:
    """Proof returned by the durable fingerprint gate for one checkpoint run."""

    run_id: str
    fingerprint_sha256: str
    mode: Literal["fresh", "resume"]
    _issuer: object = field(repr=False, compare=False)

    @classmethod
    def _issue(
        cls,
        *,
        run_id: str,
        fingerprint_sha256: str,
        mode: Literal["fresh", "resume"],
    ) -> CheckpointAuthorization:
        authorization = object.__new__(cls)
        object.__setattr__(authorization, "run_id", run_id)
        object.__setattr__(
            authorization,
            "fingerprint_sha256",
            fingerprint_sha256,
        )
        object.__setattr__(authorization, "mode", mode)
        object.__setattr__(
            authorization,
            "_issuer",
            _CHECKPOINT_AUTHORIZATION_ISSUER,
        )
        return authorization


CheckpointGuard = Callable[[PreparedInitialContext, Any], CheckpointAuthorization]


class AnalysisRunner:
    """Execute a configured TradingAgents graph without consumer-specific output."""

    def __init__(self, owner: Any):
        self.owner = owner
        self._checkpoint_context_owned = False
        self._checkpoint_entered = False
        self._checkpoint_graph_recompiled = False
        self._checkpoint_saver: Any | None = None
        self._checkpoint_authorization: CheckpointAuthorization | None = None
        self._active_thread_id: str | None = None
        self._resume_state: Mapping[str, Any] | None = None

    def run(
        self,
        request: AnalysisRequest,
        *,
        cancellation_token: CancellationToken | None = None,
        observation_context: Any | None = None,
        callbacks: list[Any] | None = None,
        checkpoint_run_id: str | None = None,
        checkpoint_guard: CheckpointGuard | None = None,
    ) -> AnalysisResult:
        checkpoint_run_id = self._resolve_checkpoint_run_id(
            observation_context,
            checkpoint_run_id,
        )
        self._validate_request_shape(request, checkpoint_run_id=checkpoint_run_id)
        if (
            checkpoint_run_id is not None
            and self.owner.config.get("checkpoint_enabled")
        ):
            if checkpoint_guard is None:
                raise ValueError("checkpointed web runs require a checkpoint guard")
            self._validate_checkpoint_guard_type(checkpoint_guard)
        token = cancellation_token or CancellationToken()
        cooperative_cancellation = cancellation_token is not None
        token.raise_if_cancelled()

        owner = self.owner
        owner.ticker = request.ticker
        owner._resolve_pending_entries(request.ticker)
        token.raise_if_cancelled()

        try:
            prepared: PreparedAnalysis | None = None
            if checkpoint_run_id is not None and owner.config.get("checkpoint_enabled"):
                initial_context = self._resolve_initial_context(request)
                token.raise_if_cancelled()
                access = checkpoint_access(
                    owner.config["data_cache_dir"],
                    request.ticker,
                    request.analysis_date,
                    owner._run_signature(request.asset_type),
                    run_id=checkpoint_run_id,
                )
                assert checkpoint_guard is not None
                authorization = checkpoint_guard(initial_context, access)
                self._validate_checkpoint_authorization(
                    authorization,
                    access,
                    checkpoint_run_id,
                )
                self._checkpoint_authorization = authorization
                token.raise_if_cancelled()
            self._open_legacy_checkpoint(request, run_id=checkpoint_run_id)
            if prepared is None:
                if (
                    self._checkpoint_authorization is not None
                    and self._checkpoint_authorization.mode == "resume"
                ):
                    prepared = PreparedAnalysis(None, initial_context)
                    self._reconcile_resume_frontier(
                        observation_context,
                        checkpoint_run_id,
                    )
                else:
                    if checkpoint_run_id is None or not owner.config.get(
                        "checkpoint_enabled"
                    ):
                        initial_context = self._resolve_initial_context(request)
                    prepared = self._create_initial_state(
                        request,
                        initial_context,
                        observation_context=observation_context,
                    )
            result = self._execute(
                request,
                prepared,
                cancellation_token=token,
                cooperative_cancellation=cooperative_cancellation,
                observation_context=observation_context,
                callbacks=callbacks,
                checkpoint_run_id=checkpoint_run_id,
            )
        except BaseException:
            self._close_checkpoint(preserve_active_error=True)
            raise
        self._close_checkpoint()
        return result

    def _execute(
        self,
        request: AnalysisRequest,
        prepared: PreparedAnalysis,
        *,
        cancellation_token: CancellationToken,
        cooperative_cancellation: bool,
        observation_context: Any | None,
        callbacks: list[Any] | None,
        checkpoint_run_id: str | None,
    ) -> AnalysisResult:
        owner = self.owner
        initial_state = prepared.initial_state

        graph_args = owner.propagator.get_graph_args(
            **({"callbacks": callbacks} if callbacks else {})
        )
        if owner.config.get("checkpoint_enabled"):
            run_shape = owner._run_signature(request.asset_type)
            configurable = graph_args.setdefault("config", {}).setdefault(
                "configurable",
                {},
            )
            configurable["thread_id"] = self._active_thread_id or thread_id(
                request.ticker,
                request.analysis_date,
                run_shape,
                **_run_id_kwargs(checkpoint_run_id),
            )
            self._active_thread_id = configurable["thread_id"]

        cancellation_token.raise_if_cancelled()
        should_stream = (
            owner.debug
            or observation_context is not None
            or cooperative_cancellation
            or callbacks is not None
        )
        if should_stream:
            final_state = self._stream_graph(
                initial_state,
                graph_args,
                cancellation_token,
                observation_context,
                checkpoint_run_id=checkpoint_run_id,
            )
        else:
            final_state = owner.graph.invoke(initial_state, **graph_args)
        cancellation_token.raise_if_cancelled(final_state)

        owner.curr_state = final_state
        owner._log_state(request.analysis_date, final_state)
        owner.memory_log.store_decision(
            ticker=request.ticker,
            trade_date=request.analysis_date,
            final_trade_decision=final_state["final_trade_decision"],
        )

        if owner.config.get("checkpoint_enabled"):
            clear_checkpoint(
                owner.config["data_cache_dir"],
                request.ticker,
                request.analysis_date,
                owner._run_signature(request.asset_type),
                **_run_id_kwargs(checkpoint_run_id),
            )

        signal = self._process_signal(final_state["final_trade_decision"])
        return AnalysisResult(final_state=final_state, final_signal=signal)

    def _resolve_initial_context(
        self,
        request: AnalysisRequest,
    ) -> PreparedInitialContext:
        owner = self.owner
        past_context = owner.memory_log.get_past_context(request.ticker)
        instrument_context = owner.resolve_instrument_context(
            request.ticker,
            request.asset_type,
        )
        return PreparedInitialContext(
            {
                "past_context": past_context,
                "company_of_interest": request.ticker,
                "asset_type": request.asset_type,
                "instrument_context": instrument_context,
            }
        )

    def _create_initial_state(
        self,
        request: AnalysisRequest,
        initial_context: PreparedInitialContext,
        *,
        observation_context: Any | None,
    ) -> PreparedAnalysis:
        owner = self.owner
        initial_kwargs: dict[str, Any] = {
            "asset_type": request.asset_type,
            "past_context": initial_context.values["past_context"],
            "instrument_context": initial_context.values["instrument_context"],
        }
        if observation_context is not None:
            initial_kwargs["observation_context"] = observation_context
        initial_state = owner.propagator.create_initial_state(
            request.ticker,
            request.analysis_date,
            **initial_kwargs,
        )
        return PreparedAnalysis(
            initial_state=initial_state,
            initial_context=initial_context,
        )

    def _stream_graph(
        self,
        initial_state: Mapping[str, Any] | None,
        graph_args: dict[str, Any],
        cancellation_token: CancellationToken,
        observation_context: Any | None,
        *,
        checkpoint_run_id: str | None,
    ) -> Mapping[str, Any]:
        owner = self.owner
        invocation_args = dict(graph_args)
        if observation_context is not None:
            invocation_args["context"] = observation_context
        checkpointed_web = (
            checkpoint_run_id is not None
            and getattr(getattr(observation_context, "observer", None), "store", None)
            is not None
            and owner.config.get("checkpoint_enabled")
        )
        observed_without_checkpoint = (
            getattr(observation_context, "observer", None) is not None
            and not owner.config.get("checkpoint_enabled")
        )
        if checkpointed_web:
            invocation_args["stream_mode"] = ["tasks", "updates", "checkpoints"]
            invocation_args["durability"] = "sync"
            invocation_args["version"] = "v1"
        elif observed_without_checkpoint:
            invocation_args["stream_mode"] = ["tasks", "updates", "values"]
            invocation_args.pop("durability", None)
            invocation_args["version"] = "v1"
        stream_mode = invocation_args.get("stream_mode", "values")
        final_state: Mapping[str, Any] | None = None
        merged: dict[str, Any] = {}
        last_printed = None

        for chunk in owner.graph.stream(initial_state, **invocation_args):
            mode: str | None = None
            payload: Any = chunk
            if isinstance(stream_mode, list):
                if (
                    not isinstance(chunk, tuple)
                    or len(chunk) != 2
                    or not isinstance(chunk[0], str)
                ):
                    raise TypeError("multi-mode graph stream must yield (mode, payload)")
                mode, payload = chunk
            if not isinstance(payload, Mapping):
                raise TypeError("graph state stream must yield mappings")
            barrier = False
            if checkpointed_web:
                if mode == "checkpoints":
                    final_state = self._accept_checkpoint_payload(
                        payload,
                        observation_context,
                    )
                    barrier = True
            elif observed_without_checkpoint:
                if mode == "values":
                    final_state = payload
                    self._accept_in_process_barrier(payload, observation_context)
                    barrier = True
            elif stream_mode == "values":
                final_state = payload
                barrier = True
            else:
                merged.update(payload)
                final_state = merged
                barrier = True

            debug_state = final_state if barrier else None
            if owner.debug and debug_state and debug_state.get("messages"):
                message = debug_state["messages"][-1]
                signature = (type(message).__name__, getattr(message, "content", None))
                if signature != last_printed:
                    message.pretty_print()
                    last_printed = signature
            if barrier:
                cancellation_token.raise_if_cancelled(final_state)

        if final_state is None:
            if initial_state is None and self._resume_state is not None:
                return self._resume_state
            raise RuntimeError("graph completed without yielding final state")
        return final_state

    def _accept_checkpoint_payload(
        self,
        payload: Mapping[str, Any],
        observation_context: Any,
    ) -> Mapping[str, Any]:
        from tradingagents.web.reconciliation import (
            DurableCheckpoint,
            apply_reconciliation_plan,
            reconcile_checkpoint_frontier,
        )

        observer = getattr(observation_context, "observer", None)
        if observer is None or self._checkpoint_saver is None:
            raise RuntimeError("checkpoint observation requires observer and active saver")
        streamed = DurableCheckpoint.from_stream_payload(payload)
        durable_tuple = self._checkpoint_saver.get_tuple(payload["config"])
        if durable_tuple is None:
            raise RuntimeError("synchronous checkpoint was not durable")
        durable_id = _checkpoint_id(durable_tuple)
        if durable_id != streamed.checkpoint_id:
            raise RuntimeError("streamed and durable checkpoint IDs do not match")

        if streamed.graph_step == -1:
            return streamed.channel_values

        parent_tuple = (
            self._checkpoint_saver.get_tuple(durable_tuple.parent_config)
            if durable_tuple.parent_config is not None
            else None
        )
        latest_next = tuple(self.owner.graph.get_state(durable_tuple.config).next)
        parent_next = (
            tuple(self.owner.graph.get_state(parent_tuple.config).next)
            if parent_tuple is not None
            else None
        )
        durable = DurableCheckpoint.from_checkpoint_tuple(
            durable_tuple,
            next_nodes=latest_next,
        )
        if (
            durable.graph_step != streamed.graph_step
            or durable.state_sha256 != streamed.state_sha256
            or durable.next_nodes != streamed.next_nodes
        ):
            raise RuntimeError("streamed checkpoint payload does not match durable state")
        store = observer.store
        events = store.read_events(observer.run_id)
        plan = reconcile_checkpoint_frontier(
            events,
            durable_tuple,
            parent_tuple,
            latest_next_nodes=latest_next,
            parent_next_nodes=parent_next,
            read_artifact=lambda artifact_id: store.read_artifact(
                observer.run_id,
                artifact_id,
            ),
        )
        apply_reconciliation_plan(
            store,
            observer.run_id,
            plan,
            current_checkpoint_id=lambda: _latest_checkpoint_id(
                self._checkpoint_saver,
                self._active_thread_id,
            ),
            observer=observer,
        )
        self.promote_reconciled_tasks(observer, plan)
        return streamed.channel_values

    def _accept_in_process_barrier(
        self,
        values: Mapping[str, Any],
        observation_context: Any,
    ) -> None:
        from tradingagents.observability.canonical import BusinessStateProjectionV1
        from tradingagents.web.reconciliation import candidate_map

        observer = getattr(observation_context, "observer", None)
        if observer is None:
            return
        events = observer.store.read_events(observer.run_id)
        candidates = candidate_map(events)
        applied = tuple(
            sorted(
                task_id
                for task_id in candidates
                if observer.application_status(task_id) not in {"committed", "abandoned"}
            )
        )
        if not applied:
            return
        graph_step = max(candidates[task_id].graph_step for task_id in applied)
        marker = observer.emit(
            _step_applied_draft(
                observer.run_id,
                graph_step,
                applied,
                BusinessStateProjectionV1.from_channel_values(values).sha256,
            )
        )
        observer.refresh_from_events()
        self._promote_commits(
            observer,
            tuple(candidates[task_id].commit for task_id in applied),
            candidates,
            marker,
        )

    def _reconcile_resume_frontier(
        self,
        observation_context: Any | None,
        checkpoint_run_id: str | None,
    ) -> None:
        if observation_context is None or checkpoint_run_id is None:
            return
        observer = getattr(observation_context, "observer", None)
        if observer is None or self._checkpoint_saver is None:
            raise RuntimeError("resume reconciliation requires observer and active saver")
        from tradingagents.web.reconciliation import (
            apply_reconciliation_plan,
            reconcile_checkpoint_frontier,
        )

        configurable = {
            "configurable": {
                "thread_id": self._active_thread_id,
            }
        }
        latest = self._checkpoint_saver.get_tuple(configurable)
        if latest is None:
            raise RuntimeError("authorized resume checkpoint disappeared")
        parent = (
            self._checkpoint_saver.get_tuple(latest.parent_config)
            if latest.parent_config is not None
            else None
        )
        latest_next = tuple(self.owner.graph.get_state(latest.config).next)
        self._resume_state = dict(latest.checkpoint["channel_values"])
        if latest.metadata.get("step") == -1:
            return
        parent_next = (
            tuple(self.owner.graph.get_state(parent.config).next)
            if parent is not None
            else None
        )
        store = observer.store
        plan = reconcile_checkpoint_frontier(
            store.read_events(observer.run_id),
            latest,
            parent,
            latest_next_nodes=latest_next,
            parent_next_nodes=parent_next,
            read_artifact=lambda artifact_id: store.read_artifact(
                observer.run_id,
                artifact_id,
            ),
        )
        apply_reconciliation_plan(
            store,
            observer.run_id,
            plan,
            current_checkpoint_id=lambda: _latest_checkpoint_id(
                self._checkpoint_saver,
                self._active_thread_id,
            ),
            observer=observer,
        )
        self.promote_reconciled_tasks(observer, plan)

    @staticmethod
    def promote_reconciled_tasks(observer: Any, plan: Any) -> None:
        """Apply already-durable checkpoint candidates during restart recovery."""
        transition = plan.latest_transition
        events = observer.store.read_events(observer.run_id)
        marker = next(
            event
            for event in reversed(events)
            if event.type == "graph.checkpoint_committed"
            and event.payload.get("checkpoint_id")
            == transition.checkpoint.checkpoint_id
        )
        AnalysisRunner._promote_commits(
            observer,
            transition.applied_commits,
            plan.candidates,
            marker,
        )

    @staticmethod
    def _promote_commits(
        observer: Any,
        commits: tuple[Any, ...],
        candidates: Mapping[str, Any],
        marker: Any,
    ) -> None:
        events = observer.store.read_events(observer.run_id)
        committed_tools = {
            str(event.payload["tool_call_id"])
            for event in events
            if event.type == "tool.committed"
        }
        terminal_turns = {
            str(event.payload["turn_id"])
            for event in events
            if event.type
            in {"turn.completed", "turn.failed", "turn.cancelled", "turn.interrupted"}
        }
        completed_turns = {
            str(event.payload["turn_id"])
            for event in events
            if event.type == "turn.completed"
        }
        promoted_state_tasks = {
            str(event.payload.get("graph_task_id"))
            for event in events
            if event.type == "state.updated" and event.payload.get("graph_task_id")
        }
        promoted_reports = {
            (
                str(event.payload.get("graph_task_id")),
                str(event.payload.get("report_kind")),
            )
            for event in events
            if event.type == "report.updated" and event.payload.get("graph_task_id")
        }
        observer.refresh_from_events()
        for commit in commits:
            candidate = candidates[commit.graph_task_id]
            delta = _read_candidate_delta(observer, candidate.artifact_id)
            if commit.turn_id and commit.graph_task_id not in promoted_state_tasks:
                observer.emit(
                    _state_updated_draft(
                        observer.run_id,
                        commit,
                        tuple(sorted(delta)),
                        marker.event_id,
                    )
                )
                promoted_state_tasks.add(commit.graph_task_id)
            _promote_report_revisions(
                observer,
                commit,
                delta,
                marker.event_id,
                promoted_reports,
            )
            if commit.task_kind == "tool":
                for tool_call_id in commit.tool_call_ids:
                    if tool_call_id not in committed_tools:
                        observer.commit_tool(tool_call_id, marker.event_id)
                        committed_tools.add(tool_call_id)
            if (
                commit.task_kind == "role"
                and not commit.tool_call_ids
                and commit.turn_id
                and commit.turn_id not in terminal_turns
            ):
                observer.complete_turn(commit.turn_id, duration_ms=0)
                terminal_turns.add(commit.turn_id)
                completed_turns.add(commit.turn_id)
            if commit.turn_id in completed_turns:
                _ensure_role_completion(
                    observer,
                    commit.turn_id,
                    marker.event_id,
                )

    def _open_legacy_checkpoint(
        self,
        request: AnalysisRequest,
        *,
        run_id: str | None,
    ) -> None:
        owner = self.owner
        if not owner.config.get("checkpoint_enabled"):
            return
        if owner._checkpointer_ctx is not None:
            raise RuntimeError("checkpoint context is already active")
        owner._checkpointer_ctx = get_checkpointer(
            owner.config["data_cache_dir"],
            request.ticker,
        )
        self._checkpoint_context_owned = True
        saver = owner._checkpointer_ctx.__enter__()
        self._checkpoint_entered = True
        self._checkpoint_saver = saver
        owner.graph = owner.workflow.compile(checkpointer=saver)
        self._checkpoint_graph_recompiled = True
        self._active_thread_id = thread_id(
            request.ticker,
            request.analysis_date,
            owner._run_signature(request.asset_type),
            **_run_id_kwargs(run_id),
        )
        step = checkpoint_step(
            owner.config["data_cache_dir"],
            request.ticker,
            request.analysis_date,
            owner._run_signature(request.asset_type),
            **_run_id_kwargs(run_id),
        )
        if step is None:
            logger.info(
                "Starting fresh for %s on %s",
                request.ticker,
                request.analysis_date,
            )
        else:
            logger.info(
                "Resuming from step %d for %s on %s",
                step,
                request.ticker,
                request.analysis_date,
            )

    def _close_checkpoint(self, *, preserve_active_error: bool = False) -> None:
        owner = self.owner
        if not self._checkpoint_context_owned:
            return
        cleanup_error: BaseException | None = None
        try:
            if self._checkpoint_entered:
                owner._checkpointer_ctx.__exit__(None, None, None)
        except BaseException as exc:
            cleanup_error = exc
        finally:
            owner._checkpointer_ctx = None
            self._checkpoint_saver = None
            self._active_thread_id = None
            self._checkpoint_authorization = None
            self._resume_state = None
            self._checkpoint_context_owned = False
            self._checkpoint_entered = False
            if self._checkpoint_graph_recompiled:
                try:
                    owner.graph = owner.workflow.compile()
                except BaseException as exc:
                    cleanup_error = cleanup_error or exc
            self._checkpoint_graph_recompiled = False
        if cleanup_error is not None:
            if preserve_active_error:
                logger.exception(
                    "checkpoint cleanup failed while preserving the active analysis error",
                    exc_info=cleanup_error,
                )
            else:
                raise cleanup_error

    def _process_signal(self, full_signal: str) -> str:
        owner = self.owner
        process = getattr(owner, "process_signal", None)
        if callable(process):
            return process(full_signal)
        return owner.signal_processor.process_signal(full_signal)

    def _resolve_checkpoint_run_id(
        self,
        observation_context: Any | None,
        checkpoint_run_id: str | None,
    ) -> str | None:
        observer = getattr(observation_context, "observer", None)
        observed_run_id = getattr(observer, "run_id", None)
        if observed_run_id is None:
            return checkpoint_run_id
        if not isinstance(observed_run_id, str) or not observed_run_id:
            raise ValueError("observation context run_id must be non-empty")
        if checkpoint_run_id is not None and checkpoint_run_id != observed_run_id:
            raise ValueError("observation and checkpoint run IDs do not match")
        return observed_run_id

    def _validate_checkpoint_authorization(
        self,
        authorization: CheckpointAuthorization,
        access: Any,
        run_id: str,
    ) -> None:
        if not isinstance(authorization, CheckpointAuthorization):
            raise RuntimeError("checkpoint guard did not return an authorization")
        if (
            getattr(authorization, "_issuer", None)
            is not _CHECKPOINT_AUTHORIZATION_ISSUER
        ):
            raise RuntimeError("checkpoint authorization was not issued by the durable gate")
        expected_mode = "resume" if getattr(access, "latest", None) is not None else "fresh"
        if authorization.run_id != run_id or authorization.mode != expected_mode:
            raise RuntimeError("checkpoint authorization does not match the checkpoint frontier")
        digest = authorization.fingerprint_sha256
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise RuntimeError("checkpoint authorization has an invalid fingerprint")

    def _validate_checkpoint_guard_type(self, checkpoint_guard: CheckpointGuard) -> None:
        from tradingagents.web.fingerprint import FingerprintCheckpointGuard

        if type(checkpoint_guard) is not FingerprintCheckpointGuard:
            raise ValueError(
                "checkpointed web runs require FingerprintCheckpointGuard"
            )

    def _validate_request_shape(
        self,
        request: AnalysisRequest,
        *,
        checkpoint_run_id: str | None,
    ) -> None:
        owner = self.owner
        if checkpoint_run_id is not None and not request.effective_config:
            raise ValueError("checkpointed web runs require complete effective_config")
        if request.effective_config:
            request_config = prepare_effective_config(request.effective_config)
            owner_config = prepare_effective_config(owner.config)
            if not request_config or request_config != owner_config:
                raise ValueError(
                    "analysis request config does not match the configured graph"
                )
        if checkpoint_run_id is not None:
            canonical_order = tuple(
                analyst
                for analyst in ANALYST_WIRE_KEYS
                if analyst in request.selected_analysts
            )
            if tuple(request.selected_analysts) != canonical_order:
                raise ValueError(
                    "checkpointed web analysts must use canonical registry order"
                )
        if tuple(request.selected_analysts) != tuple(owner.selected_analysts):
            raise ValueError("analysis request analysts do not match the compiled graph")
        if request.max_debate_rounds != int(owner.config["max_debate_rounds"]):
            raise ValueError("analysis request debate rounds do not match the compiled graph")
        if request.max_risk_discuss_rounds != int(
            owner.config["max_risk_discuss_rounds"]
        ):
            raise ValueError("analysis request risk rounds do not match the compiled graph")


def _run_id_kwargs(run_id: str | None) -> dict[str, str]:
    return {"run_id": run_id} if run_id is not None else {}


def _checkpoint_id(checkpoint_tuple: Any | None) -> str | None:
    if checkpoint_tuple is None:
        return None
    config = getattr(checkpoint_tuple, "config", None)
    checkpoint = getattr(checkpoint_tuple, "checkpoint", None)
    configurable = config.get("configurable") if isinstance(config, Mapping) else None
    value = (
        configurable.get("checkpoint_id")
        if isinstance(configurable, Mapping)
        else None
    )
    if value is None and isinstance(checkpoint, Mapping):
        value = checkpoint.get("id")
    return value if isinstance(value, str) and value else None


def _latest_checkpoint_id(saver: Any, thread_identity: str | None) -> str | None:
    if saver is None or not thread_identity:
        return None
    return _checkpoint_id(
        saver.get_tuple({"configurable": {"thread_id": thread_identity}})
    )


def _step_applied_draft(
    run_id: str,
    graph_step: int,
    applied_task_ids: tuple[str, ...],
    state_sha256: str,
):
    from tradingagents.observability.events import RunEventDraft

    return RunEventDraft(
        run_id,
        "graph.step_applied",
        {
            "graph_step": graph_step,
            "applied_task_ids": list(applied_task_ids),
            "state_sha256": state_sha256,
            "next_nodes": [],
        },
        status="committed",
    )


def _read_candidate_delta(observer: Any, artifact_id: str) -> dict[str, Any]:
    try:
        value = json.loads(observer.store.read_artifact(observer.run_id, artifact_id))
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError("committed candidate artifact is unreadable") from exc
    if not isinstance(value, dict):
        raise RuntimeError("committed candidate artifact must contain an object")
    return value


def _state_updated_draft(
    run_id: str,
    commit: Any,
    changed_keys: tuple[str, ...],
    checkpoint_event_id: str,
):
    from tradingagents.observability.events import RunEventDraft

    return RunEventDraft(
        run_id,
        "state.updated",
        {
            "turn_id": commit.turn_id,
            "graph_task_id": commit.graph_task_id,
            "changed_keys": list(changed_keys),
            "checkpoint_event_id": checkpoint_event_id,
        },
        node_id=commit.node_id,
        parent_event_id=checkpoint_event_id,
        status="committed",
    )


_REPORT_FIELDS = {
    "market_report": "market",
    "sentiment_report": "sentiment",
    "news_report": "news",
    "fundamentals_report": "fundamentals",
    "trader_investment_plan": "trader",
    "final_trade_decision": "portfolio",
}


def _promote_report_revisions(
    observer: Any,
    commit: Any,
    delta: Mapping[str, Any],
    checkpoint_event_id: str,
    promoted_reports: set[tuple[str, str]],
) -> None:
    if not commit.turn_id:
        return
    from tradingagents.observability.events import RunEventDraft
    from tradingagents.web.reports import ReportArtifactWriter

    writer = ReportArtifactWriter(observer.store)
    for state_field, report_kind in _REPORT_FIELDS.items():
        content = delta.get(state_field)
        identity = (commit.graph_task_id, report_kind)
        if not isinstance(content, str) or not content or identity in promoted_reports:
            continue
        revision = writer.write_revision_once(observer.run_id, report_kind, content)
        events = observer.store.read_events(observer.run_id)
        if not any(
            event.type == "artifact.written"
            and event.payload.get("artifact_id") == revision.artifact.artifact_id
            for event in events
        ):
            observer.emit(
                RunEventDraft(
                    observer.run_id,
                    "artifact.written",
                    {
                        "artifact_id": revision.artifact.artifact_id,
                        "kind": revision.artifact.kind,
                        "media_type": revision.artifact.media_type,
                        "content_sha256": revision.artifact.content_sha256,
                        "byte_size": revision.artifact.byte_size,
                        "locator": revision.artifact.locator,
                    },
                    parent_event_id=checkpoint_event_id,
                )
            )
        observer.emit(
            RunEventDraft(
                observer.run_id,
                "report.updated",
                {
                    "turn_id": commit.turn_id,
                    "graph_task_id": commit.graph_task_id,
                    "report_kind": report_kind,
                    "revision": revision.revision,
                    "artifact_id": revision.artifact.artifact_id,
                    "checkpoint_event_id": checkpoint_event_id,
                },
                node_id=commit.node_id,
                parent_event_id=checkpoint_event_id,
                status="committed",
            )
        )
        promoted_reports.add(identity)


def _ensure_role_completion(
    observer: Any,
    turn_id: str,
    checkpoint_event_id: str,
) -> None:
    from tradingagents.observability.events import RunEventDraft

    events = observer.store.read_events(observer.run_id)
    if any(
        event.type == "role.status_changed"
        and event.payload.get("turn_id") == turn_id
        and event.payload.get("new_status") == "completed"
        for event in events
    ):
        return
    turn_event = next(
        (
            event
            for event in events
            if event.type.startswith("turn.")
            and event.payload.get("turn_id") == turn_id
        ),
        None,
    )
    if turn_event is None or turn_event.actor_id is None:
        raise RuntimeError("committed turn has no durable role identity")
    previous = next(
        (
            event.payload.get("new_status")
            for event in reversed(events)
            if event.type == "role.status_changed"
            and event.actor_id == turn_event.actor_id
        ),
        "running",
    )
    observer.emit(
        RunEventDraft(
            observer.run_id,
            "role.status_changed",
            {
                "role_instance_id": turn_event.payload["role_instance_id"],
                "previous_status": previous,
                "new_status": "completed",
                "reason": "checkpoint_committed",
                "turn_id": turn_id,
            },
            team_id=turn_event.team_id,
            actor_id=turn_event.actor_id,
            node_id=turn_event.node_id,
            parent_event_id=checkpoint_event_id,
            status="completed",
        )
    )
