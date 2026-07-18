"""Lightweight progress events for data vendor calls."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True)
class DataProgressEvent:
    stage: str
    method: str
    vendor: str
    message: str
    run_id: str | None = None
    turn_id: str | None = None
    graph_task_id: str | None = None
    tool_call_id: str | None = None
    vendor_call_id: str | None = None
    artifact_id: str | None = None


ProgressSink = Callable[[DataProgressEvent], None]
_progress_sink: ProgressSink | None = None


def set_progress_sink(sink: ProgressSink | None) -> None:
    global _progress_sink
    _progress_sink = sink


def emit_progress(
    stage: str,
    method: str,
    vendor: str,
    message: str,
    *,
    vendor_call_id: str | None = None,
    artifact_id: str | None = None,
) -> None:
    if _progress_sink is None:
        return
    try:
        from tradingagents.observability.provenance import current_progress_correlation

        correlation = current_progress_correlation()
        if vendor_call_id is not None:
            correlation["vendor_call_id"] = vendor_call_id
        if artifact_id is not None:
            correlation["artifact_id"] = artifact_id
        _progress_sink(
            DataProgressEvent(
                stage=stage,
                method=method,
                vendor=vendor,
                message=message,
                **correlation,
            )
        )
    except Exception:
        return


@contextmanager
def capture_progress() -> Iterator[list[DataProgressEvent]]:
    events: list[DataProgressEvent] = []
    previous = _progress_sink
    set_progress_sink(events.append)
    try:
        yield events
    finally:
        set_progress_sink(previous)


@contextmanager
def progress_sink(sink: ProgressSink | None) -> Iterator[None]:
    previous = _progress_sink
    set_progress_sink(sink)
    try:
        yield
    finally:
        set_progress_sink(previous)
