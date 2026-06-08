"""Tests for universe reconciliation + watchlist seeding (Fase 2)."""

from __future__ import annotations

import pytest

from tradingagents.broker import PaperBroker
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo
from tradingagents.universe import Sp500Source, load_sp500_seed, seed_watchlist, sync_universe

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'usync.db'}")
    yield
    reset_engine()


def _seed_file(tmp_path):
    p = tmp_path / "sp500.csv"
    p.write_text("symbol,sector\n# comment\nAAPL,Tech\nMSFT,Tech\nJPM,Financials\n")
    return p


def test_load_sp500_seed_skips_comments_and_header(tmp_path):
    seed = load_sp500_seed(_seed_file(tmp_path))
    assert seed == {"AAPL": "Tech", "MSFT": "Tech", "JPM": "Financials"}


def test_packaged_seed_loads():
    seed = load_sp500_seed()  # the shipped data/sp500.csv
    assert "AAPL" in seed and len(seed) > 20


def test_sync_universe_from_broker_and_tags_sp500(tmp_path, db):
    broker = PaperBroker(assets=[
        {"symbol": "AAPL", "exchange": "NASDAQ", "asset_class": "us_equity", "tradable": True},
        {"symbol": "MSFT", "exchange": "NASDAQ", "tradable": True},
        {"symbol": "ZZZZ", "exchange": "NYSE", "tradable": True},  # tradable but not S&P500
    ])
    src = Sp500Source(_seed_file(tmp_path))
    with database.get_session() as s:
        rep = sync_universe(s, broker, sp500=src)
        assert set(rep.added) == {"AAPL", "MSFT", "ZZZZ"}
        assert rep.total == 3
    with database.get_session() as s:
        assert repo.universe_symbols(s) == {"AAPL", "MSFT", "ZZZZ"}
        assert repo.sp500_symbols(s) == {"AAPL", "MSFT"}  # ZZZZ not in seed


def test_sync_reconciles_removed(tmp_path, db):
    src = Sp500Source(_seed_file(tmp_path))
    with database.get_session() as s:
        sync_universe(s, PaperBroker(assets=[
            {"symbol": "AAPL", "tradable": True}, {"symbol": "GONE", "tradable": True},
        ]), sp500=src)
    # next sync: broker dropped GONE
    with database.get_session() as s:
        rep = sync_universe(s, PaperBroker(assets=[{"symbol": "AAPL", "tradable": True}]), sp500=src)
        assert rep.removed == ["GONE"]
    with database.get_session() as s:
        assert repo.universe_symbols(s) == {"AAPL"}


def test_sync_fallback_to_seed_when_no_listing(tmp_path, db):
    src = Sp500Source(_seed_file(tmp_path))
    with database.get_session() as s:
        rep = sync_universe(s, PaperBroker(assets=[]), sp500=src)  # no listing -> seed
        assert rep.total == 3
    with database.get_session() as s:
        assert repo.universe_symbols(s) == {"AAPL", "MSFT", "JPM"}


def test_seed_watchlist_sp500_intersect_tradable(tmp_path, db):
    src = Sp500Source(_seed_file(tmp_path))
    broker = PaperBroker(assets=[
        {"symbol": "AAPL", "tradable": True}, {"symbol": "MSFT", "tradable": True},
        {"symbol": "ZZZZ", "tradable": True},  # tradable, not S&P500 -> not seeded
    ])
    with database.get_session() as s:
        sync_universe(s, broker, sp500=src)
        added = seed_watchlist(s, mode="sp500")
        assert added == 2
    with database.get_session() as s:
        assert repo.watchlist_symbols(s) == {"AAPL", "MSFT"}
        # idempotent: second seeding does nothing
    with database.get_session() as s:
        assert seed_watchlist(s, mode="sp500") == 0
