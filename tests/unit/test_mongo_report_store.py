"""Tests for MongoReportStore (mocked pymongo).

All tests mock the pymongo Collection so no real MongoDB is needed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_col():
    """Return a MagicMock pymongo Collection."""
    return MagicMock()


@pytest.fixture
def mongo_store(mock_col):
    """Return a MongoReportStore with a mocked Collection."""
    with patch("tradingagents.portfolio.mongo_report_store.MongoClient") as mock_client_cls:
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_client_cls.return_value = mock_client

        from tradingagents.portfolio.mongo_report_store import MongoReportStore

        store = MongoReportStore(
            connection_string="mongodb://localhost:27017",
            db_name="test_db",
            run_id="test_run",
        )
        # Replace the internal collection with our mock
        store._col = mock_col
        return store


# ---------------------------------------------------------------------------
# save_scan / load_scan
# ---------------------------------------------------------------------------


def test_save_scan_inserts_document(mongo_store, mock_col):
    """save_scan should call insert_one with correct document shape."""
    mock_col.insert_one.return_value = MagicMock(inserted_id="abc123")

    mongo_store.save_scan("2026-03-20", {"watchlist": ["AAPL"]})

    mock_col.insert_one.assert_called_once()
    doc = mock_col.insert_one.call_args[0][0]
    assert doc["date"] == "2026-03-20"
    assert doc["report_type"] == "scan"
    assert doc["data"] == {"watchlist": ["AAPL"]}
    assert doc["run_id"] == "test_run"
    assert doc["ticker"] is None


def test_load_scan_finds_latest(mongo_store, mock_col):
    """load_scan should call find_one with date and report_type, sorted by created_at."""
    from pymongo import DESCENDING

    mock_col.find_one.return_value = {"data": {"watchlist": ["AAPL"]}}

    result = mongo_store.load_scan("2026-03-20")

    mock_col.find_one.assert_called_once()
    query = mock_col.find_one.call_args[0][0]
    assert query["date"] == "2026-03-20"
    assert query["report_type"] == "scan"
    assert result == {"watchlist": ["AAPL"]}


def test_load_scan_returns_none_when_missing(mongo_store, mock_col):
    """load_scan should return None when no document is found."""
    mock_col.find_one.return_value = None

    result = mongo_store.load_scan("1900-01-01")

    assert result is None


# ---------------------------------------------------------------------------
# save_analysis / load_analysis
# ---------------------------------------------------------------------------


def test_save_analysis_includes_ticker(mongo_store, mock_col):
    """save_analysis should include uppercase ticker in the document."""
    mock_col.insert_one.return_value = MagicMock(inserted_id="abc")

    mongo_store.save_analysis("2026-03-20", "aapl", {"score": 0.9})

    doc = mock_col.insert_one.call_args[0][0]
    assert doc["ticker"] == "AAPL"
    assert doc["report_type"] == "analysis"


def test_load_analysis_filters_by_ticker(mongo_store, mock_col):
    """load_analysis should filter by ticker in the query."""
    mock_col.find_one.return_value = {"data": {"score": 0.9}}

    result = mongo_store.load_analysis("2026-03-20", "AAPL")

    query = mock_col.find_one.call_args[0][0]
    assert query["ticker"] == "AAPL"
    assert result == {"score": 0.9}


# ---------------------------------------------------------------------------
# PM decision
# ---------------------------------------------------------------------------


def test_save_pm_decision_with_markdown(mongo_store, mock_col):
    """save_pm_decision should include markdown in the document."""
    mock_col.insert_one.return_value = MagicMock(inserted_id="abc")

    mongo_store.save_pm_decision(
        "2026-03-20", "pid-123", {"buys": []}, markdown="# Decision"
    )

    doc = mock_col.insert_one.call_args[0][0]
    assert doc["portfolio_id"] == "pid-123"
    assert doc["markdown"] == "# Decision"
    assert doc["report_type"] == "pm_decision"


def test_load_pm_decision_filters_by_portfolio(mongo_store, mock_col):
    """load_pm_decision should filter by portfolio_id."""
    mock_col.find_one.return_value = {"data": {"buys": []}}

    result = mongo_store.load_pm_decision("2026-03-20", "pid-123")

    query = mock_col.find_one.call_args[0][0]
    assert query["portfolio_id"] == "pid-123"
    assert result == {"buys": []}


# ---------------------------------------------------------------------------
# clear_portfolio_stage
# ---------------------------------------------------------------------------


def test_clear_portfolio_stage(mongo_store, mock_col):
    """clear_portfolio_stage should delete pm_decision and execution_result docs."""
    mock_col.delete_many.return_value = MagicMock(deleted_count=1)

    result = mongo_store.clear_portfolio_stage("2026-03-20", "pid-123")

    assert mock_col.delete_many.call_count == 2
    assert "pm_decision" in result
    assert "execution_result" in result


# ---------------------------------------------------------------------------
# list_analyses_for_date
# ---------------------------------------------------------------------------


def test_list_analyses_for_date(mongo_store, mock_col):
    """list_analyses_for_date should return unique ticker symbols."""
    mock_col.find.return_value = [
        {"ticker": "AAPL"},
        {"ticker": "MSFT"},
        {"ticker": "AAPL"},  # duplicate
    ]

    result = mongo_store.list_analyses_for_date("2026-03-20")

    assert set(result) == {"AAPL", "MSFT"}


# ---------------------------------------------------------------------------
# run_id property
# ---------------------------------------------------------------------------


def test_run_id_property(mongo_store):
    """run_id property should return the configured value."""
    assert mongo_store.run_id == "test_run"


# ---------------------------------------------------------------------------
# ensure_indexes
# ---------------------------------------------------------------------------


def test_ensure_indexes(mongo_store, mock_col):
    """ensure_indexes should create the expected indexes."""
    mongo_store.ensure_indexes()

    assert mock_col.create_index.call_count >= 4
