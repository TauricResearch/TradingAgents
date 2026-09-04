"""Memory-log lessons must be point-in-time safe in a backtest (#1251).

get_past_context previously returned every resolved lesson regardless of the run
date, so a historical run could learn from an outcome that had not happened yet.
Resolved entries now record the date their outcome became known (``resolved:``),
and get_past_context(as_of=...) filters on it. Legacy entries without a
resolution date are excluded from a point-in-time query (conservative migration).
"""
from __future__ import annotations

import pytest

from tradingagents.agents.utils.memory import TradingMemoryLog


def _log(tmp_path):
    return TradingMemoryLog({"memory_log_path": str(tmp_path / "mem.md")})


def _resolve(log, ticker, date, resolution_date, reflection):
    log.store_decision(ticker, date, f"Rating: Buy\n{reflection}")
    log.update_with_outcome(
        ticker, date, 0.05, 0.02, 5, reflection, resolution_date=resolution_date,
    )


@pytest.mark.unit
def test_resolution_date_is_stored_and_parsed(tmp_path):
    log = _log(tmp_path)
    _resolve(log, "NVDA", "2026-01-05", "2026-01-10", "outcome known 01-10")
    entry = log.load_entries()[0]
    assert entry["resolved"] == "2026-01-10"
    assert "resolved:2026-01-10" in (tmp_path / "mem.md").read_text()


@pytest.mark.unit
def test_as_of_excludes_lessons_resolved_after_the_run_date(tmp_path):
    log = _log(tmp_path)
    # Decision on 01-05, outcome only known on 01-10.
    _resolve(log, "NVDA", "2026-01-05", "2026-01-10", "great trade")

    # A run as-of 01-07 must NOT see it (the outcome was still in the future).
    assert log.get_past_context("NVDA", as_of="2026-01-07") == ""
    # A run as-of 01-10 (and later) sees it.
    assert "great trade" in log.get_past_context("NVDA", as_of="2026-01-10")
    assert "great trade" in log.get_past_context("NVDA", as_of="2026-02-01")


@pytest.mark.unit
def test_no_as_of_is_unfiltered_live_behavior(tmp_path):
    log = _log(tmp_path)
    _resolve(log, "NVDA", "2026-01-05", "2026-01-10", "great trade")
    # Live run (no as_of): unchanged behavior, lesson is shown.
    assert "great trade" in log.get_past_context("NVDA")


@pytest.mark.unit
def test_legacy_entry_without_resolution_date_excluded_in_backtest(tmp_path):
    log = _log(tmp_path)
    # Simulate a pre-migration resolved entry: no resolution_date recorded.
    log.store_decision("NVDA", "2026-01-05", "Rating: Buy\nlegacy lesson")
    log.update_with_outcome("NVDA", "2026-01-05", 0.05, 0.02, 5, "legacy lesson")
    entry = log.load_entries()[0]
    assert entry["resolved"] is None

    # Conservative: excluded from a point-in-time query (can't prove it was known)...
    assert log.get_past_context("NVDA", as_of="2026-06-01") == ""
    # ...but still available on a live (unfiltered) run.
    assert "legacy lesson" in log.get_past_context("NVDA")


@pytest.mark.unit
def test_cross_ticker_lessons_are_also_gated(tmp_path):
    log = _log(tmp_path)
    _resolve(log, "AAPL", "2026-01-05", "2026-01-10", "cross lesson")
    # Querying a different ticker as-of before resolution: no cross lesson leaks.
    assert log.get_past_context("NVDA", as_of="2026-01-07") == ""
    assert "cross lesson" in log.get_past_context("NVDA", as_of="2026-01-10")


@pytest.mark.unit
def test_memory_as_of_gates_historical_but_not_live():
    # The graph filters only for a past trade date; a current-date run passes
    # None so live behavior and legacy entries are unaffected (#1251).
    from datetime import datetime, timedelta

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    g = object.__new__(TradingAgentsGraph)
    past = "2024-01-01"
    today = datetime.now().strftime("%Y-%m-%d")
    future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    assert g._memory_as_of(past) == past       # backtest -> filter on the trade date
    assert g._memory_as_of(today) is None      # live -> no filter
    assert g._memory_as_of(future) is None     # future-dated run -> no filter
