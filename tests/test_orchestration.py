"""Tests for the Trigger Engine + cycle runner."""

from __future__ import annotations

from datetime import date

import pytest

from tradingagents.broker import PaperBroker, PerTradeCommission
from tradingagents.domain import Direction, Levels, ResearchState, RiskVerdict
from tradingagents.orchestration import collect_triggers, hold_analyzer, run_cycle
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'orch.db'}")
    yield
    reset_engine()


def _buy_analyzer(session, symbol):
    state = ResearchState(
        ticker=symbol,
        market_view="m", sentiment_view="s", fundamental_view="f", technical_view="t",
        direction=Direction.BUY, conviction_level=Direction.BUY,
        levels=Levels(k_entry=0.5, k_stop=2, k_tp=3,
                      entry_price=100.0, stop_loss=90.0, take_profit=130.0),
        position_sizing_pct=0.01,
    )
    state.risk.verdict = RiskVerdict.APPROVED
    return state


# --- Trigger Engine -------------------------------------------------------
def test_collect_triggers_dedup_and_order(db):
    with database.get_session() as s:
        # AAPL: both a due checkpoint and a screening score -> checkpoint wins
        repo.upsert_ticker_card(s, "AAPL", screening_score=0.5,
                                next_check_date=date(2026, 1, 1))
        repo.upsert_ticker_card(s, "MSFT", screening_score=0.9)
        repo.upsert_ticker_card(s, "TSLA", screening_score=0.3)

    with database.get_session() as s:
        events = collect_triggers(s, top_k=10, today=date(2026, 6, 6))
        by_symbol = {e.symbol: e for e in events}
        assert by_symbol["AAPL"].type == "checkpoint"     # precedence
        assert by_symbol["MSFT"].type == "screening"
        # highest priority first; checkpoint priority 1.0 > MSFT 0.9
        assert events[0].symbol == "AAPL"


# --- Cycle runner ---------------------------------------------------------
def test_run_cycle_hold_stub_trades_nothing(db):
    broker = PaperBroker()
    with database.get_session() as s:
        repo.upsert_ticker_card(s, "AAPL", screening_score=0.9)
        repo.save_portfolio_snapshot(s, cash=20_000, total_value=100_000, positions=[])

    with database.get_session() as s:
        report = run_cycle(s, broker, hold_analyzer, top_k=5)
        assert report.triggers == 1
        assert report.analyzed == 1
        assert report.traded == 0
        assert report.skipped_not_tradable == 1


def test_run_cycle_executes_buy(db):
    broker = PaperBroker()
    with database.get_session() as s:
        repo.upsert_ticker_card(s, "AAPL", screening_score=0.9)
        repo.save_portfolio_snapshot(s, cash=20_000, total_value=100_000, positions=[])

    with database.get_session() as s:
        report = run_cycle(s, broker, _buy_analyzer, base_risk_pct=0.01)
        assert report.traded == 1
        assert report.trades[0].status == "filled"
        assert report.trades[0].symbol == "AAPL"


def test_run_cycle_cost_gate_skips(db):
    broker = PaperBroker()
    with database.get_session() as s:
        repo.upsert_ticker_card(s, "AAPL", screening_score=0.9)
        repo.save_portfolio_snapshot(s, cash=20_000, total_value=100_000, positions=[])

    with database.get_session() as s:
        # commission larger than any possible reward -> skipped on cost
        report = run_cycle(
            s, broker, _buy_analyzer,
            commission_model=PerTradeCommission(1_000_000.0),
            base_risk_pct=0.01,
        )
        assert report.traded == 0
        assert report.skipped_cost == 1
