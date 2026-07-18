"""Strict backend lifecycle transition validation."""

from __future__ import annotations

from collections.abc import Mapping


class InvalidLifecycleTransition(ValueError):
    def __init__(self, lifecycle: str, previous: str, new: str):
        self.lifecycle = lifecycle
        self.previous = previous
        self.new = new
        super().__init__(f"invalid {lifecycle} transition: {previous} -> {new}")


RUN_TRANSITIONS = {
    "created": frozenset({"running"}),
    "running": frozenset({"completed", "failed", "cancel_requested", "interrupted"}),
    "cancel_requested": frozenset({"cancelled", "failed", "interrupted"}),
    "interrupted": frozenset({"running"}),
}

ROLE_TRANSITIONS = {
    "pending": frozenset({"running", "skipped", "not_reached"}),
    "running": frozenset({"completed", "failed", "cancelled", "interrupted"}),
    "completed": frozenset({"running"}),
    "interrupted": frozenset({"running"}),
}

TURN_TRANSITIONS = {
    "started": frozenset({"output_ready", "failed", "cancelled", "interrupted"}),
    "output_ready": frozenset({"completed", "failed", "cancelled", "interrupted"}),
    "interrupted": frozenset({"resumed"}),
    "resumed": frozenset({"output_ready", "failed", "cancelled", "interrupted"}),
}

MODEL_TRANSITIONS = {
    "started": frozenset({"completed", "failed", "interrupted"}),
}

LOGICAL_TOOL_TRANSITIONS = {
    "requested": frozenset({"committed", "cancelled"}),
}

TOOL_EXECUTION_TRANSITIONS = {
    "started": frozenset({"completed", "failed", "interrupted"}),
}

VENDOR_TRANSITIONS = {
    "progress": frozenset({"progress", "completed", "failed", "interrupted"}),
}

TRANSITIONS: Mapping[str, Mapping[str, frozenset[str]]] = {
    "run": RUN_TRANSITIONS,
    "role": ROLE_TRANSITIONS,
    "turn": TURN_TRANSITIONS,
    "model": MODEL_TRANSITIONS,
    "logical_tool": LOGICAL_TOOL_TRANSITIONS,
    "tool_execution": TOOL_EXECUTION_TRANSITIONS,
    "vendor": VENDOR_TRANSITIONS,
}


def validate_transition(lifecycle: str, previous: str, new: str) -> None:
    try:
        allowed = TRANSITIONS[lifecycle][previous]
    except KeyError as exc:
        raise InvalidLifecycleTransition(lifecycle, previous, new) from exc
    if new not in allowed:
        raise InvalidLifecycleTransition(lifecycle, previous, new)


def transition_is_valid(lifecycle: str, previous: str, new: str) -> bool:
    try:
        validate_transition(lifecycle, previous, new)
    except InvalidLifecycleTransition:
        return False
    return True

