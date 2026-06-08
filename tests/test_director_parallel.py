"""Tests for the Director: parallel fan-out + portfolio-level Statute (Fase 5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.brain import DeskOpinion, PMDecision, RiskDecision
from tradingagents.brain.director import analyze_batch
from tradingagents.broker import PaperBroker
from tradingagents.domain import Direction, RiskVerdict
from tradingagents.execution import PortfolioProposal, admit_within_statute
from tradingagents.ingestion import ingest_price_bars
from tradingagents.orchestration import make_brain_analyzer, run_cycle
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'director.db'}")
    yield
    reset_engine()


class _FetcherUp:
    def fetch(self, symbol, start, end, interval):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [{"ts": base + timedelta(days=i), "open": 100.0 + i, "high": 102.0 + i,
                 "low": 98.0 + i, "close": 100.0 + i, "volume": 1000} for i in range(40)]


class _FakeLLM:
    def generate(self, system_prompt, context, schema, *, tools=(), recorder=None):
        if schema is DeskOpinion:
            return DeskOpinion(view="v", suggested_direction=Direction.BUY,
                               suggested_conviction=Direction.BUY, rationale="r")
        if schema is PMDecision:
            return PMDecision(direction=Direction.BUY, conviction=Direction.BUY,
                              k_entry=0.5, k_stop=2.0, k_tp=3.0)
        return RiskDecision(verdict=RiskVerdict.APPROVED, rationale="ok")


# --- portfolio-level Statute ---------------------------------------------
def test_admit_within_statute_cash_reserve(db):
    with database.get_session() as s:
        repo.save_portfolio_snapshot(s, cash=25_000, total_value=100_000, positions=[])
    with database.get_session() as s:
        # three 10k buys: cash 25k, reserve 10k -> only one fits (25-10=15>=10, 15-10=5<10)
        props = [PortfolioProposal(f"S{i}", position_value=10_000, risk_value=500) for i in range(3)]
        res = admit_within_statute(s, props, charter={"cash_reserve_pct": 0.10})
        assert len(res.admitted) == 1
        assert "cash_reserve" in set(res.blocked.values())


def test_admit_within_statute_var_cap(db):
    with database.get_session() as s:
        repo.save_portfolio_snapshot(s, cash=100_000, total_value=100_000, positions=[])
    with database.get_session() as s:
        # each risk 4k = 4% of 100k; cap 10% -> at most 2 admitted
        props = [PortfolioProposal(f"S{i}", position_value=1_000, risk_value=4_000) for i in range(4)]
        res = admit_within_statute(s, props, charter={"max_portfolio_var": 0.10})
        assert len(res.admitted) == 2
        assert "portfolio_var" in set(res.blocked.values())


# --- parallel fan-out -----------------------------------------------------
def test_analyze_batch_runs_all_symbols(db):
    syms = ["AAA", "BBB", "CCC"]
    with database.get_session() as s:
        for sym in syms:
            ingest_price_bars(s, sym, fetcher=_FetcherUp(), start="2026-01-01", end="2026-03-01")
        repo.save_portfolio_snapshot(s, cash=100_000, total_value=100_000, positions=[])

    states = analyze_batch(
        syms, _FakeLLM(), session_factory=database.get_session,
        max_parallel=3, max_revisions=0,
    )
    assert set(states) == set(syms)
    assert all(st.direction is Direction.BUY for st in states.values())


def test_run_cycle_with_director_batch(db):
    syms = ["AAA", "BBB"]
    with database.get_session() as s:
        for sym in syms:
            ingest_price_bars(s, sym, fetcher=_FetcherUp(), start="2026-01-01", end="2026-03-01")
            repo.set_watchlist(s, sym, True, reason="seed")
        repo.save_portfolio_snapshot(s, cash=100_000, total_value=100_000, positions=[])

    def batch(symbols):
        return analyze_batch(symbols, _FakeLLM(), session_factory=database.get_session,
                             max_parallel=2, max_revisions=0)

    broker = PaperBroker()
    with database.get_session() as s:
        report = run_cycle(s, broker, make_brain_analyzer(_FakeLLM(), max_revisions=0),
                           batch_analyze=batch, base_risk_pct=0.01)
        assert report.analyzed == 2
        assert report.traded >= 1   # portfolio Statute may cap, but at least one
