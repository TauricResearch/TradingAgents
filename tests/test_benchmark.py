"""Tests for benchmark tracking + performance/alpha (Fase 3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.benchmark import benchmark_return, ingest_benchmarks
from tradingagents.performance import performance_vs_benchmarks, portfolio_return
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'bench.db'}")
    yield
    reset_engine()


class _Fetcher:
    def __init__(self, closes):
        self._closes = closes

    def fetch(self, symbol, start, end, interval):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [{"ts": base + timedelta(days=i), "open": c, "high": c, "low": c, "close": c}
                for i, c in enumerate(self._closes)]


def test_benchmark_return(db):
    with database.get_session() as s:
        ingest_benchmarks(s, ["SPY"], fetcher=_Fetcher([100, 110]), start="2026-01-01")
    with database.get_session() as s:
        assert benchmark_return(s, "SPY") == pytest.approx(0.10)   # 100 -> 110
        assert benchmark_return(s, "MISSING") is None


def test_portfolio_return(db):
    with database.get_session() as s:
        repo.save_portfolio_snapshot(s, cash=0, total_value=100_000, positions=[])
    with database.get_session() as s:
        repo.save_portfolio_snapshot(s, cash=0, total_value=120_000, positions=[])
    with database.get_session() as s:
        assert portfolio_return(s) == pytest.approx(0.20)


def test_alpha_vs_benchmark(db):
    with database.get_session() as s:
        ingest_benchmarks(s, ["SPY"], fetcher=_Fetcher([100, 110]), start="2026-01-01")
        repo.save_portfolio_snapshot(s, cash=0, total_value=100_000, positions=[])
    with database.get_session() as s:
        repo.save_portfolio_snapshot(s, cash=0, total_value=120_000, positions=[])
    with database.get_session() as s:
        rep = performance_vs_benchmarks(s, ["SPY"])
        assert rep.portfolio_return == pytest.approx(0.20)
        assert rep.benchmark_returns["SPY"] == pytest.approx(0.10)
        assert rep.alpha["SPY"] == pytest.approx(0.10)   # beat the benchmark by 10%
