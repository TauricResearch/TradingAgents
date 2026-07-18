"""Single-writer lifecycle owner for localhost analysis workers."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, Protocol

from tradingagents.dataflows.config import config_scope
from tradingagents.dataflows.interface import news_cache_scope
from tradingagents.dataflows.progress import DataProgressEvent, progress_sink
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.execution.config_identity import prepare_effective_config
from tradingagents.execution.models import (
    AnalysisCancelled,
    AnalysisRequest,
    AnalysisResult,
    CancellationToken,
)
from tradingagents.observability.events import PersistedEvent, RunEventDraft
from tradingagents.observability.graph_tasks import GraphObservationRunContext
from tradingagents.observability.observer import DurableRunObserver
from tradingagents.observability.projections import RoleProjectionRunContext
from tradingagents.observability.provenance import provenance_scope
from tradingagents.observability.roles import ROLE_REGISTRY, role_instance_id

from .broker import EventBroker
from .reports import ReportArtifactWriter
from .run_models import RunSnapshot
from .store import RunStore

TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})
RETRYABLE_RUN_STATUSES = TERMINAL_RUN_STATUSES | {"interrupted"}
ORPHANED_RUN_STATUSES = frozenset({"running", "cancel_requested"})


class ManagedRunner(Protocol):
    def run(
        self,
        request: AnalysisRequest,
        *,
        cancellation_token: CancellationToken,
        observation_context: GraphObservationRunContext,
        callbacks: list[Any],
        checkpoint_run_id: str,
        checkpoint_guard: Any,
    ) -> AnalysisResult: ...


RunnerFactory = Callable[[AnalysisRequest, DurableRunObserver], ManagedRunner]
CheckpointGuardFactory = Callable[
    [RunStore, str, AnalysisRequest, Mapping[str, Any]],
    Any,
]
RequestResolver = Callable[[RunSnapshot], AnalysisRequest]
ResumePreflight = Callable[[RunSnapshot, AnalysisRequest], Any]
StartupReconciler = Callable[[RunSnapshot, DurableRunObserver], None]


class RunManagerError(RuntimeError):
    pass


class ActiveRunConflict(RunManagerError):
    def __init__(self, active_run_id: str):
        self.active_run_id = active_run_id
        super().__init__(f"another analysis is active: {active_run_id}")


class RunNotActive(RunManagerError):
    pass


class RunNotRetryable(RunManagerError):
    pass


class ResumeRunConflict(RunManagerError):
    def __init__(self, message: str, *, fields: tuple[str, ...] = ()):
        self.fields = fields
        super().__init__(message)


class RunNotResumable(ResumeRunConflict):
    pass


@dataclass
class _ActiveRun:
    run_id: str
    token: CancellationToken
    thread: threading.Thread
    phase: str = "running"


class SingleRunManager:
    """Own exactly one background analysis and every durable lifecycle edge."""

    def __init__(
        self,
        store: RunStore,
        broker: EventBroker | None = None,
        runner_factory: RunnerFactory | None = None,
        *,
        report_writer: ReportArtifactWriter | None = None,
        checkpoint_guard_factory: CheckpointGuardFactory | None = None,
        startup_reconciler: StartupReconciler | None = None,
        request_resolver: RequestResolver | None = None,
        resume_preflight: ResumePreflight | None = None,
    ) -> None:
        self.store = store
        self.broker = broker or EventBroker(store)
        self._uses_default_runner_factory = runner_factory is None
        self.runner_factory = runner_factory or _default_runner_factory
        self.report_writer = report_writer or ReportArtifactWriter(store)
        self.checkpoint_guard_factory = (
            checkpoint_guard_factory or _default_checkpoint_guard_factory
        )
        self.startup_reconciler = startup_reconciler
        self.request_resolver = request_resolver
        self.resume_preflight = resume_preflight
        self._guard = threading.RLock()
        self._active: _ActiveRun | None = None
        self._requests: dict[str, AnalysisRequest] = {}

    @property
    def active_run_id(self) -> str | None:
        with self._guard:
            return self._active.run_id if self._active is not None else None

    def start(
        self,
        request: AnalysisRequest,
        *,
        configured_keys: Mapping[str, bool] | None = None,
    ) -> RunSnapshot:
        normalized = _complete_request(request)
        with self._guard:
            self._assert_idle()
            snapshot = self._create_run(
                normalized,
                configured_keys=configured_keys,
            )
            self._launch(snapshot.run_id, normalized, resume=False)
            return self.store.read_snapshot(snapshot.run_id)

    def cancel(self, run_id: str) -> RunSnapshot:
        with self._guard:
            active = self._active
            if active is None or active.run_id != run_id:
                raise RunNotActive(f"run is not active: {run_id}")
            if active.phase != "running":
                raise RunNotActive(f"run is already terminalizing: {run_id}")
            snapshot = self.store.read_snapshot(run_id)
            if snapshot.status == "cancel_requested":
                return snapshot
            if snapshot.status != "running":
                raise RunNotActive(f"run cannot be cancelled from {snapshot.status}")
            self.broker.publish(
                RunEventDraft(
                    run_id,
                    "run.cancel_requested",
                    {
                        "run_status": "cancel_requested",
                        "summary": "Cancellation requested by the local user.",
                    },
                    status="cancel_requested",
                )
            )
            active.token.cancel()
            return self.store.read_snapshot(run_id)

    def retry(self, run_id: str) -> RunSnapshot:
        source = self.store.read_snapshot(run_id)
        if source.status not in RETRYABLE_RUN_STATUSES:
            raise RunNotRetryable(
                f"run cannot be retried from status {source.status}: {run_id}"
            )
        request = self._request_for_snapshot(source)
        with self._guard:
            self._assert_idle()
            snapshot = self._create_run(
                request,
                configured_keys=source.configured_keys,
                retry_of=source.run_id,
            )
            self._launch(snapshot.run_id, request, resume=False)
            return self.store.read_snapshot(snapshot.run_id)

    def resume(self, run_id: str) -> RunSnapshot:
        snapshot = self.store.read_snapshot(run_id)
        if snapshot.status != "interrupted":
            raise RunNotResumable(
                f"run cannot be resumed from status {snapshot.status}: {run_id}"
            )
        request = self._request_for_snapshot(snapshot)
        with self._guard:
            self._assert_idle()
            checkpoint_guard = self._validate_resume(snapshot, request)
            resumed_from = snapshot.latest_sequence
            checkpoint_sequence = _checkpoint_sequence(
                self.store.read_events(run_id)
            )
            self.store.write_snapshot_atomic(
                snapshot.evolve(resumed_from_sequence=resumed_from)
            )
            self.broker.publish(
                RunEventDraft(
                    run_id,
                    "run.resumed",
                    {
                        "run_status": "running",
                        "checkpoint_sequence": checkpoint_sequence,
                        "resumed_from_sequence": resumed_from,
                    },
                    status="running",
                )
            )
            self._launch(
                run_id,
                request,
                resume=True,
                checkpoint_guard_override=checkpoint_guard,
                resumed_from_sequence=resumed_from,
            )
            return self.store.read_snapshot(run_id)

    def recover_startup(self) -> tuple[RunSnapshot, ...]:
        recovered: list[RunSnapshot] = []
        with self._guard:
            self._assert_idle()
            for summary in self.store.list_runs():
                if summary.status not in ORPHANED_RUN_STATUSES:
                    continue
                snapshot = self.store.read_snapshot(summary.run_id)
                request = self._request_for_snapshot(snapshot)
                observer = DurableRunObserver(
                    self.store,
                    snapshot.run_id,
                    event_sink=self.broker.publish,
                    development_assertions=False,
                )
                reconciliation_error: BaseException | None = None
                try:
                    self._reconcile_startup(snapshot, request, observer)
                except Exception as exc:
                    reconciliation_error = exc
                reason = (
                    "startup_reconciliation_failed"
                    if reconciliation_error is not None
                    else "server_restarted"
                )
                self._terminalize_open_lifecycles(
                    snapshot.run_id,
                    mode="interrupted",
                    reason=reason,
                )
                events = self.store.read_events(snapshot.run_id)
                current = self.store.read_snapshot(snapshot.run_id)
                self.store.write_snapshot_atomic(
                    current.evolve(
                        summary="The local server stopped before this analysis finished.",
                        error_category=(
                            _error_category(reconciliation_error)
                            if reconciliation_error is not None
                            else None
                        ),
                    )
                )
                self.broker.publish(
                    RunEventDraft(
                        snapshot.run_id,
                        "run.interrupted",
                        {
                            "run_status": "interrupted",
                            "checkpoint_sequence": _checkpoint_sequence(events),
                            "summary": "The local server stopped before this analysis finished.",
                            **(
                                {
                                    "error_category": _error_category(
                                        reconciliation_error
                                    )
                                }
                                if reconciliation_error is not None
                                else {}
                            ),
                        },
                        status="interrupted",
                    )
                )
                recovered.append(self.store.read_snapshot(snapshot.run_id))
        return tuple(recovered)

    def wait(self, run_id: str, timeout: float | None = None) -> RunSnapshot:
        with self._guard:
            active = self._active if self._active and self._active.run_id == run_id else None
        if active is not None:
            active.thread.join(timeout)
        return self.store.read_snapshot(run_id)

    def _assert_idle(self) -> None:
        if self._active is not None:
            raise ActiveRunConflict(self._active.run_id)

    def _create_run(
        self,
        request: AnalysisRequest,
        *,
        configured_keys: Mapping[str, bool] | None,
        retry_of: str | None = None,
    ) -> RunSnapshot:
        config = dict(request.effective_config)
        safe_config = prepare_effective_config(config)
        snapshot = RunSnapshot.create(
            ticker=request.ticker,
            analysis_date=request.analysis_date,
            asset_type=request.asset_type,
            selected_analysts=request.selected_analysts,
            max_debate_rounds=request.max_debate_rounds,
            max_risk_discuss_rounds=request.max_risk_discuss_rounds,
            output_language=str(config.get("output_language") or "English"),
            llm_provider=str(config.get("llm_provider") or ""),
            quick_think_llm=str(config.get("quick_think_llm") or ""),
            deep_think_llm=str(config.get("deep_think_llm") or ""),
            configured_keys=dict(configured_keys or {}),
            retry_of=retry_of,
            metadata={"effective_config": safe_config},
        )
        self.store.create_run(snapshot)
        self.broker.publish(
            RunEventDraft(
                snapshot.run_id,
                "run.started",
                {
                    "run_status": "running",
                    "retry_of": retry_of,
                },
                status="running",
            )
        )
        self._initialize_roles(snapshot.run_id, request.selected_analysts)
        self._requests[snapshot.run_id] = request
        return self.store.read_snapshot(snapshot.run_id)

    def _initialize_roles(
        self,
        run_id: str,
        selected_analysts: tuple[str, ...],
    ) -> None:
        selected = set(selected_analysts)
        for role in ROLE_REGISTRY:
            included = role.analyst_key is None or role.analyst_key in selected
            status = "pending" if included else "skipped"
            reason = "selected" if included else "not_selected"
            self.broker.publish(
                RunEventDraft(
                    run_id,
                    "role.status_changed",
                    {
                        "role_instance_id": role_instance_id(run_id, role.actor_id),
                        "previous_status": "uninitialized",
                        "new_status": status,
                        "reason": reason,
                    },
                    team_id=role.team_id,
                    actor_id=role.actor_id,
                    node_id=role.node_id,
                    status=status,
                )
            )

    def _launch(
        self,
        run_id: str,
        request: AnalysisRequest,
        *,
        resume: bool,
        checkpoint_guard_override: Any | None = None,
        resumed_from_sequence: int | None = None,
    ) -> None:
        token = CancellationToken()
        thread = threading.Thread(
            target=self._worker,
            args=(
                run_id,
                request,
                token,
                resume,
                checkpoint_guard_override,
                resumed_from_sequence,
            ),
            name=f"tradingagents-{run_id}",
            daemon=True,
        )
        active = _ActiveRun(run_id, token, thread)
        self._active = active
        try:
            thread.start()
        except BaseException as exc:
            self._active = None
            self._finish_failure(run_id, exc)
            raise

    def _worker(
        self,
        run_id: str,
        request: AnalysisRequest,
        token: CancellationToken,
        resume: bool,
        checkpoint_guard_override: Any | None,
        resumed_from_sequence: int | None,
    ) -> None:
        observer = DurableRunObserver(
            self.store,
            run_id,
            event_sink=self.broker.publish,
            development_assertions=False,
        )
        try:
            with config_scope(request.effective_config), progress_sink(
                self._progress_sink(observer)
            ), news_cache_scope(run_id), provenance_scope(observer):
                config_artifact = observer.store_artifact(
                    "data",
                    prepare_effective_config(request.effective_config),
                )
                self._record_config_artifact(run_id, config_artifact.artifact_id)
                if resume:
                    if resumed_from_sequence is None:
                        raise RunNotResumable("resume sequence is missing")
                    self._resume_open_turns(observer, resumed_from_sequence)
                run_context = GraphObservationRunContext(
                    observer,
                    RoleProjectionRunContext(
                        request.effective_config,
                        effective_config_artifact_id=config_artifact.artifact_id,
                    ),
                )
                runner = self.runner_factory(request, observer)
                checkpoint_guard = checkpoint_guard_override
                if checkpoint_guard is None:
                    checkpoint_guard = self.checkpoint_guard_factory(
                        self.store,
                        run_id,
                        request,
                        request.effective_config,
                    )
                result = runner.run(
                    request,
                    cancellation_token=token,
                    observation_context=run_context,
                    callbacks=[observer],
                    checkpoint_run_id=run_id,
                    checkpoint_guard=checkpoint_guard,
                )
                status = self._begin_terminalization(run_id)
                if status == "cancel_requested":
                    self._finish_cancelled(run_id)
                else:
                    self._finish_success(run_id, request, result)
        except AnalysisCancelled:
            self._begin_terminalization(run_id)
            self._finish_cancelled(run_id)
        except BaseException as exc:
            self._begin_terminalization(run_id)
            if self.store.read_snapshot(run_id).status not in TERMINAL_RUN_STATUSES:
                self._finish_failure(run_id, exc)
        finally:
            with self._guard:
                if self._active is not None and self._active.run_id == run_id:
                    self._active = None

    def _begin_terminalization(self, run_id: str) -> str:
        with self._guard:
            active = self._active
            if active is not None and active.run_id == run_id:
                active.phase = "terminalizing"
            return self.store.read_snapshot(run_id).status

    def _finish_success(
        self,
        run_id: str,
        request: AnalysisRequest,
        result: AnalysisResult,
    ) -> None:
        invalid_roles = {
            actor_id: status
            for actor_id, (status, _event) in _reduce_open_lifecycles(
                self.store.read_events(run_id)
            ).roles.items()
            if status in {"pending", "running", "interrupted"}
        }
        if invalid_roles:
            raise RunManagerError(
                "successful analysis left non-terminal aggregate roles"
            )
        publication = self.report_writer.publish_final(
            run_id,
            dict(result.final_state),
            request.ticker,
        )
        artifact_ids: list[str] = []
        for artifact in publication.artifacts:
            artifact_ids.append(artifact.artifact_id)
            self.broker.publish(
                RunEventDraft(
                    run_id,
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
        current = self.store.read_snapshot(run_id)
        self.store.write_snapshot_atomic(
            current.evolve(
                final_signal=result.final_signal,
                summary="Analysis completed successfully.",
                error_category=None,
                artifacts=tuple(dict.fromkeys((*current.artifacts, *artifact_ids))),
            )
        )
        self.broker.publish(
            RunEventDraft(
                run_id,
                "run.completed",
                {
                    "run_status": "completed",
                    "summary": "Analysis completed successfully.",
                    "final_signal": result.final_signal,
                    "report_artifact_ids": artifact_ids,
                },
                status="completed",
            )
        )

    def _finish_cancelled(self, run_id: str) -> None:
        snapshot = self.store.read_snapshot(run_id)
        if snapshot.status == "running":
            self.broker.publish(
                RunEventDraft(
                    run_id,
                    "run.cancel_requested",
                    {
                        "run_status": "cancel_requested",
                        "summary": "Cancellation reached a safe execution boundary.",
                    },
                    status="cancel_requested",
                )
            )
        self._terminalize_open_lifecycles(
            run_id,
            mode="cancelled",
            reason="user_cancelled",
        )
        summary = "Analysis cancelled by the local user."
        current = self.store.read_snapshot(run_id)
        self.store.write_snapshot_atomic(current.evolve(summary=summary))
        self.broker.publish(
            RunEventDraft(
                run_id,
                "run.cancelled",
                {"run_status": "cancelled", "summary": summary},
                status="cancelled",
            )
        )

    def _finish_failure(self, run_id: str, error: BaseException) -> None:
        self._terminalize_open_lifecycles(
            run_id,
            mode="failed",
            reason="analysis_failed",
        )
        category = _error_category(error)
        summary = f"Analysis failed in the {category.replace('_', ' ')} stage."
        current = self.store.read_snapshot(run_id)
        self.store.write_snapshot_atomic(
            current.evolve(summary=summary, error_category=category)
        )
        self.broker.publish(
            RunEventDraft(
                run_id,
                "run.failed",
                {
                    "run_status": "failed",
                    "summary": summary,
                    "error_category": category,
                },
                status="failed",
            )
        )

    def _terminalize_open_lifecycles(
        self,
        run_id: str,
        *,
        mode: str,
        reason: str,
    ) -> None:
        reduced = _reduce_open_lifecycles(self.store.read_events(run_id))
        model_terminal = "model.failed" if mode == "failed" else "model.interrupted"
        for event in reduced.models.values():
            payload = {
                **event.payload,
                "duration_ms": 0,
                "usage": {},
                "reason": reason,
            }
            self.broker.publish(_terminal_draft(event, model_terminal, payload, mode))

        data_terminal = "data.failed" if mode == "failed" else "data.interrupted"
        for event in reduced.data_calls.values():
            payload = {
                **event.payload,
                "stage": "failed" if mode == "failed" else "interrupted",
                "data_status": "failed" if mode == "failed" else "interrupted",
                "duration_ms": 0,
                "reason": reason,
            }
            self.broker.publish(_terminal_draft(event, data_terminal, payload, mode))

        execution_terminal = (
            "tool.execution_failed"
            if mode == "failed"
            else "tool.execution_interrupted"
        )
        for event in reduced.tool_executions.values():
            payload = {**event.payload, "duration_ms": 0, "reason": reason}
            self.broker.publish(
                _terminal_draft(event, execution_terminal, payload, mode)
            )

        if mode != "interrupted":
            for event in reduced.logical_tools.values():
                self.broker.publish(
                    _terminal_draft(
                        event,
                        "tool.cancelled",
                        {**event.payload, "reason": reason},
                        "cancelled",
                    )
                )

        turn_status = mode
        for event in reduced.turns.values():
            self.broker.publish(
                _terminal_draft(
                    event,
                    f"turn.{turn_status}",
                    {
                        **event.payload,
                        "turn_status": turn_status,
                        "duration_ms": 0,
                        "reason": reason,
                    },
                    turn_status,
                )
            )

        for actor_id, (status, event) in reduced.roles.items():
            if status != "running":
                continue
            role = next(role for role in ROLE_REGISTRY if role.actor_id == actor_id)
            self.broker.publish(
                RunEventDraft(
                    run_id,
                    "role.status_changed",
                    {
                        "role_instance_id": role_instance_id(run_id, actor_id),
                        "previous_status": "running",
                        "new_status": mode,
                        "reason": reason,
                        **(
                            {"turn_id": event.payload.get("turn_id")}
                            if event.payload.get("turn_id")
                            else {}
                        ),
                    },
                    team_id=role.team_id,
                    actor_id=actor_id,
                    node_id=role.node_id,
                    status=mode,
                    parent_event_id=event.event_id,
                )
            )
        if mode != "interrupted":
            self._terminalize_pending_roles(run_id, reason=reason)

    def _terminalize_pending_roles(self, run_id: str, *, reason: str) -> None:
        reduced = _reduce_open_lifecycles(self.store.read_events(run_id))
        for actor_id, (status, event) in reduced.roles.items():
            if status != "pending":
                continue
            role = next(role for role in ROLE_REGISTRY if role.actor_id == actor_id)
            self.broker.publish(
                RunEventDraft(
                    run_id,
                    "role.status_changed",
                    {
                        "role_instance_id": role_instance_id(run_id, actor_id),
                        "previous_status": "pending",
                        "new_status": "not_reached",
                        "reason": reason,
                    },
                    team_id=role.team_id,
                    actor_id=actor_id,
                    node_id=role.node_id,
                    status="not_reached",
                    parent_event_id=event.event_id,
                )
            )

    def _record_config_artifact(self, run_id: str, artifact_id: str) -> None:
        with self.store.lock_for(run_id):
            current = self.store.read_snapshot(run_id)
            metadata = dict(current.metadata)
            metadata["effective_config_artifact_id"] = artifact_id
            self.store.write_snapshot_atomic(
                current.evolve(
                    metadata=metadata,
                    artifacts=tuple(
                        dict.fromkeys((*current.artifacts, artifact_id))
                    ),
                )
            )

    def _progress_sink(
        self,
        observer: DurableRunObserver,
    ) -> Callable[[DataProgressEvent], None]:
        def emit(event: DataProgressEvent) -> None:
            if (
                event.run_id == observer.run_id
                and event.turn_id
                and event.graph_task_id
                and event.vendor_call_id
            ):
                observer.emit(
                    RunEventDraft(
                        observer.run_id,
                        "data.progress",
                        {
                            "turn_id": event.turn_id,
                            "graph_task_id": event.graph_task_id,
                            "tool_call_id": event.tool_call_id,
                            "vendor_call_id": event.vendor_call_id,
                            "method": event.method,
                            "vendor": event.vendor,
                            "stage": event.stage,
                            "data_status": "progress",
                            "message": event.message,
                            "artifact_id": event.artifact_id,
                        },
                        status="progress",
                    )
                )

        return emit

    def _resume_open_turns(
        self,
        observer: DurableRunObserver,
        resumed_from_sequence: int,
    ) -> None:
        reduced = _reduce_open_lifecycles(
            self.store.read_events(observer.run_id)
        )
        for turn_id in reduced.interrupted_turns:
            observer.resume_turn(turn_id, resumed_from_sequence)

    def _request_for_snapshot(self, snapshot: RunSnapshot) -> AnalysisRequest:
        request = self._requests.get(snapshot.run_id)
        if request is not None:
            return request
        if self.request_resolver is not None:
            return _complete_request(self.request_resolver(snapshot))
        resolved = _request_from_snapshot(snapshot)
        return _complete_request(resolved) if self._uses_default_runner_factory else resolved

    def _validate_resume(
        self,
        snapshot: RunSnapshot,
        request: AnalysisRequest,
    ) -> Any | None:
        if self.resume_preflight is not None:
            return self.resume_preflight(snapshot, request)
        if self._uses_default_runner_factory:
            return _default_resume_preflight(
                self.store,
                snapshot,
                request,
                self.runner_factory,
                self.checkpoint_guard_factory,
            )
        return None

    def _reconcile_startup(
        self,
        snapshot: RunSnapshot,
        request: AnalysisRequest,
        observer: DurableRunObserver,
    ) -> None:
        if self.startup_reconciler is not None:
            self.startup_reconciler(snapshot, observer)
            return
        _default_startup_reconciler(snapshot, request, observer)


@dataclass(frozen=True)
class _OpenLifecycles:
    models: dict[str, PersistedEvent]
    tool_executions: dict[str, PersistedEvent]
    data_calls: dict[str, PersistedEvent]
    logical_tools: dict[str, PersistedEvent]
    turns: dict[str, PersistedEvent]
    interrupted_turns: dict[str, PersistedEvent]
    roles: dict[str, tuple[str, PersistedEvent]]


def _reduce_open_lifecycles(events: list[PersistedEvent]) -> _OpenLifecycles:
    models: dict[str, PersistedEvent] = {}
    executions: dict[str, PersistedEvent] = {}
    data_calls: dict[str, PersistedEvent] = {}
    logical_tools: dict[str, PersistedEvent] = {}
    turns: dict[str, PersistedEvent] = {}
    interrupted_turns: dict[str, PersistedEvent] = {}
    roles: dict[str, tuple[str, PersistedEvent]] = {}
    for event in events:
        payload = event.payload
        if event.type == "model.started":
            models[str(payload["model_call_id"])] = event
        elif event.type in {"model.completed", "model.failed", "model.interrupted"}:
            models.pop(str(payload["model_call_id"]), None)
        elif event.type == "tool.execution_started":
            executions[str(payload["tool_execution_id"])] = event
        elif event.type in {
            "tool.execution_completed",
            "tool.execution_failed",
            "tool.execution_interrupted",
        }:
            executions.pop(str(payload["tool_execution_id"]), None)
        elif event.type == "data.progress":
            data_calls[str(payload["vendor_call_id"])] = event
        elif event.type in {"data.completed", "data.failed", "data.interrupted"}:
            data_calls.pop(str(payload["vendor_call_id"]), None)
        elif event.type == "tool.requested":
            logical_tools[str(payload["tool_call_id"])] = event
        elif event.type in {"tool.committed", "tool.cancelled"}:
            logical_tools.pop(str(payload["tool_call_id"]), None)
        elif event.type in {"turn.started", "turn.resumed", "turn.output_ready"}:
            turn_id = str(payload["turn_id"])
            turns[turn_id] = event
            interrupted_turns.pop(turn_id, None)
        elif event.type == "turn.interrupted":
            turn_id = str(payload["turn_id"])
            turns.pop(turn_id, None)
            interrupted_turns[turn_id] = event
        elif event.type in {"turn.completed", "turn.failed", "turn.cancelled"}:
            turn_id = str(payload["turn_id"])
            turns.pop(turn_id, None)
            interrupted_turns.pop(turn_id, None)
        if event.type == "role.status_changed" and event.actor_id:
            roles[event.actor_id] = (str(payload["new_status"]), event)
    return _OpenLifecycles(
        models,
        executions,
        data_calls,
        logical_tools,
        turns,
        interrupted_turns,
        roles,
    )


def _terminal_draft(
    source: PersistedEvent,
    event_type: str,
    payload: dict[str, Any],
    status: str,
) -> RunEventDraft:
    return RunEventDraft(
        source.run_id,
        event_type,
        payload,
        team_id=source.team_id,
        actor_id=source.actor_id,
        node_id=source.node_id,
        status=status,
        parent_event_id=source.event_id,
    )


def _complete_request(request: AnalysisRequest) -> AnalysisRequest:
    config = deepcopy(DEFAULT_CONFIG)
    for key, value in request.effective_config.items():
        if isinstance(value, Mapping) and isinstance(config.get(key), dict):
            config[key].update(deepcopy(dict(value)))
        else:
            config[key] = deepcopy(value)
    config["max_debate_rounds"] = request.max_debate_rounds
    config["max_risk_discuss_rounds"] = request.max_risk_discuss_rounds
    return replace(request, effective_config=config)


def _request_from_snapshot(snapshot: RunSnapshot) -> AnalysisRequest:
    config: dict[str, Any] = {}
    stored = snapshot.metadata.get("effective_config")
    if isinstance(stored, Mapping):
        for key, value in stored.items():
            if key == "backend_url" and isinstance(value, Mapping):
                config[key] = _endpoint_from_identity(value)
            elif isinstance(value, Mapping) and isinstance(config.get(key), dict):
                config[key].update(deepcopy(dict(value)))
            else:
                config[key] = deepcopy(value)
    config.update(
        {
            "llm_provider": snapshot.llm_provider,
            "quick_think_llm": snapshot.quick_think_llm,
            "deep_think_llm": snapshot.deep_think_llm,
            "max_debate_rounds": snapshot.max_debate_rounds,
            "max_risk_discuss_rounds": snapshot.max_risk_discuss_rounds,
            "output_language": snapshot.output_language,
        }
    )
    return AnalysisRequest(
        ticker=snapshot.ticker,
        analysis_date=snapshot.analysis_date,
        asset_type=snapshot.asset_type,
        selected_analysts=snapshot.selected_analysts,
        max_debate_rounds=snapshot.max_debate_rounds,
        max_risk_discuss_rounds=snapshot.max_risk_discuss_rounds,
        effective_config=config,
    )


def _endpoint_from_identity(value: Mapping[str, Any]) -> str | None:
    scheme = value.get("scheme")
    host = value.get("host")
    if not isinstance(scheme, str) or not isinstance(host, str) or not scheme or not host:
        return None
    port = value.get("port")
    path = value.get("path") if isinstance(value.get("path"), str) else "/"
    default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
    authority = host if port in {None, default_port} else f"{host}:{port}"
    return f"{scheme}://{authority}{path or '/'}"


def _default_runner_factory(
    request: AnalysisRequest,
    observer: DurableRunObserver,
) -> ManagedRunner:
    from tradingagents.execution.runner import AnalysisRunner
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    owner = TradingAgentsGraph(
        selected_analysts=request.selected_analysts,
        config=dict(request.effective_config),
        callbacks=[observer],
        observation_enabled=True,
    )
    return AnalysisRunner(owner)


def _default_checkpoint_guard_factory(
    store: RunStore,
    run_id: str,
    request: AnalysisRequest,
    effective_config: Mapping[str, Any],
) -> Any:
    from .fingerprint import FingerprintCheckpointGuard

    return FingerprintCheckpointGuard(
        store,
        run_id,
        request,
        effective_config,
    )


def _default_resume_preflight(
    store: RunStore,
    snapshot: RunSnapshot,
    request: AnalysisRequest,
    runner_factory: RunnerFactory,
    guard_factory: CheckpointGuardFactory,
) -> Any:
    from tradingagents.execution.runner import AnalysisRunner, checkpoint_access

    from .fingerprint import CheckpointIncompatible
    from .reconciliation import (
        CheckpointObservationIncompatible,
        reconcile_checkpoint_frontier,
    )

    observer = DurableRunObserver(
        store,
        snapshot.run_id,
        development_assertions=False,
    )
    with config_scope(request.effective_config):
        runner = runner_factory(request, observer)
        if not isinstance(runner, AnalysisRunner):
            raise RunNotResumable("the configured runner cannot prove resume compatibility")
        owner = runner.owner
        if not owner.config.get("checkpoint_enabled"):
            raise RunNotResumable("checkpoint resume is disabled")
        owner.ticker = request.ticker
        owner._resolve_pending_entries(request.ticker)
        initial_context = runner._resolve_initial_context(request)
        access = checkpoint_access(
            owner.config["data_cache_dir"],
            request.ticker,
            request.analysis_date,
            owner._run_signature(request.asset_type),
            run_id=snapshot.run_id,
        )
        guard = guard_factory(
            store,
            snapshot.run_id,
            request,
            request.effective_config,
        )
        try:
            preauthorize = getattr(guard, "preauthorize", None)
            authorization = (
                preauthorize(initial_context, access)
                if callable(preauthorize)
                else guard(initial_context, access)
            )
        except CheckpointIncompatible as exc:
            raise ResumeRunConflict(
                "checkpoint_incompatible",
                fields=exc.mismatch_categories,
            ) from exc
        if authorization.mode != "resume":
            raise RunNotResumable("no durable checkpoint exists for this run")
        assert access.latest is not None
        try:
            plan = reconcile_checkpoint_frontier(
                store.read_events(snapshot.run_id),
                access.latest,
                access.parent,
                read_artifact=lambda artifact_id: store.read_artifact(
                    snapshot.run_id,
                    artifact_id,
                ),
            )
        except CheckpointObservationIncompatible as exc:
            raise ResumeRunConflict(
                "checkpoint_observation_incompatible",
                fields=exc.categories,
            ) from exc
        if plan.missing_checkpoint_transition is not None or plan.abandoned_task_ids:
            raise ResumeRunConflict(
                "checkpoint_observation_not_reconciled",
                fields=("observation_frontier",),
            )
        return guard


def _default_startup_reconciler(
    snapshot: RunSnapshot,
    request: AnalysisRequest,
    observer: DurableRunObserver,
) -> None:
    from tradingagents.execution.runner import AnalysisRunner, checkpoint_access

    from .reconciliation import apply_reconciliation_plan, reconcile_checkpoint_frontier

    config = request.effective_config
    if not config.get("checkpoint_enabled"):
        _abandon_uncommitted_event_tail(observer, cancel_all_tools=True)
        return
    signature = "|".join(
        (
            "analysts=" + ",".join(request.selected_analysts),
            f"debate={request.max_debate_rounds}",
            f"risk={request.max_risk_discuss_rounds}",
            f"asset={request.asset_type}",
        )
    )
    access = checkpoint_access(
        config["data_cache_dir"],
        request.ticker,
        request.analysis_date,
        signature,
        run_id=snapshot.run_id,
    )
    if access.latest is None:
        _abandon_uncommitted_event_tail(observer, cancel_all_tools=True)
        return
    plan = reconcile_checkpoint_frontier(
        observer.store.read_events(snapshot.run_id),
        access.latest,
        access.parent,
        read_artifact=lambda artifact_id: observer.store.read_artifact(
            snapshot.run_id,
            artifact_id,
        ),
    )

    def current_checkpoint_id() -> str | None:
        current = checkpoint_access(
            config["data_cache_dir"],
            request.ticker,
            request.analysis_date,
            signature,
            run_id=snapshot.run_id,
        ).latest
        if current is None:
            return None
        configurable = current.config.get("configurable", {})
        return configurable.get("checkpoint_id") or current.checkpoint.get("id")

    apply_reconciliation_plan(
        observer.store,
        snapshot.run_id,
        plan,
        current_checkpoint_id=current_checkpoint_id,
        observer=observer,
    )
    AnalysisRunner.promote_reconciled_tasks(observer, plan)


def _abandon_uncommitted_event_tail(
    observer: DurableRunObserver,
    *,
    cancel_all_tools: bool,
) -> None:
    """Close event work that has no durable SQLite frontier to resume from."""
    events = observer.store.read_events(observer.run_id)
    committed = {
        str(task_id)
        for event in events
        if event.type in {"graph.step_applied", "graph.checkpoint_committed"}
        for task_id in event.payload.get("applied_task_ids", ())
    }
    abandoned = {
        str(event.payload["graph_task_id"])
        for event in events
        if event.type == "graph.task_abandoned"
    }
    starts = {
        str(event.payload["graph_task_id"]): event
        for event in events
        if event.type == "graph.task_started"
    }
    candidates = {
        str(event.payload["observation_commit"]["graph_task_id"]): event
        for event in events
        if event.type == "graph.task_output_ready"
        and isinstance(event.payload.get("observation_commit"), Mapping)
    }
    tails = sorted(
        (set(starts) | set(candidates)) - committed - abandoned,
        key=lambda task_id: (starts.get(task_id) or candidates[task_id]).sequence,
    )
    for task_id in tails:
        source = starts.get(task_id) or candidates[task_id]
        observer.emit(
            RunEventDraft(
                observer.run_id,
                "graph.task_abandoned",
                {
                    "graph_task_id": task_id,
                    "graph_step": source.payload["graph_step"],
                    "node_id": source.payload["node_id"],
                    "reason": "process_interrupted_without_checkpoint",
                },
                actor_id=source.actor_id,
                node_id=source.node_id,
                status="abandoned",
                parent_event_id=source.event_id,
            )
        )

    refreshed = observer.store.read_events(observer.run_id)
    reduced = _reduce_open_lifecycles(refreshed)
    tail_set = set(tails)
    for event in reduced.logical_tools.values():
        if cancel_all_tools or str(event.payload["graph_task_id"]) in tail_set:
            observer.emit(
                _terminal_draft(
                    event,
                    "tool.cancelled",
                    {
                        **event.payload,
                        "reason": "process_interrupted_without_checkpoint",
                    },
                    "cancelled",
                )
            )


def _checkpoint_sequence(events: list[PersistedEvent]) -> int:
    return max(
        (
            event.sequence
            for event in events
            if event.type == "graph.checkpoint_committed"
        ),
        default=0,
    )


def _error_category(error: BaseException | None) -> str:
    if error is None:
        return "unexpected_internal_failure"
    name = type(error).__name__.lower()
    if "checkpoint" in name or "fingerprint" in name:
        return "checkpoint_incompatibility"
    if "auth" in name or "credential" in name:
        return "provider_authentication"
    if "timeout" in name:
        return "provider_timeout"
    if "rate" in name and "limit" in name:
        return "vendor_rate_limit"
    if "evidence" in name:
        return "evidence_rejection"
    if isinstance(error, (ValueError, KeyError)):
        return "missing_configuration"
    return "unexpected_internal_failure"
