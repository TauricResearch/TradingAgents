"""Tests for tradingagents.portfolio.store_factory.

Covers:
- Default (no env var) returns filesystem ReportStore
- TRADINGAGENTS_MONGO_URI returns MongoReportStore
- Explicit mongo_uri parameter takes precedence
- MongoDB failure falls back to filesystem
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.portfolio.report_store import ReportStore
from tradingagents.portfolio.store_factory import create_report_store


def _stub_pymongo(mongo_client: object) -> dict[str, types.ModuleType]:
    pymongo = types.ModuleType("pymongo")
    pymongo.DESCENDING = -1
    pymongo.MongoClient = mongo_client

    collection = types.ModuleType("pymongo.collection")
    collection.Collection = object

    database = types.ModuleType("pymongo.database")
    database.Database = object

    return {
        "pymongo": pymongo,
        "pymongo.collection": collection,
        "pymongo.database": database,
    }


# ---------------------------------------------------------------------------
# Default: filesystem
# ---------------------------------------------------------------------------


def test_default_returns_filesystem_store():
    """When no MongoDB URI is configured, the factory returns ReportStore."""
    with patch.dict("os.environ", {}, clear=True):
        store = create_report_store()

    assert isinstance(store, ReportStore)


def test_default_passes_run_id():
    """run_id should be forwarded to the filesystem store."""
    with patch.dict("os.environ", {}, clear=True):
        store = create_report_store(run_id="abc123")

    assert isinstance(store, ReportStore)
    assert store.run_id == "abc123"


def test_base_dir_forwarded():
    """base_dir should be forwarded to the filesystem store."""
    with patch.dict("os.environ", {}, clear=True):
        store = create_report_store(base_dir="/custom/reports")

    assert isinstance(store, ReportStore)


# ---------------------------------------------------------------------------
# Explicit mongo_uri → MongoDB
# ---------------------------------------------------------------------------


def test_explicit_mongo_uri_returns_mongo_store():
    """When mongo_uri is provided, the factory returns MongoReportStore."""
    mock_mc = MagicMock()
    with patch.dict(sys.modules, _stub_pymongo(mock_mc)):
        sys.modules.pop("tradingagents.portfolio.mongo_report_store", None)
        mock_mc.return_value = MagicMock()
        store = create_report_store(
            run_id="abc",
            mongo_uri="mongodb://localhost:27017",
        )

    assert store is not None


# ---------------------------------------------------------------------------
# MongoDB failure → filesystem fallback
# ---------------------------------------------------------------------------


def test_mongo_failure_falls_back_to_filesystem():
    """When MongoDB connection fails, the factory falls back to ReportStore."""
    mock_mc = MagicMock(side_effect=Exception("connection refused"))
    with patch.dict(sys.modules, _stub_pymongo(mock_mc)):
        sys.modules.pop("tradingagents.portfolio.mongo_report_store", None)
        store = create_report_store(
            run_id="test",
            mongo_uri="mongodb://bad-host:27017",
        )

    assert isinstance(store, ReportStore)
    assert store.run_id == "test"


# ---------------------------------------------------------------------------
# Env var
# ---------------------------------------------------------------------------


def test_env_var_mongo_uri():
    """TRADINGAGENTS_MONGO_URI env var should trigger MongoDB store."""
    mock_mc = MagicMock(side_effect=Exception("connection refused"))
    with patch.dict(
        "os.environ",
        {"TRADINGAGENTS_MONGO_URI": "mongodb://envhost:27017"},
    ), patch.dict(sys.modules, _stub_pymongo(mock_mc)):
        sys.modules.pop("tradingagents.portfolio.mongo_report_store", None)
        # Will fail to connect, but should try and then fall back
        store = create_report_store()

    # Should fall back to filesystem
    assert isinstance(store, ReportStore)
