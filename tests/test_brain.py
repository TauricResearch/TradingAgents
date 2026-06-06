"""Tests for the brain graph (our wiki topology) with a fake LLM, offline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.brain import DeskOpinion, PMDecision, RiskDecision, analyze_symbol
from tradingagents.broker import PaperBroker
from tradingagents.domain import Direction, RiskVerdict
from tradingagents.ingestion import ingest_price_bars
from tradingagents.orchestration import make_brain_analyzer, run_cycle
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'brain.db'}")
    yield
    reset_engine()


class _FetcherUp:
    def fetch(self, symbol, start, end, interval):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = []
        for i in range(40):
            p = 100.0 + i
            bars.append({"ts": base + timedelta(days=i), "open": p, "high": p + 2,
                         "low": p - 2, "close": p, "volume": 1000 + i})
        return bars


class FakeLLM:
    """Returns canned structured outputs keyed by schema type."""

    def __init__(self, desk: DeskOpinion, pm: PMDecision, risk: RiskDecision):
        self._desk, self._pm, self._risk = desk, pm, risk

    def generate(self, system_prompt, context, schema):
        if schema is DeskOpinion:
            return self._desk
        if schema is PMDecision:
            return self._pm
        if schema is RiskDecision:
            return self._risk
        raise AssertionError(f"unexpected schema {schema}")


def _bullish_llm(*, k_tp=3.0, k_stop=2.0, verdict=RiskVerdict.APPROVED, direction=Direction.BUY):
    return FakeLLM(
        desk=DeskOpinion(view="ok", suggested_direction=direction,
                         suggested_conviction=direction, rationale="r"),
        pm=PMDecision(direction=direction, conviction=direction,
                      k_entry=0.5, k_stop=k_stop, k_tp=k_tp, pro=["p"], contro=["c"]),
        risk=RiskDecision(verdict=verdict, rationale="bear"),
    )


def _ingest(symbol="AAPL"):
    with database.get_session() as s:
        ingest_price_bars(s, symbol, fetcher=_FetcherUp(), start="2026-01-01", end="2026-03-01")
        repo.save_portfolio_snapshot(s, cash=20_000, total_value=100_000, positions=[])


def test_brain_produces_approved_buy_thesis(db):
    _ingest()
    with database.get_session() as s:
        rs = analyze_symbol(s, "AAPL", _bullish_llm(), max_revisions=0)
        assert rs.direction is Direction.BUY
        assert len(rs.agent_opinions) == 4           # 2 desks = 4 agents
        assert rs.levels is not None and rs.levels.has_prices
        assert rs.risk.verdict is RiskVerdict.APPROVED
        assert rs.is_complete()


def test_brain_hard_guardrail_overrides_llm(db):
    _ingest()
    with database.get_session() as s:
        # R:R = k_tp/k_stop = 1/3 < 1.5 -> guardrail fails -> SEND_BACK even if LLM approves
        rs = analyze_symbol(s, "AAPL", _bullish_llm(k_tp=1.0, k_stop=3.0), max_revisions=0)
        assert rs.risk.guardrail_checks["risk_reward"]["ok"] is False
        assert rs.risk.verdict is RiskVerdict.SEND_BACK


def test_brain_hold_has_no_levels(db):
    _ingest()
    with database.get_session() as s:
        rs = analyze_symbol(s, "AAPL", _bullish_llm(direction=Direction.HOLD), max_revisions=0)
        assert rs.direction is Direction.HOLD
        assert rs.levels is None
        assert rs.risk.verdict is RiskVerdict.APPROVED  # nothing to gate
        assert rs.is_complete()


def test_brain_analyzer_in_cycle_executes(db):
    _ingest()
    broker = PaperBroker()
    with database.get_session() as s:
        repo.upsert_ticker_card(s, "AAPL", screening_score=0.9)

    analyzer = make_brain_analyzer(_bullish_llm(), max_revisions=0)
    with database.get_session() as s:
        report = run_cycle(s, broker, analyzer, base_risk_pct=0.01)
        assert report.traded == 1
        assert report.trades[0].status == "filled"
        assert report.trades[0].symbol == "AAPL"

    # the deep-dive wrote the ticker card: latest call + next_check_date (DTC)
    with database.get_session() as s:
        card = repo.get_ticker_card(s, "AAPL")
        assert card.latest_direction == "buy"
        assert card.next_check_date is not None
