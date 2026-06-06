"""Tests for the Trigger Engine + cycle runner."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from tradingagents.broker import PaperBroker, PerTradeCommission
from tradingagents.domain import Direction, Levels, ResearchState, RiskVerdict
from tradingagents.ingestion import ingest_price_bars
from tradingagents.orchestration import collect_triggers, hold_analyzer, price_alerts, run_cycle
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
class _SpikeFetcher:
    """16 flat bars then a large jump on the last bar."""

    def fetch(self, symbol, start, end, interval):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = []
        for i in range(16):
            bars.append({"ts": base + timedelta(days=i), "open": 100.0, "high": 100.5,
                         "low": 99.5, "close": 100.0, "volume": 1000})
        bars.append({"ts": base + timedelta(days=16), "open": 100.0, "high": 110.0,
                     "low": 100.0, "close": 110.0, "volume": 5000})  # +10 spike
        return bars


def test_price_alert_fires_on_anomalous_move(db):
    with database.get_session() as s:
        ingest_price_bars(s, "AAPL", fetcher=_SpikeFetcher(), start="2026-01-01", end="2026-03-01")
    with database.get_session() as s:
        alerts = price_alerts(s, threshold_atr=1.5)
        assert any(e.symbol == "AAPL" and e.type == "price_alert" for e in alerts)
        # appears in the unified queue too
        assert any(e.type == "price_alert" for e in collect_triggers(s))


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


def test_run_cycle_records_commission(db):
    broker = PaperBroker()
    with database.get_session() as s:
        repo.upsert_ticker_card(s, "AAPL", screening_score=0.9)
        repo.save_portfolio_snapshot(s, cash=20_000, total_value=100_000, positions=[])

    with database.get_session() as s:
        report = run_cycle(
            s, broker, _buy_analyzer,
            commission_model=PerTradeCommission(5.0),
            token_cost=0.5,
            base_risk_pct=0.01,
        )
        assert report.traded == 1
        assert report.trades[0].commission == 5.0
        assert report.trades[0].token_cost == 0.5


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
