import pytest

from tradingagents.observability.lifecycle import (
    TRANSITIONS,
    InvalidLifecycleTransition,
    transition_is_valid,
    validate_transition,
)


pytestmark = pytest.mark.unit


EXPECTED_TRANSITIONS = {
    "run": {
        ("created", "running"),
        ("running", "completed"),
        ("running", "failed"),
        ("running", "cancel_requested"),
        ("running", "interrupted"),
        ("cancel_requested", "cancelled"),
        ("cancel_requested", "failed"),
        ("cancel_requested", "interrupted"),
        ("interrupted", "running"),
    },
    "role": {
        ("pending", "running"),
        ("pending", "skipped"),
        ("pending", "not_reached"),
        ("running", "completed"),
        ("running", "failed"),
        ("running", "cancelled"),
        ("running", "interrupted"),
        ("completed", "running"),
        ("interrupted", "running"),
    },
    "turn": {
        ("started", "output_ready"),
        ("started", "failed"),
        ("started", "cancelled"),
        ("started", "interrupted"),
        ("output_ready", "completed"),
        ("output_ready", "failed"),
        ("output_ready", "cancelled"),
        ("output_ready", "interrupted"),
        ("interrupted", "resumed"),
        ("resumed", "output_ready"),
        ("resumed", "failed"),
        ("resumed", "cancelled"),
        ("resumed", "interrupted"),
    },
    "model": {
        ("started", "completed"),
        ("started", "failed"),
        ("started", "interrupted"),
    },
    "logical_tool": {
        ("requested", "committed"),
        ("requested", "cancelled"),
    },
    "tool_execution": {
        ("started", "completed"),
        ("started", "failed"),
        ("started", "interrupted"),
    },
    "vendor": {
        ("progress", "progress"),
        ("progress", "completed"),
        ("progress", "failed"),
        ("progress", "interrupted"),
    },
}


def test_every_approved_transition_is_encoded_exactly():
    actual = {
        lifecycle: {
            (previous, new)
            for previous, allowed in transitions.items()
            for new in allowed
        }
        for lifecycle, transitions in TRANSITIONS.items()
    }

    assert actual == EXPECTED_TRANSITIONS
    for lifecycle, transitions in EXPECTED_TRANSITIONS.items():
        for previous, new in transitions:
            validate_transition(lifecycle, previous, new)
            assert transition_is_valid(lifecycle, previous, new) is True


@pytest.mark.parametrize(
    ("lifecycle", "previous", "new"),
    [
        ("run", "completed", "running"),
        ("run", "created", "failed"),
        ("role", "skipped", "running"),
        ("role", "pending", "completed"),
        ("turn", "started", "completed"),
        ("turn", "interrupted", "output_ready"),
        ("model", "completed", "started"),
        ("logical_tool", "committed", "cancelled"),
        ("tool_execution", "completed", "started"),
        ("vendor", "completed", "progress"),
        ("unknown", "started", "completed"),
    ],
)
def test_illegal_transitions_are_rejected(lifecycle, previous, new):
    with pytest.raises(InvalidLifecycleTransition) as exc_info:
        validate_transition(lifecycle, previous, new)

    assert exc_info.value.lifecycle == lifecycle
    assert transition_is_valid(lifecycle, previous, new) is False

