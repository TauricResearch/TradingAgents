"""Integration tests: domain thesis -> deterministic trade -> persistence."""

from __future__ import annotations

import pytest

from tradingagents.domain import Direction, Levels, ResearchState, RiskVerdict
from tradingagents.execution import (
    build_trade,
    can_trade,
    inject_portfolio_state,
    propose_and_record,
)
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'exec.db'}")
    yield
    reset_engine()


def _approved_state(direction=Direction.BUY) -> ResearchState:
    state = ResearchState(
        ticker="AAPL",
        market_view="m", sentiment_view="s",
        fundamental_view="f", technical_view="t",
        direction=direction, conviction_level=direction,
        levels=Levels(k_entry=0.5, k_stop=2, k_tp=3,
                      entry_price=100.0, stop_loss=90.0, take_profit=130.0),
        position_sizing_pct=0.01,
    )
    state.risk.verdict = RiskVerdict.APPROVED
    return state


def test_build_trade_long():
    state = _approved_state(Direction.BUY)
    assert can_trade(state)
    order = build_trade(state, portfolio_value=100_000, base_risk_pct=0.01)
    assert order.action == "buy"
    assert order.entry_price == 100.0
    # stop_distance = 10 ; risk 1% of 100k = 1000 ; qty = 100
    assert order.quantity == pytest.approx(100)
    assert order.client_order_id.startswith("AAPL-")


def test_build_trade_rejects_unapproved():
    state = _approved_state()
    state.risk.verdict = RiskVerdict.DECLINED
    assert not can_trade(state)
    with pytest.raises(ValueError):
        build_trade(state, 100_000)


def test_build_trade_rejects_hold():
    state = ResearchState(
        ticker="AAPL", market_view="m", sentiment_view="s",
        fundamental_view="f", technical_view="t",
        direction=Direction.HOLD, conviction_level=Direction.HOLD,
    )
    state.risk.verdict = RiskVerdict.APPROVED
    assert not can_trade(state)


def test_inject_portfolio_state_default_and_snapshot(db):
    with database.get_session() as s:
        assert inject_portfolio_state(s)["total_value"] == 0.0
        repo.save_portfolio_snapshot(s, cash=5000, total_value=50000,
                                     positions=[{"symbol": "MSFT", "qty": 10}])
    with database.get_session() as s:
        snap = inject_portfolio_state(s)
        assert snap["total_value"] == 50000
        assert snap["positions"][0]["symbol"] == "MSFT"


def test_propose_and_record_persists_idempotent_trade(db):
    with database.get_session() as s:
        repo.save_portfolio_snapshot(s, cash=20000, total_value=100000, positions=[])

    with database.get_session() as s:
        trade = propose_and_record(s, _approved_state(Direction.BUY), base_risk_pct=0.01)
        coid = trade.client_order_id
        assert trade.action == "buy"
        assert trade.status == "pending"
        assert trade.quantity == pytest.approx(100)
        assert trade.payload["proposal"]["direction"] == "buy"

    with database.get_session() as s:
        found = repo.trade_by_client_order_id(s, coid)
        assert found is not None and found.symbol == "AAPL"
