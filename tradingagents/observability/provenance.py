"""One provenance model for tool-mediated and direct data-provider calls."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from tradingagents.observability.context import current_observation_context
from tradingagents.observability.events import RunEventDraft
from tradingagents.observability.redaction import redact_recursive


@dataclass(frozen=True)
class CacheOrigin:
    vendor_call_ids: tuple[str, ...]
    artifact_ids: tuple[str, ...]
    created_at_monotonic: float


@dataclass(frozen=True)
class VendorAttemptRef:
    vendor_call_id: str
    vendor: str
    attempt_index: int
    started_at: float
    fallback_chain: tuple[str, ...]


@dataclass
class _SuccessfulAttempt:
    ref: VendorAttemptRef
    vendor_output_artifact_id: str
    raw_artifact_ids: list[str] = field(default_factory=list)
    raw_metadata: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DataRequestObservation:
    observer: Any | None
    method: str
    arguments: Any
    request_id: str
    started_at: float
    period: dict[str, Any]
    unit: str | None = None
    currency: str | None = None
    _attempt_count: int = 0
    _attempt_ids: list[str] = field(default_factory=list)
    _successful: dict[str, _SuccessfulAttempt] = field(default_factory=dict)
    _pending_raw: dict[str, list[tuple[str, dict[str, Any]]]] = field(default_factory=dict)
    _cache_hit: bool = False

    @property
    def active(self) -> bool:
        return self.observer is not None and current_observation_context() is not None

    def start_attempt(
        self,
        vendor: str,
        *,
        fallback_chain: tuple[str, ...] | list[str] = (),
        emit_started: bool = True,
    ) -> VendorAttemptRef:
        self._attempt_count += 1
        ref = VendorAttemptRef(
            vendor_call_id=f"vendor_call_{uuid.uuid4().hex}",
            vendor=vendor,
            attempt_index=self._attempt_count,
            started_at=time.monotonic(),
            fallback_chain=tuple(fallback_chain),
        )
        self._attempt_ids.append(ref.vendor_call_id)
        if self.active and emit_started:
            self._emit(
                "data.progress",
                ref,
                stage="started",
                data_status="running",
                arguments=redact_recursive(self.arguments).value,
            )
        return ref

    @contextmanager
    def attempt_scope(self, ref: VendorAttemptRef) -> Iterator[VendorAttemptRef]:
        request_token = _CURRENT_DATA_REQUEST.set(self)
        attempt_token = _CURRENT_VENDOR_ATTEMPT.set(ref)
        try:
            yield ref
        finally:
            _CURRENT_VENDOR_ATTEMPT.reset(attempt_token)
            _CURRENT_DATA_REQUEST.reset(request_token)

    def capture_raw(
        self,
        ref: VendorAttemptRef,
        value: Any,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> str | None:
        if not self.active:
            return None
        artifact = self.observer.store_artifact(
            "data",
            redact_recursive(value).value,
        )
        self._pending_raw.setdefault(ref.vendor_call_id, []).append(
            (artifact.artifact_id, dict(metadata or {}))
        )
        return artifact.artifact_id

    def succeed(self, ref: VendorAttemptRef, vendor_output: Any) -> str | None:
        if not self.active:
            return None
        artifact = self.observer.store_artifact(
            "data",
            redact_recursive(vendor_output).value,
        )
        captured = self._pending_raw.pop(ref.vendor_call_id, [])
        self._successful[ref.vendor_call_id] = _SuccessfulAttempt(
            ref=ref,
            vendor_output_artifact_id=artifact.artifact_id,
            raw_artifact_ids=[item[0] for item in captured],
            raw_metadata=[item[1] for item in captured],
        )
        return artifact.artifact_id

    def fail(self, ref: VendorAttemptRef, error: BaseException | str) -> str | None:
        if not self.active:
            return None
        error_type = type(error).__name__ if isinstance(error, BaseException) else "DataUnavailable"
        artifact = self.observer.store_artifact(
            "data",
            {
                "error_type": error_type,
                "message": "Provider call failed; inspect local logs for the detailed error.",
            },
        )
        self._emit(
            "data.failed",
            ref,
            stage="vendor",
            data_status="failed",
            duration_ms=_duration_ms(ref.started_at),
            error_artifact_id=artifact.artifact_id,
            raw_artifact_ids=[item[0] for item in self._pending_raw.pop(ref.vendor_call_id, [])],
        )
        return artifact.artifact_id

    def skip(self, ref: VendorAttemptRef, *, reason: str) -> None:
        """Record an intentional router skip without inventing a provider error."""
        if not self.active:
            return
        self._emit(
            "data.progress",
            ref,
            stage="skipped_cooldown",
            data_status="skipped",
            reason=reason,
        )

    def complete(
        self, normalized_value: Any, *, data_status: str = "success"
    ) -> CacheOrigin | None:
        if not self.active or self._cache_hit:
            return None
        normalized = self.observer.store_artifact(
            "data",
            redact_recursive(normalized_value).value,
        )
        artifact_ids = [normalized.artifact_id]
        for successful in self._successful.values():
            artifact_ids.append(successful.vendor_output_artifact_id)
            artifact_ids.extend(successful.raw_artifact_ids)
            self._emit(
                "data.completed",
                successful.ref,
                stage="normalized",
                data_status=data_status,
                duration_ms=_duration_ms(successful.ref.started_at),
                raw_artifact_ids=list(successful.raw_artifact_ids),
                raw_capture_status=("captured" if successful.raw_artifact_ids else "unavailable"),
                raw_metadata=list(successful.raw_metadata),
                vendor_output_artifact_id=successful.vendor_output_artifact_id,
                normalized_artifact_id=normalized.artifact_id,
                origin_vendor_call_ids=list(self._attempt_ids),
            )
        return CacheOrigin(
            vendor_call_ids=tuple(self._attempt_ids),
            artifact_ids=tuple(dict.fromkeys(artifact_ids)),
            created_at_monotonic=time.monotonic(),
        )

    def cache_hit(self, *, cache_key: Any, origin: CacheOrigin) -> None:
        self._cache_hit = True
        if not self.active:
            return
        context = current_observation_context(required=True)
        assert context is not None
        self.observer.emit(
            RunEventDraft(
                context.run_id,
                "data.cache_hit",
                {
                    **_relationship_payload(context),
                    "cache_hit_id": f"cache_hit_{uuid.uuid4().hex}",
                    "cache_key_sha256": _cache_key_sha256(cache_key),
                    "origin_vendor_call_ids": list(origin.vendor_call_ids),
                    "origin_artifacts": list(origin.artifact_ids),
                    "age_ms": _duration_ms(origin.created_at_monotonic),
                    "method": self.method,
                },
                actor_id=context.actor_id,
                node_id=context.node_id,
                status="cache_hit",
            )
        )

    def request_failed(self, error: BaseException) -> None:
        if not self.active or self._attempt_count:
            return
        ref = VendorAttemptRef(
            vendor_call_id=self.request_id,
            vendor="router",
            attempt_index=0,
            started_at=self.started_at,
            fallback_chain=(),
        )
        self.fail(ref, error)

    def _emit(self, event_type: str, ref: VendorAttemptRef, **payload: Any) -> None:
        context = current_observation_context(required=True)
        assert context is not None
        self.observer.emit(
            RunEventDraft(
                context.run_id,
                event_type,
                {
                    **_relationship_payload(context),
                    "vendor_call_id": ref.vendor_call_id,
                    "request_id": self.request_id,
                    "method": self.method,
                    "vendor": ref.vendor,
                    "attempt_index": ref.attempt_index,
                    "fallback_chain": list(ref.fallback_chain),
                    "period": self.period,
                    "unit": self.unit,
                    "currency": self.currency,
                    **payload,
                },
                actor_id=context.actor_id,
                node_id=context.node_id,
                status=str(payload.get("data_status") or "progress"),
            )
        )


_CURRENT_PROVENANCE_OBSERVER: ContextVar[Any | None] = ContextVar(
    "tradingagents_provenance_observer",
    default=None,
)
_CURRENT_DATA_REQUEST: ContextVar[DataRequestObservation | None] = ContextVar(
    "tradingagents_data_request",
    default=None,
)
_CURRENT_VENDOR_ATTEMPT: ContextVar[VendorAttemptRef | None] = ContextVar(
    "tradingagents_vendor_attempt",
    default=None,
)


@contextmanager
def provenance_scope(observer: Any) -> Iterator[None]:
    token = _CURRENT_PROVENANCE_OBSERVER.set(observer)
    try:
        yield
    finally:
        _CURRENT_PROVENANCE_OBSERVER.reset(token)


def begin_data_request(
    method: str,
    args: tuple[Any, ...] = (),
    kwargs: Mapping[str, Any] | None = None,
) -> DataRequestObservation:
    return DataRequestObservation(
        observer=_CURRENT_PROVENANCE_OBSERVER.get(),
        method=method,
        arguments={"args": list(args), "kwargs": dict(kwargs or {})},
        request_id=f"data_request_{uuid.uuid4().hex}",
        started_at=time.monotonic(),
        period=_infer_period(method, args, kwargs or {}),
    )


def capture_vendor_raw(
    value: Any,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> str | None:
    """Adapter hook: persist the true transport/provider value before normalization."""
    request = _CURRENT_DATA_REQUEST.get()
    attempt = _CURRENT_VENDOR_ATTEMPT.get()
    if request is None or attempt is None:
        return None
    return request.capture_raw(attempt, value, metadata=metadata)


def current_progress_correlation() -> dict[str, Any]:
    context = current_observation_context()
    if context is None:
        return {}
    attempt = _CURRENT_VENDOR_ATTEMPT.get()
    successful = None
    request = _CURRENT_DATA_REQUEST.get()
    if request is not None and attempt is not None:
        successful = request._successful.get(attempt.vendor_call_id)
    return {
        "run_id": context.run_id,
        "turn_id": context.turn_id,
        "graph_task_id": context.graph_task_id,
        "tool_call_id": context.tool_call_id,
        "vendor_call_id": attempt.vendor_call_id if attempt else None,
        "artifact_id": successful.vendor_output_artifact_id if successful else None,
    }


@contextmanager
def direct_data_scope(invocation_path: str) -> Iterator[None]:
    observer = _CURRENT_PROVENANCE_OBSERVER.get()
    if observer is None:
        yield
        return
    with observer.direct_call_scope(invocation_path):
        yield


def capture_direct_call(
    *,
    invocation_path: str,
    method: str,
    vendor: str,
    function: Callable[..., Any],
    args: tuple[Any, ...] = (),
    kwargs: Mapping[str, Any] | None = None,
    normalize: Callable[[Any], Any] | None = None,
) -> Any:
    result, _origin = capture_direct_call_with_origin(
        invocation_path=invocation_path,
        method=method,
        vendor=vendor,
        function=function,
        args=args,
        kwargs=kwargs,
        normalize=normalize,
    )
    return result


def capture_direct_call_with_origin(
    *,
    invocation_path: str,
    method: str,
    vendor: str,
    function: Callable[..., Any],
    args: tuple[Any, ...] = (),
    kwargs: Mapping[str, Any] | None = None,
    normalize: Callable[[Any], Any] | None = None,
) -> tuple[Any, CacheOrigin | None]:
    """Run a direct provider call and return its durable artifact lineage.

    ``capture_direct_call`` remains the compatibility wrapper for existing
    callers.  Consumers that turn a provider response into durable domain
    records (such as the Evidence Steward) can retain the source artifacts.
    """
    call_kwargs = dict(kwargs or {})
    with direct_data_scope(invocation_path):
        request = begin_data_request(method, args, call_kwargs)
        attempt = request.start_attempt(vendor, fallback_chain=(vendor,))
        try:
            with request.attempt_scope(attempt):
                result = function(*args, **call_kwargs)
        except Exception as exc:
            request.fail(attempt, exc)
            raise
        request.succeed(attempt, result)
        origin = request.complete(normalize(result) if normalize is not None else result)
        return result, origin


def current_provenance_observer() -> Any | None:
    """Return the observer that must be attached to dynamically created LLMs."""
    return _CURRENT_PROVENANCE_OBSERVER.get()


def _relationship_payload(context) -> dict[str, Any]:
    return {
        "turn_id": context.turn_id,
        "graph_task_id": context.graph_task_id,
        "tool_call_id": context.tool_call_id,
        "invocation_path": context.invocation_path,
    }


def _duration_ms(started_at: float) -> int:
    return max(0, round((time.monotonic() - started_at) * 1000))


def _cache_key_sha256(cache_key: Any) -> str:
    safe = redact_recursive(cache_key).value
    content = json.dumps(safe, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _infer_period(
    method: str,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    if method in {"get_news", "get_stock_data"} and len(args) >= 3:
        return {"symbol": str(args[0]), "start": str(args[1]), "end": str(args[2])}
    if method == "get_global_news" and args:
        return {
            "as_of": str(args[0]),
            "look_back_days": kwargs.get("look_back_days", args[1] if len(args) > 1 else None),
        }
    if method == "get_indicators":
        return {
            "symbol": str(args[0]) if args else None,
            "indicator": str(args[1]) if len(args) > 1 else None,
            "as_of": str(args[2]) if len(args) > 2 else None,
            "look_back_days": args[3] if len(args) > 3 else None,
        }
    if method in {
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
    }:
        return {
            "symbol": str(args[0]) if args else None,
            "as_of": str(args[-1]) if len(args) > 1 else None,
        }
    return {"arguments_present": bool(args or kwargs)}
