"""One authoritative execution path for CLI, web, and programmatic callers."""

from __future__ import annotations

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

    initial_state: Mapping[str, Any]
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
                token.raise_if_cancelled()
                prepared = self._create_initial_state(
                    request,
                    initial_context,
                    observation_context=observation_context,
                )
            self._open_legacy_checkpoint(request, run_id=checkpoint_run_id)
            if prepared is None:
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
            configurable["thread_id"] = thread_id(
                request.ticker,
                request.analysis_date,
                run_shape,
                **_run_id_kwargs(checkpoint_run_id),
            )

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
        initial_state: Mapping[str, Any],
        graph_args: dict[str, Any],
        cancellation_token: CancellationToken,
        observation_context: Any | None,
    ) -> Mapping[str, Any]:
        owner = self.owner
        invocation_args = dict(graph_args)
        if observation_context is not None:
            invocation_args["context"] = observation_context
        stream_mode = invocation_args.get("stream_mode", "values")
        final_state: Mapping[str, Any] | None = None
        merged: dict[str, Any] = {}
        last_printed = None

        for chunk in owner.graph.stream(initial_state, **invocation_args):
            if not isinstance(chunk, Mapping):
                raise TypeError("graph state stream must yield mappings")
            if stream_mode == "values":
                final_state = chunk
            else:
                merged.update(chunk)
                final_state = merged

            if owner.debug and chunk.get("messages"):
                message = chunk["messages"][-1]
                signature = (type(message).__name__, getattr(message, "content", None))
                if signature != last_printed:
                    message.pretty_print()
                    last_printed = signature
            cancellation_token.raise_if_cancelled(final_state)

        if final_state is None:
            raise RuntimeError("graph completed without yielding final state")
        return final_state

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
        owner.graph = owner.workflow.compile(checkpointer=saver)
        self._checkpoint_graph_recompiled = True
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
