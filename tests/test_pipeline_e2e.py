"""End-to-end deterministic backbone (no LLM):

    ingest bars -> ATR from DB -> ATR price levels -> position sizing
    -> deterministic Trade -> persisted order

This is the spine the LLM graph plugs into: the graph only has to fill the
ResearchState's views/direction; everything numeric is the code below.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.domain import Direction, Levels, ResearchState, RiskVerdict
from tradingagents.domain.risk import atr_levels, position_size
from tradingagents.execution import propose_and_record
from tradingagents.indicators import atr_from_db
from tradingagents.ingestion import ingest_price_bars
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'e2e.db'}")
    yield
    reset_engine()


class FakeFetcher:
    def __init__(self, bars):
        self._bars = bars

    def fetch(self, symbol, start, end, interval):
        return list(self._bars)


def _uptrend_bars(n=40, start_price=100.0, step=1.0):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(n):
        p = start_price + i * step
        bars.append({
            "ts": base + timedelta(days=i),
            "open": p, "high": p + 2, "low": p - 2, "close": p, "volume": 1000 + i,
        })
    return bars


def test_data_to_trade_backbone(db):
    fetcher = FakeFetcher(_uptrend_bars())

    with database.get_session() as s:
        ingest_price_bars(s, "AAPL", fetcher=fetcher, start="2026-01-01", end="2026-03-01")
        repo.save_portfolio_snapshot(s, cash=20_000, total_value=100_000, positions=[])

    with database.get_session() as s:
        # 1) indicator from stored data
        a = atr_from_db(s, "AAPL", period=14)
        assert a is not None and a > 0

        last_close = repo.latest_price(s, "AAPL").close

        # 2) ATR price levels (deterministic)
        levels = atr_levels(last_close, a, Direction.BUY, k_entry=0.5, k_stop=2, k_tp=3)
        assert levels.entry_price < last_close  # buy on a small pullback
        assert levels.stop_loss < levels.entry_price < levels.take_profit

        # 3) assemble an approved thesis (the part the LLM graph would fill)
        state = ResearchState(
            ticker="AAPL",
            current_price=last_close,
            market_view="m", sentiment_view="s",
            fundamental_view="f", technical_view="t",
            direction=Direction.BUY, conviction_level=Direction.BUY,
            levels=levels, position_sizing_pct=0.01,
        )
        state.risk.verdict = RiskVerdict.APPROVED
        assert state.is_complete()

        # 4) deterministic trade -> persisted order
        trade = propose_and_record(s, state, base_risk_pct=0.01, max_position_pct=0.10)
        assert trade.action == "buy"
        assert trade.quantity > 0
        assert trade.status == "pending"
        assert trade.payload["proposal"]["levels"]["entry_price"] == pytest.approx(levels.entry_price)

    # 5) the order is durably stored and idempotently retrievable
    with database.get_session() as s:
        again = repo.trade_by_client_order_id(s, trade.client_order_id)
        assert again is not None and again.symbol == "AAPL"
