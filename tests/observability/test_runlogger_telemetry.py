"""Property-based tests for RunLogger event accumulation accuracy.

Feature: remaining-graph-hardening, Property 4: RunLogger event accumulation accuracy

Validates: Requirements 5.2, 5.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tradingagents.observability import RunLogger, _Event

# Strategy: generate lists of (tokens_in, tokens_out) tuples representing LLM call events
llm_event_tuples = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=100_000),
        st.integers(min_value=0, max_value=100_000),
    ),
    min_size=0,
    max_size=50,
)


@given(events=llm_event_tuples)
@settings(max_examples=100)
def test_runlogger_event_accumulation_accuracy(events: list[tuple[int, int]]) -> None:
    """Property 4: RunLogger event accumulation accuracy.

    Feature: remaining-graph-hardening, Property 4: RunLogger event accumulation accuracy

    For any sequence of N simulated LLM call events with known tokens_in/tokens_out,
    RunLogger.summary() reports llm_calls == N, tokens_in == sum(all tokens_in),
    tokens_out == sum(all tokens_out).

    **Validates: Requirements 5.2, 5.3**
    """
    logger = RunLogger()

    # Simulate N LLM call events by directly appending _Event objects
    for tokens_in, tokens_out in events:
        logger._append(
            _Event(
                kind="llm",
                ts=0,
                data={
                    "model": "test-model",
                    "agent": "test-agent",
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "duration_ms": 0,
                    "prompt": "",
                    "response": "",
                },
            )
        )

    summary = logger.summary()

    # Verify accumulation accuracy
    assert summary["llm_calls"] == len(events), (
        f"Expected llm_calls={len(events)}, got {summary['llm_calls']}"
    )
    assert summary["tokens_in"] == sum(t[0] for t in events), (
        f"Expected tokens_in={sum(t[0] for t in events)}, got {summary['tokens_in']}"
    )
    assert summary["tokens_out"] == sum(t[1] for t in events), (
        f"Expected tokens_out={sum(t[1] for t in events)}, got {summary['tokens_out']}"
    )
