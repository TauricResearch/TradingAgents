"""Tests for rating-based disinvestment."""

from __future__ import annotations

import pytest

from tradingagents.broker import PaperBroker
from tradingagents.execution import disinvest_weakest, rank_holdings_by_weakness
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'disinvest.db'}")
    yield
    reset_engine()


def _setup(s):
    # Two holdings: AAPL strong conviction, XYZ weak conviction.
    repo.record_trade(s, "AAPL", "buy", quantity=100, entry_price=100, stop_loss=90,
                      status="filled", client_order_id="a")
    repo.record_trade(s, "XYZ", "buy", quantity=100, entry_price=50, stop_loss=45,
                      status="filled", client_order_id="x")
    repo.upsert_ticker_card(s, "AAPL", latest_conviction="strong_buy", screening_score=0.9)
    repo.upsert_ticker_card(s, "XYZ", latest_conviction="hold", screening_score=0.2)


def test_ranking_weakest_first(db):
    with database.get_session() as s:
        _setup(s)
    with database.get_session() as s:
        ranked = rank_holdings_by_weakness(s)
        assert ranked[0].symbol == "XYZ"   # weakest first
        assert ranked[-1].symbol == "AAPL"


def test_disinvest_frees_room_from_weakest(db):
    with database.get_session() as s:
        _setup(s)
    broker = PaperBroker()
    with database.get_session() as s:
        closed = disinvest_weakest(s, broker, needed_cash=1000)
        # XYZ position value 5000 >= 1000 -> only the weakest is sold
        assert [t.symbol for t in closed] == ["XYZ"]
        assert closed[0].exit_reason == "rating"
    with database.get_session() as s:
        assert repo.trade_by_client_order_id(s, "x").status == "closed"
        assert repo.trade_by_client_order_id(s, "a").status == "filled"  # strong kept
