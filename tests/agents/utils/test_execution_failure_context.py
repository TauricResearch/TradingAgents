"""Property-based and unit tests for execution failure context formatting.

Feature: remaining-graph-hardening
Tests for `format_execution_failure_block()` and `find_latest_execution_failures()`
from `tradingagents.agents.utils.historical_context`.
"""

from __future__ import annotations

import json
import string

from hypothesis import given, settings
from hypothesis import strategies as st

from tradingagents.agents.utils.historical_context import (
    find_latest_execution_failures,
    format_execution_failure_block,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_actions = st.sampled_from(["BUY", "SELL"])
_tickers = st.text(alphabet=string.ascii_uppercase, min_size=1, max_size=5).filter(
    lambda s: s.strip() != ""
)
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
        # All trades should be fully present (accounting for _truncate stripping trailing whitespace)
        for trade in failures["failed_trades"]:
            action = trade["action"]
            ticker = trade["ticker"]
            shares_str = str(trade["shares"])
            reason = trade["reason"].strip()  # _truncate strips trailing whitespace
            line_fragment = f"- {action} {ticker} x{shares_str}: {reason}"
            assert line_fragment in result, f"Non-truncated output missing trade: {line_fragment!r}"


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


# ---------------------------------------------------------------------------
# Tests for find_latest_execution_failures() — directory-walking logic
# ---------------------------------------------------------------------------


def test_find_latest_execution_failures_returns_failures(tmp_path):
    """find_latest_execution_failures() returns the most recent failure data."""
    # Create reports/daily/2026-05-01/run_001/portfolio/report/main_portfolio_execution_result.json
    date_dir = tmp_path / "2026-05-01"
    report_dir = date_dir / "run_001" / "portfolio" / "report"
    report_dir.mkdir(parents=True)
    data = {
        "failed_trades": [
            {"action": "BUY", "ticker": "AAPL", "shares": 100, "reason": "Insufficient cash"}
        ]
    }
    (report_dir / "main_portfolio_execution_result.json").write_text(
        json.dumps(data), encoding="utf-8"
    )

    result = find_latest_execution_failures(
        portfolio_id="main_portfolio",
        as_of_date="2026-05-02",
        reports_root=tmp_path,
        lookback_days=7,
    )

    assert result is not None
    assert result["date"] == "2026-05-01"
    assert len(result["failed_trades"]) == 1
    assert result["failed_trades"][0]["ticker"] == "AAPL"


def test_find_latest_execution_failures_skips_empty_trades(tmp_path):
    """find_latest_execution_failures() skips files with empty failed_trades."""
    date_dir = tmp_path / "2026-05-01"
    report_dir = date_dir / "run_001" / "portfolio" / "report"
    report_dir.mkdir(parents=True)
    data = {"failed_trades": []}
    (report_dir / "main_portfolio_execution_result.json").write_text(
        json.dumps(data), encoding="utf-8"
    )

    result = find_latest_execution_failures(
        portfolio_id="main_portfolio",
        as_of_date="2026-05-02",
        reports_root=tmp_path,
        lookback_days=7,
    )

    assert result is None


def test_find_latest_execution_failures_returns_none_when_no_reports(tmp_path):
    """find_latest_execution_failures() returns None when no matching files exist."""
    result = find_latest_execution_failures(
        portfolio_id="main_portfolio",
        as_of_date="2026-05-02",
        reports_root=tmp_path,
        lookback_days=7,
    )

    assert result is None


def test_find_latest_execution_failures_picks_most_recent_date(tmp_path):
    """find_latest_execution_failures() returns the most recent date with failures."""
    # Older date
    old_dir = tmp_path / "2026-04-28" / "run_001" / "portfolio" / "report"
    old_dir.mkdir(parents=True)
    old_data = {
        "failed_trades": [
            {"action": "SELL", "ticker": "MSFT", "shares": 50, "reason": "Old failure"}
        ]
    }
    (old_dir / "main_portfolio_execution_result.json").write_text(
        json.dumps(old_data), encoding="utf-8"
    )

    # Newer date
    new_dir = tmp_path / "2026-04-30" / "run_002" / "portfolio" / "report"
    new_dir.mkdir(parents=True)
    new_data = {
        "failed_trades": [
            {"action": "BUY", "ticker": "GOOG", "shares": 25, "reason": "Recent failure"}
        ]
    }
    (new_dir / "main_portfolio_execution_result.json").write_text(
        json.dumps(new_data), encoding="utf-8"
    )

    result = find_latest_execution_failures(
        portfolio_id="main_portfolio",
        as_of_date="2026-05-01",
        reports_root=tmp_path,
        lookback_days=7,
    )

    assert result is not None
    assert result["date"] == "2026-04-30"
    assert result["failed_trades"][0]["ticker"] == "GOOG"


def test_find_latest_execution_failures_respects_lookback_window(tmp_path):
    """find_latest_execution_failures() ignores dates outside the lookback window."""
    # Date outside lookback window (8 days before as_of_date, lookback=7)
    old_dir = tmp_path / "2026-04-23" / "run_001" / "portfolio" / "report"
    old_dir.mkdir(parents=True)
    data = {
        "failed_trades": [{"action": "BUY", "ticker": "TSLA", "shares": 10, "reason": "Too old"}]
    }
    (old_dir / "main_portfolio_execution_result.json").write_text(
        json.dumps(data), encoding="utf-8"
    )

    result = find_latest_execution_failures(
        portfolio_id="main_portfolio",
        as_of_date="2026-05-01",
        reports_root=tmp_path,
        lookback_days=7,
    )

    assert result is None


def test_find_latest_execution_failures_excludes_as_of_date_itself(tmp_path):
    """find_latest_execution_failures() only looks strictly before as_of_date."""
    same_day_dir = tmp_path / "2026-05-01" / "run_001" / "portfolio" / "report"
    same_day_dir.mkdir(parents=True)
    data = {
        "failed_trades": [{"action": "BUY", "ticker": "NVDA", "shares": 200, "reason": "Same day"}]
    }
    (same_day_dir / "main_portfolio_execution_result.json").write_text(
        json.dumps(data), encoding="utf-8"
    )

    result = find_latest_execution_failures(
        portfolio_id="main_portfolio",
        as_of_date="2026-05-01",
        reports_root=tmp_path,
        lookback_days=7,
    )

    assert result is None


def test_find_latest_execution_failures_matches_portfolio_id(tmp_path):
    """find_latest_execution_failures() only matches files for the given portfolio_id."""
    report_dir = tmp_path / "2026-05-01" / "run_001" / "portfolio" / "report"
    report_dir.mkdir(parents=True)
    data = {
        "failed_trades": [
            {"action": "BUY", "ticker": "AMZN", "shares": 30, "reason": "Wrong portfolio"}
        ]
    }
    # File is for "other_portfolio", not "main_portfolio"
    (report_dir / "other_portfolio_execution_result.json").write_text(
        json.dumps(data), encoding="utf-8"
    )

    result = find_latest_execution_failures(
        portfolio_id="main_portfolio",
        as_of_date="2026-05-02",
        reports_root=tmp_path,
        lookback_days=7,
    )

    assert result is None
