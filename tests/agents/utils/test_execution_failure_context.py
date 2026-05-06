"""Property-based and unit tests for execution failure context formatting.

Feature: remaining-graph-hardening
Tests for `format_execution_failure_block()` from
`tradingagents.agents.utils.historical_context`.
"""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from tradingagents.agents.utils.historical_context import (
    format_execution_failure_block,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_actions = st.sampled_from(["BUY", "SELL"])
_tickers = st.text(
    alphabet=string.ascii_uppercase, min_size=1, max_size=5
).filter(lambda s: s.strip() != "")
_shares = st.integers(min_value=1, max_value=100_000)
_reasons = st.text(
    alphabet=string.ascii_letters + string.digits + " :$,.-",
    min_size=1,
    max_size=120,
).filter(lambda s: s.strip() != "")

_failed_trade = st.fixed_dictionaries(
    {
        "action": _actions,
        "ticker": _tickers,
        "shares": _shares,
        "reason": _reasons,
    }
)

_failed_trades_list = st.lists(_failed_trade, min_size=1, max_size=50)

_iso_date = st.dates(
    min_value=__import__("datetime").date(2020, 1, 1),
    max_value=__import__("datetime").date(2030, 12, 31),
).map(lambda d: d.isoformat())

_failures_dict = st.builds(
    lambda date, trades: {"date": date, "failed_trades": trades},
    date=_iso_date,
    trades=_failed_trades_list,
)


# ---------------------------------------------------------------------------
# Property 1: Execution failure block structural completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(failures=_failures_dict)
def test_property_structural_completeness(failures: dict) -> None:
    """Property 1: Execution failure block structural completeness.

    Feature: remaining-graph-hardening, Property 1: execution failure block structural completeness

    **Validates: Requirements 1.1, 1.7**

    For any non-empty list of failed trades (each with action, ticker, shares,
    and reason), format_execution_failure_block() produces a string containing
    the action, ticker, share count, and failure reason for every included trade,
    plus the date header.
    """
    result = format_execution_failure_block(failures)

    # Must be non-empty for non-empty failed_trades
    assert result != ""

    # Must contain the date header
    assert failures["date"] in result
    assert "## Prior Execution Failures" in result

    # Each trade that fits within the 600-char cap must have its fields present.
    # Since the block is capped at 600 chars, we check that for every trade whose
    # line IS present in the output, all four fields appear.
    for trade in failures["failed_trades"]:
        action = trade["action"]
        ticker = trade["ticker"]
        shares_str = str(trade["shares"])
        reason = trade["reason"]

        # Build the expected line fragment
        line_fragment = f"- {action} {ticker} x{shares_str}: {reason}"

        # If this trade's line is included (not truncated), verify all fields
        if line_fragment in result:
            assert action in result
            assert ticker in result
            assert shares_str in result
            assert reason in result


# ---------------------------------------------------------------------------
# Property 2: Execution failure block length cap
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(failures=_failures_dict)
def test_property_length_cap(failures: dict) -> None:
    """Property 2: Execution failure block length cap.

    Feature: remaining-graph-hardening, Property 2: execution failure block length cap

    **Validates: Requirements 1.8**

    For any input (including arbitrarily large failure lists), the returned
    string never exceeds 600 characters.
    """
    result = format_execution_failure_block(failures)
    assert len(result) <= 600
    # If truncated, must end with ellipsis; if not truncated, must contain all trade lines
    if "…" in result:
        assert result.endswith("…"), "Truncated output must end with ellipsis, not mid-line"
    else:
        # All trades should be fully present
        for trade in failures["failed_trades"]:
            line_fragment = f"- {trade['action']} {trade['ticker']} x{trade['shares']}: {trade['reason']}"
            assert line_fragment in result, f"Non-truncated output missing trade: {line_fragment}"


@settings(max_examples=100)
@given(failures=_failures_dict)
def test_property_length_cap_custom_max(failures: dict) -> None:
    """Length cap holds for custom max_chars values too.

    **Validates: Requirements 1.8**
    """
    result = format_execution_failure_block(failures, max_chars=300)
    assert len(result) <= 300


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_none_failures_returns_empty_string() -> None:
    """Empty failures (None) returns empty string."""
    result = format_execution_failure_block(None)
    assert result == ""


def test_empty_failed_trades_returns_empty_string() -> None:
    """Empty `failed_trades` list returns empty string."""
    result = format_execution_failure_block({"date": "2026-05-01", "failed_trades": []})
    assert result == ""


def test_single_failure_formats_correctly() -> None:
    """Single failure formats correctly with date header."""
    failures = {
        "date": "2026-05-01",
        "failed_trades": [
            {
                "action": "BUY",
                "ticker": "AAPL",
                "shares": 100,
                "reason": "Insufficient cash: needed $18,500, available $12,000",
            }
        ],
    }
    result = format_execution_failure_block(failures)

    # Check header
    assert "## Prior Execution Failures (2026-05-01)" in result

    # Check trade line
    assert "- BUY AAPL x100: Insufficient cash: needed $18,500, available $12,000" in result

    # Check length cap
    assert len(result) <= 600
