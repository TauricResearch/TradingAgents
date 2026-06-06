"""Tests for fundamentals ingestion and its use in the brain context."""

from __future__ import annotations

import pytest

from tradingagents.brain.context import fundamentals_context
from tradingagents.ingestion import ingest_fundamentals
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'fund.db'}")
    yield
    reset_engine()


class FakeFund:
    def fetch(self, symbol):
        return {"pe_trailing": 28.5, "pb": 12.0, "roe": 0.35}


def test_ingest_and_latest_fundamentals(db):
    with database.get_session() as s:
        ingest_fundamentals(s, "AAPL", fetcher=FakeFund())
    with database.get_session() as s:
        snap = repo.latest_fundamentals(s, "AAPL")
        assert snap is not None and snap.metrics["pe_trailing"] == 28.5


def test_fundamentals_context(db):
    with database.get_session() as s:
        ingest_fundamentals(s, "AAPL", fetcher=FakeFund())
    with database.get_session() as s:
        ctx = fundamentals_context(s, "AAPL")
        assert "pe_trailing" in ctx and "roe" in ctx


def test_fundamentals_context_empty(db):
    with database.get_session() as s:
        assert "(no fundamentals in DB)" in fundamentals_context(s, "AAPL")
