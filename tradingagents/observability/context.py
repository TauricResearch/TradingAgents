"""ContextVar correlation carried across role, model, tool, and data calls."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RoleTurnRef:
    """Stable identity for one logical role turn across graph re-entries."""

    run_id: str
    actor_id: str
    node_id: str
    role_instance_id: str
    turn_id: str
    turn_index: int


@dataclass(frozen=True)
class ObservationContext:
    """Correlation for one concrete LangGraph task invocation."""

    run_id: str
    actor_id: str
    node_id: str
    role_instance_id: str
    turn_id: str
    graph_task_id: str
    graph_step: int
    invocation_path: str = "role"
    attempt_id: str | None = None
    tool_call_id: str | None = None


_CURRENT_OBSERVATION: ContextVar[ObservationContext | None] = ContextVar(
    "tradingagents_observation_context",
    default=None,
)


def current_observation_context(*, required: bool = False) -> ObservationContext | None:
    context = _CURRENT_OBSERVATION.get()
    if required and context is None:
        raise AssertionError("observation context is required")
    return context


@contextmanager
def observation_scope(context: ObservationContext) -> Iterator[ObservationContext]:
    token = _CURRENT_OBSERVATION.set(context)
    try:
        yield context
    finally:
        _CURRENT_OBSERVATION.reset(token)
