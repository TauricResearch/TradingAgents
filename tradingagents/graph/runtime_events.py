"""Ephemeral, safe runtime markers for graph wrappers.

These markers deliberately never enter ``AgentState`` or a prompt.  They are
only delivered to an active durable observer, which persists the already
sanitised counts as scratchpad events.  This keeps operational recovery
auditable without retaining model-private working context.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

RuntimeEventType = Literal["tool_limit", "microcompact"]
RuntimeEventSink = Callable[[RuntimeEventType, str, dict[str, int]], None]

_runtime_event_sink: ContextVar[RuntimeEventSink | None] = ContextVar(
    "tradingagents_runtime_event_sink",
    default=None,
)


@contextmanager
def runtime_event_sink(sink: RuntimeEventSink) -> Iterator[None]:
    """Send safe wrapper events to ``sink`` for the current invocation only."""
    token = _runtime_event_sink.set(sink)
    try:
        yield
    finally:
        _runtime_event_sink.reset(token)


def record_runtime_event(
    event_type: RuntimeEventType,
    detail_code: str,
    *,
    metadata: dict[str, int],
) -> None:
    """Emit only numeric metadata when an observer installed a sink."""
    sink = _runtime_event_sink.get()
    if sink is not None:
        sink(event_type, detail_code, dict(metadata))
