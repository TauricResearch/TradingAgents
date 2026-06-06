"""Tests for macro ingestion (DB-first) and its use in the Market context."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.brain.context import market_context
from tradingagents.ingestion import ingest_macro
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'macro.db'}")
    yield
    reset_engine()


class FakeMacro:
    def __init__(self, points):
        self._points = points

    def fetch(self, series_id, start, end):
        return list(self._points)


def _points():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        {"ts": base, "value": 3.0},
        {"ts": base + timedelta(days=30), "value": 3.2},
    ]


def test_ingest_macro_and_dedup(db):
    fetcher = FakeMacro(_points())
    with database.get_session() as s:
        r1 = ingest_macro(s, "FEDFUNDS", fetcher=fetcher)
        assert r1.inserted == 2 and r1.skipped == 0
    with database.get_session() as s:
        r2 = ingest_macro(s, "FEDFUNDS", fetcher=fetcher)
        assert r2.inserted == 0 and r2.skipped == 2
    with database.get_session() as s:
        assert repo.latest_macro(s, "FEDFUNDS").value == 3.2


def test_market_context_includes_macro(db):
    with database.get_session() as s:
        ingest_macro(s, "FEDFUNDS", fetcher=FakeMacro(_points()))
    with database.get_session() as s:
        ctx = market_context(s, "AAPL")
        assert "FEDFUNDS" in ctx and "3.2" in ctx
