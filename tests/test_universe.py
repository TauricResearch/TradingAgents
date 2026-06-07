"""Tests for the universe / watchlist / ticker-event storage helpers (Fase 1)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'universe.db'}")
    yield
    reset_engine()


def test_bulk_upsert_and_list_universe(db):
    with database.get_session() as s:
        repo.bulk_upsert_instruments(s, [
            {"symbol": "AAPL", "tradable": True, "active": True, "is_sp500": True, "asset_class": "us_equity"},
            {"symbol": "MSFT", "tradable": True, "active": True, "is_sp500": True},
            {"symbol": "OTC1", "tradable": False, "active": True},
        ])
    with database.get_session() as s:
        assert repo.universe_symbols(s) == {"AAPL", "MSFT"}      # tradable only
        assert repo.sp500_symbols(s) == {"AAPL", "MSFT"}


def test_reconcile_marks_inactive(db):
    with database.get_session() as s:
        repo.bulk_upsert_instruments(s, [
            {"symbol": "AAPL", "tradable": True}, {"symbol": "DEAD", "tradable": True},
        ])
    # broker no longer offers DEAD -> mark inactive
    with database.get_session() as s:
        repo.mark_instruments_inactive(s, ["DEAD"])
    with database.get_session() as s:
        assert repo.universe_symbols(s) == {"AAPL"}


def test_watchlist_membership(db):
    with database.get_session() as s:
        repo.set_watchlist(s, "AAPL", True, reason="sp500_seed")
        repo.set_watchlist(s, "MSFT", True, reason="news")
        repo.set_watchlist(s, "MSFT", False)
    with database.get_session() as s:
        assert repo.watchlist_symbols(s) == {"AAPL"}
        card = repo.get_ticker_card(s, "AAPL")
        assert card.watchlist_reason == "sp500_seed" and card.watchlist_added_at is not None


def test_ticker_events_due_and_consume(db):
    today = date(2026, 6, 8)
    with database.get_session() as s:
        repo.add_ticker_event(s, "AAPL", today - timedelta(days=1), "earnings")
        repo.add_ticker_event(s, "AAPL", today - timedelta(days=1), "earnings")  # idempotent
        repo.add_ticker_event(s, "MSFT", today + timedelta(days=5), "review")    # future
    with database.get_session() as s:
        due = repo.due_events(s, today=today)
        assert [e.symbol for e in due] == ["AAPL"]
        repo.mark_events_consumed(s, [due[0].id])
    with database.get_session() as s:
        assert repo.due_events(s, today=today) == []
