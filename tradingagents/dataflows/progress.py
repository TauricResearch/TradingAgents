"""Lightweight progress events for data vendor calls."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator


@dataclass(frozen=True)
class DataProgressEvent:
    stage: str
    method: str
    vendor: str
    message: str


ProgressSink = Callable[[DataProgressEvent], None]
_progress_sink: ProgressSink | None = None


def set_progress_sink(sink: ProgressSink | None) -> None:
    global _progress_sink
    _progress_sink = sink


def emit_progress(stage: str, method: str, vendor: str, message: str) -> None:
    if _progress_sink is None:
        return
    try:
        _progress_sink(DataProgressEvent(stage=stage, method=method, vendor=vendor, message=message))
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
