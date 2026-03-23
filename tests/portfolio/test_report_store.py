"""Tests for tradingagents/portfolio/report_store.py.

Tests filesystem save/load operations for all report types.

All tests use a temporary directory (``tmp_reports`` fixture) and do not
require Supabase or network access.

Run::

    pytest tests/portfolio/test_report_store.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradingagents.portfolio.exceptions import ReportStoreError
from tradingagents.portfolio.report_store import ReportStore


# ---------------------------------------------------------------------------
# Macro scan
# ---------------------------------------------------------------------------


def test_save_and_load_scan(report_store, tmp_reports):
    """save_scan() then load_scan() must return the original data."""
    data = {"watchlist": ["AAPL", "MSFT"], "date": "2026-03-20"}
    path = report_store.save_scan("2026-03-20", data)
    assert path.exists()
    loaded = report_store.load_scan("2026-03-20")
    assert loaded == data


def test_load_scan_returns_none_for_missing_file(report_store):
    """load_scan() must return None when the file does not exist."""
    result = report_store.load_scan("1900-01-01")
    assert result is None


# ---------------------------------------------------------------------------
# Per-ticker analysis
# ---------------------------------------------------------------------------


def test_save_and_load_analysis(report_store):
    """save_analysis() then load_analysis() must return the original data."""
    data = {"ticker": "AAPL", "recommendation": "BUY", "score": 0.92}
    report_store.save_analysis("2026-03-20", "AAPL", data)
    loaded = report_store.load_analysis("2026-03-20", "AAPL")
    assert loaded == data


def test_analysis_ticker_stored_as_uppercase(report_store, tmp_reports):
    """Ticker symbol must be stored as uppercase in the directory path."""
    data = {"ticker": "aapl"}
    report_store.save_analysis("2026-03-20", "aapl", data)
    expected = tmp_reports / "daily" / "2026-03-20" / "AAPL" / "complete_report.json"
    assert expected.exists()
    # load with lowercase should still work
    loaded = report_store.load_analysis("2026-03-20", "aapl")
    assert loaded == data


# ---------------------------------------------------------------------------
# Holding reviews
# ---------------------------------------------------------------------------


def test_save_and_load_holding_review(report_store):
    """save_holding_review() then load_holding_review() must round-trip."""
    data = {"ticker": "MSFT", "verdict": "HOLD", "price_target": 420.0}
    report_store.save_holding_review("2026-03-20", "MSFT", data)
    loaded = report_store.load_holding_review("2026-03-20", "MSFT")
    assert loaded == data


def test_load_holding_review_returns_none_for_missing(report_store):
    """load_holding_review() must return None when the file does not exist."""
    result = report_store.load_holding_review("1900-01-01", "ZZZZ")
    assert result is None


# ---------------------------------------------------------------------------
# Risk metrics
# ---------------------------------------------------------------------------


def test_save_and_load_risk_metrics(report_store):
    """save_risk_metrics() then load_risk_metrics() must round-trip."""
    data = {"sharpe": 1.35, "sortino": 1.8, "max_drawdown": -0.12}
    report_store.save_risk_metrics("2026-03-20", "pid-123", data)
    loaded = report_store.load_risk_metrics("2026-03-20", "pid-123")
    assert loaded == data


# ---------------------------------------------------------------------------
# PM decisions
# ---------------------------------------------------------------------------


def test_save_and_load_pm_decision_json(report_store):
    """save_pm_decision() then load_pm_decision() must round-trip JSON."""
    decision = {"sells": [], "buys": [{"ticker": "AAPL", "shares": 10}]}
    report_store.save_pm_decision("2026-03-20", "pid-123", decision)
    loaded = report_store.load_pm_decision("2026-03-20", "pid-123")
    assert loaded == decision


def test_save_pm_decision_writes_markdown_when_provided(report_store, tmp_reports):
    """When markdown is passed to save_pm_decision(), .md file must be written."""
    decision = {"sells": [], "buys": []}
    md_text = "# Decision\n\nHold everything."
    report_store.save_pm_decision("2026-03-20", "pid-123", decision, markdown=md_text)
    md_path = tmp_reports / "daily" / "2026-03-20" / "portfolio" / "pid-123_pm_decision.md"
    assert md_path.exists()
    assert md_path.read_text(encoding="utf-8") == md_text


def test_save_pm_decision_no_markdown_file_when_not_provided(report_store, tmp_reports):
    """When markdown=None, no .md file should be written."""
    decision = {"sells": [], "buys": []}
    report_store.save_pm_decision("2026-03-20", "pid-123", decision, markdown=None)
    md_path = tmp_reports / "daily" / "2026-03-20" / "portfolio" / "pid-123_pm_decision.md"
    assert not md_path.exists()


def test_load_pm_decision_returns_none_for_missing(report_store):
    """load_pm_decision() must return None when the file does not exist."""
    result = report_store.load_pm_decision("1900-01-01", "pid-none")
    assert result is None


def test_list_pm_decisions(report_store):
    """list_pm_decisions() must return all saved decision paths, newest first."""
    dates = ["2026-03-18", "2026-03-19", "2026-03-20"]
    for d in dates:
        report_store.save_pm_decision(d, "pid-abc", {"date": d})
    paths = report_store.list_pm_decisions("pid-abc")
    assert len(paths) == 3
    # Sorted newest first by ISO date string ordering
    date_parts = [p.parent.parent.name for p in paths]
    assert date_parts == sorted(dates, reverse=True)


# ---------------------------------------------------------------------------
# Filesystem behaviour
# ---------------------------------------------------------------------------


def test_directories_created_on_write(report_store, tmp_reports):
    """Directories must be created automatically on first write."""
    target_dir = tmp_reports / "daily" / "2026-03-20" / "portfolio"
    assert not target_dir.exists()
    report_store.save_risk_metrics("2026-03-20", "pid-123", {"sharpe": 1.2})
    assert target_dir.is_dir()


def test_json_formatted_with_indent(report_store, tmp_reports):
    """Written JSON files must use indent=2 for human readability."""
    data = {"key": "value", "nested": {"a": 1}}
    path = report_store.save_scan("2026-03-20", data)
    raw = path.read_text(encoding="utf-8")
    # indent=2 means lines like '  "key": ...'
    assert '  "key"' in raw


def test_read_json_raises_on_corrupt_file(report_store, tmp_reports):
    """_read_json must raise ReportStoreError for corrupt JSON."""
    corrupt = tmp_reports / "corrupt.json"
    corrupt.write_text("not valid json{{{", encoding="utf-8")
    with pytest.raises(ReportStoreError):
        report_store._read_json(corrupt)


# ---------------------------------------------------------------------------
# _sanitize
# ---------------------------------------------------------------------------


class _FakeMessage:
    """Minimal stand-in for a LangChain HumanMessage / AIMessage."""

    def __init__(self, type_: str, content: str) -> None:
        self.type = type_
        self.content = content


class _FakeMessageWithDict(_FakeMessage):
    """Stand-in that also exposes a .dict() method like LangChain BaseMessage."""

    def dict(self) -> dict:
        return {"type": self.type, "content": self.content, "extra": "field"}


def test_sanitize_primitives_passthrough():
    """Primitive values must be returned unchanged."""
    assert ReportStore._sanitize(None) is None
    assert ReportStore._sanitize(True) is True
    assert ReportStore._sanitize(42) == 42
    assert ReportStore._sanitize(3.14) == 3.14
    assert ReportStore._sanitize("hello") == "hello"


def test_sanitize_plain_dict_passthrough():
    """A plain JSON-safe dict must survive _sanitize unchanged."""
    data = {"a": 1, "b": [2, 3], "c": {"d": "e"}}
    assert ReportStore._sanitize(data) == data


def test_sanitize_list_and_tuple():
    """Lists and tuples of primitives must be returned as lists."""
    assert ReportStore._sanitize([1, 2, 3]) == [1, 2, 3]
    assert ReportStore._sanitize((1, "x")) == [1, "x"]


def test_sanitize_message_without_dict_method():
    """A message-like object without .dict() must be converted to type/content."""
    msg = _FakeMessage("human", "hello world")
    result = ReportStore._sanitize(msg)
    assert result == {"type": "human", "content": "hello world"}


def test_sanitize_message_with_dict_method():
    """A message-like object with .dict() must be sanitized via that dict."""
    msg = _FakeMessageWithDict("ai", "response text")
    result = ReportStore._sanitize(msg)
    assert result == {"type": "ai", "content": "response text", "extra": "field"}


def test_sanitize_nested_messages_in_state():
    """Messages nested inside a LangGraph-style state dict must be sanitized."""
    msg = _FakeMessage("human", "buy signal")
    state = {
        "messages": [msg],
        "investment_debate_state": {"history": [msg]},
        "ticker": "AAPL",
    }
    result = ReportStore._sanitize(state)
    assert result["ticker"] == "AAPL"
    assert result["messages"] == [{"type": "human", "content": "buy signal"}]
    debate = result["investment_debate_state"]["history"]
    assert debate == [{"type": "human", "content": "buy signal"}]


def test_sanitize_arbitrary_non_serializable_falls_back_to_str():
    """An arbitrary non-serializable object must fall back to str()."""

    class _Weird:
        def __str__(self) -> str:
            return "weird_value"

    result = ReportStore._sanitize(_Weird())
    assert result == "weird_value"


def test_write_json_with_message_objects_does_not_raise(report_store, tmp_reports):
    """_write_json must not raise when data contains message-like objects."""
    msg = _FakeMessage("human", "test")
    data = {"messages": [msg], "ticker": "TSLA"}
    path = tmp_reports / "test_output.json"
    written = report_store._write_json(path, data)
    assert written.exists()
    loaded = json.loads(written.read_text(encoding="utf-8"))
    assert loaded["ticker"] == "TSLA"
    assert loaded["messages"] == [{"type": "human", "content": "test"}]
