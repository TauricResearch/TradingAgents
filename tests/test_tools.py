"""Tests for the agent tool layer (real-time-first, write-through, heat)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.ingestion import ingest_price_bars
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo
from tradingagents.tools import get_open_positions_risk, get_realtime_quote, volume_spike

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'tools.db'}")
    yield
    reset_engine()


class _Fetcher:
    def fetch(self, symbol, start, end, interval):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [{"ts": base + timedelta(days=i), "open": 100.0 + i, "high": 102.0 + i,
                 "low": 98.0 + i, "close": 100.0 + i, "volume": 1000} for i in range(25)]


def test_realtime_quote_falls_back_to_db(db):
    with database.get_session() as s:
        ingest_price_bars(s, "AAPL", fetcher=_Fetcher(), start="2026-01-01", end="2026-03-01")
    with database.get_session() as s:
        # no live_fn -> latest stored close (124)
        assert get_realtime_quote(s, "AAPL") == pytest.approx(124.0)


def test_realtime_quote_live_first_writes_through(db):
    with database.get_session() as s:
        ingest_price_bars(s, "AAPL", fetcher=_Fetcher(), start="2026-01-01", end="2026-03-01")
    with database.get_session() as s:
        price = get_realtime_quote(s, "AAPL", live_fn=lambda sym: 200.0)
        assert price == 200.0
    with database.get_session() as s:
        # written through on the "rt" interval, not polluting daily history
        rt = repo.latest_price(s, "AAPL", interval="rt")
        assert rt is not None and rt.close == 200.0
        assert repo.latest_price(s, "AAPL", interval="1d").close == 124.0


def test_open_positions_risk_heat(db):
    with database.get_session() as s:
        repo.save_portfolio_snapshot(s, cash=50_000, total_value=100_000, positions=[])
        repo.record_trade(s, "AAPL", "buy", quantity=100, entry_price=100, stop_loss=90,
                          status="filled", client_order_id="c1")  # risk = 10*100 = 1000
    with database.get_session() as s:
        info = get_open_positions_risk(s)
        assert info["open_risk"] == pytest.approx(1000.0)
        assert info["heat_pct"] == pytest.approx(0.01)


def test_volume_spike(db):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [{"ts": base + timedelta(days=i), "open": 10, "high": 11, "low": 9,
             "close": 10, "volume": 1000} for i in range(20)]
    bars.append({"ts": base + timedelta(days=20), "open": 10, "high": 11, "low": 9,
                 "close": 10, "volume": 100000})  # spike
    with database.get_session() as s:
        repo.insert_price_bars(s, "AAPL", [{k: v for k, v in b.items()} for b in bars])
    with database.get_session() as s:
        assert volume_spike(s, "AAPL", window=20)["spike"] is True
