"""Offline end-to-end test of the app wiring (ingest -> screen -> brain -> execute)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.app import run_forever, run_once
from tradingagents.brain import DeskOpinion, PMDecision, RiskDecision
from tradingagents.broker import PaperBroker
from tradingagents.domain import Direction, RiskVerdict
from tradingagents.orchestration import make_brain_analyzer
from tradingagents.storage import reset_engine

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    reset_engine()


class _FetcherUp:
    def fetch(self, symbol, start, end, interval):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [
            {"ts": base + timedelta(days=i), "open": 100.0 + i, "high": 102.0 + i,
             "low": 98.0 + i, "close": 100.0 + i, "volume": 1000 + i}
            for i in range(40)
        ]


class _FakeLLM:
    def generate(self, system_prompt, context, schema, *, tools=(), recorder=None):
        if schema is DeskOpinion:
            return DeskOpinion(view="ok", suggested_direction=Direction.BUY,
                               suggested_conviction=Direction.BUY, rationale="r")
        if schema is PMDecision:
            return PMDecision(direction=Direction.BUY, conviction=Direction.BUY,
                              k_entry=0.5, k_stop=2.0, k_tp=3.0, pro=["p"], contro=["c"])
        if schema is RiskDecision:
            return RiskDecision(verdict=RiskVerdict.APPROVED, rationale="ok")
        raise AssertionError(schema)


def test_run_once_executes_offline(tmp_path):
    broker = PaperBroker()
    analyzer = make_brain_analyzer(_FakeLLM(), max_revisions=0)
    report = run_once(
        ["AAPL"],
        fetcher=_FetcherUp(),
        analyzer=analyzer,
        broker=broker,
        db_url=f"sqlite:///{tmp_path / 'app.db'}",
        start="2026-01-01",
        end="2026-03-01",
        base_risk_pct=0.01,
    )
    assert report.triggers == 1
    assert report.traded == 1
    assert report.trades[0].symbol == "AAPL"
    assert report.trades[0].status == "filled"


def test_autonomous_mode_seeds_watchlist_from_universe(tmp_path):
    """No symbols -> bootstrap universe + watchlist from the S&P 500 seed."""
    from tradingagents.storage import database, init_db
    from tradingagents.storage import repository as repo

    # PaperBroker with no listing -> sync falls back to the packaged S&P 500 seed.
    broker = PaperBroker()
    report = run_once(
        None,  # autonomous: decide the working set from own state
        fetcher=_FetcherUp(),
        analyzer=make_brain_analyzer(_FakeLLM(), max_revisions=0),
        broker=broker,
        top_k=3,
        db_url=f"sqlite:///{tmp_path / 'auto.db'}",
        start="2026-01-01", end="2026-03-01",
    )
    # the watchlist got seeded and the funnel analysed some of it
    assert report.triggers >= 1
    assert report.analyzed >= 1
    with database.get_session() as s:
        assert repo.watchlist_size(s) > 0
        assert len(repo.universe_symbols(s)) > 20


def test_run_forever_bounded(tmp_path):
    sleeps: list[float] = []
    reports = run_forever(
        ["AAPL"],
        interval_seconds=999,
        max_cycles=2,
        sleep=sleeps.append,  # no real sleeping
        fetcher=_FetcherUp(),
        analyzer=make_brain_analyzer(_FakeLLM(), max_revisions=0),
        broker=PaperBroker(),
        db_url=f"sqlite:///{tmp_path / 'loop.db'}",
        start="2026-01-01",
        end="2026-03-01",
    )
    assert len(reports) == 2
    assert len(sleeps) == 1  # sleeps between cycles, not after the last
