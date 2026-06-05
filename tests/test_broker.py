"""Tests for the broker layer + submit/reconcile (PaperBroker offline)."""

from __future__ import annotations

import os

import pytest

from tradingagents.broker import OrderRequest, OrderStatus, PaperBroker
from tradingagents.domain import Direction, Levels, ResearchState, RiskVerdict
from tradingagents.execution import (
    execute_thesis,
    propose_and_record,
    reconcile_open_trades,
    submit_trade,
)
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'broker.db'}")
    yield
    reset_engine()


def _approved_state() -> ResearchState:
    state = ResearchState(
        ticker="AAPL",
        market_view="m", sentiment_view="s", fundamental_view="f", technical_view="t",
        direction=Direction.BUY, conviction_level=Direction.BUY,
        levels=Levels(k_entry=0.5, k_stop=2, k_tp=3,
                      entry_price=100.0, stop_loss=90.0, take_profit=130.0),
        position_sizing_pct=0.01,
    )
    state.risk.verdict = RiskVerdict.APPROVED
    return state


# --- PaperBroker ----------------------------------------------------------
def test_paper_broker_fills_and_is_idempotent():
    broker = PaperBroker(cash=100_000)
    req = OrderRequest(symbol="AAPL", side="buy", quantity=10,
                       limit_price=100.0, client_order_id="coid-1")
    o1 = broker.submit_order(req)
    assert o1.status is OrderStatus.FILLED and o1.broker_order_id
    # same client_order_id -> same order, no double fill
    o2 = broker.submit_order(req)
    assert o2.broker_order_id == o1.broker_order_id
    assert broker.get_positions() == [{"symbol": "AAPL", "qty": 10}]


def test_paper_broker_get_order():
    broker = PaperBroker()
    broker.submit_order(OrderRequest("MSFT", "buy", 5, limit_price=10, client_order_id="x"))
    assert broker.get_order("x") is not None
    assert broker.get_order("nope") is None


# --- submit / execute -----------------------------------------------------
def test_submit_trade_updates_status(db):
    broker = PaperBroker()
    with database.get_session() as s:
        repo.save_portfolio_snapshot(s, cash=20_000, total_value=100_000, positions=[])
        trade = propose_and_record(s, _approved_state())
        assert trade.status == "pending"
        submit_trade(s, trade, broker)
        assert trade.status == "filled"
        assert trade.broker_order_id is not None


def test_execute_thesis_end_to_end(db):
    broker = PaperBroker()
    with database.get_session() as s:
        repo.save_portfolio_snapshot(s, cash=20_000, total_value=100_000, positions=[])
        trade = execute_thesis(s, _approved_state(), broker, base_risk_pct=0.01)
        assert trade.status == "filled"
        assert trade.quantity > 0


# --- reconciliation (graceful recovery) -----------------------------------
def test_reconcile_aligns_db_to_broker(db):
    broker = PaperBroker()
    with database.get_session() as s:
        # a pending trade exists in the DB but was actually filled at the broker
        trade = repo.record_trade(
            s, "AAPL", "buy", quantity=10, entry_price=100.0,
            client_order_id="coid-recon", status="pending",
        )
    broker.submit_order(OrderRequest("AAPL", "buy", 10, limit_price=100.0,
                                     client_order_id="coid-recon"))

    with database.get_session() as s:
        updated = reconcile_open_trades(s, broker)
        assert len(updated) == 1
        assert updated[0].status == "filled"

    with database.get_session() as s:
        assert repo.trade_by_client_order_id(s, "coid-recon").status == "filled"


# --- Alpaca (integration, gated) ------------------------------------------
@pytest.mark.integration
def test_alpaca_account_real():
    if not (os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY")):
        pytest.skip("Alpaca credentials not set")
    from tradingagents.broker.alpaca import AlpacaBroker

    acct = AlpacaBroker().get_account()
    assert "cash" in acct
