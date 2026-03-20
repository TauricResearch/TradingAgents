"""Tests for tradingagents/portfolio/report_store.py.

Tests filesystem save/load operations for all report types.

All tests use a temporary directory (``tmp_reports`` fixture) and do not
require Supabase or network access.

Run::

    pytest tests/portfolio/test_report_store.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Macro scan
# ---------------------------------------------------------------------------


def test_save_and_load_scan(report_store, tmp_reports):
    """save_scan() then load_scan() must return the original data."""
    # TODO: implement
    # data = {"watchlist": ["AAPL", "MSFT"], "date": "2026-03-20"}
    # path = report_store.save_scan("2026-03-20", data)
    # assert path.exists()
    # loaded = report_store.load_scan("2026-03-20")
    # assert loaded == data
    raise NotImplementedError


def test_load_scan_returns_none_for_missing_file(report_store):
    """load_scan() must return None when the file does not exist."""
    # TODO: implement
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Per-ticker analysis
# ---------------------------------------------------------------------------


def test_save_and_load_analysis(report_store):
    """save_analysis() then load_analysis() must return the original data."""
    # TODO: implement
    raise NotImplementedError


def test_analysis_ticker_stored_as_uppercase(report_store, tmp_reports):
    """Ticker symbol must be stored as uppercase in the directory path."""
    # TODO: implement
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Holding reviews
# ---------------------------------------------------------------------------


def test_save_and_load_holding_review(report_store):
    """save_holding_review() then load_holding_review() must round-trip."""
    # TODO: implement
    raise NotImplementedError


def test_load_holding_review_returns_none_for_missing(report_store):
    """load_holding_review() must return None when the file does not exist."""
    # TODO: implement
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Risk metrics
# ---------------------------------------------------------------------------


def test_save_and_load_risk_metrics(report_store):
    """save_risk_metrics() then load_risk_metrics() must round-trip."""
    # TODO: implement
    raise NotImplementedError


# ---------------------------------------------------------------------------
# PM decisions
# ---------------------------------------------------------------------------


def test_save_and_load_pm_decision_json(report_store):
    """save_pm_decision() then load_pm_decision() must round-trip JSON."""
    # TODO: implement
    # decision = {"sells": [], "buys": [{"ticker": "AAPL", "shares": 10}]}
    # report_store.save_pm_decision("2026-03-20", "pid-123", decision)
    # loaded = report_store.load_pm_decision("2026-03-20", "pid-123")
    # assert loaded == decision
    raise NotImplementedError


def test_save_pm_decision_writes_markdown_when_provided(report_store, tmp_reports):
    """When markdown is passed to save_pm_decision(), .md file must be written."""
    # TODO: implement
    raise NotImplementedError


def test_save_pm_decision_no_markdown_file_when_not_provided(report_store, tmp_reports):
    """When markdown=None, no .md file should be written."""
    # TODO: implement
    raise NotImplementedError


def test_load_pm_decision_returns_none_for_missing(report_store):
    """load_pm_decision() must return None when the file does not exist."""
    # TODO: implement
    raise NotImplementedError


def test_list_pm_decisions(report_store):
    """list_pm_decisions() must return all saved decision paths, newest first."""
    # TODO: implement
    # Save decisions for multiple dates, verify order
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Filesystem behaviour
# ---------------------------------------------------------------------------


def test_directories_created_on_write(report_store, tmp_reports):
    """Directories must be created automatically on first write."""
    # TODO: implement
    # assert not (tmp_reports / "daily" / "2026-03-20" / "portfolio").exists()
    # report_store.save_risk_metrics("2026-03-20", "pid-123", {"sharpe": 1.2})
    # assert (tmp_reports / "daily" / "2026-03-20" / "portfolio").is_dir()
    raise NotImplementedError


def test_json_formatted_with_indent(report_store, tmp_reports):
    """Written JSON files must use indent=2 for human readability."""
    # TODO: implement
    # Write a file, read the raw bytes, verify indentation
    raise NotImplementedError
