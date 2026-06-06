"""Tests for the mantainer (rendicontazione kept up to date)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tradingagents.broker import OrderRequest, PaperBroker
from tradingagents.execution import run_mantainer
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'mant.db'}")
    yield
    reset_engine()


def test_mantainer_marks_positions_to_market(db):
    broker = PaperBroker(cash=100_000)
    # buy 100 AAPL at 100 -> cash 90k, position 100
    broker.submit_order(OrderRequest("AAPL", "buy", 100, limit_price=100.0, client_order_id="c1"))
    with database.get_session() as s:
        repo.insert_price_bars(s, "AAPL", [{
            "ts": datetime(2026, 6, 1, tzinfo=timezone.utc),
            "open": 120, "high": 121, "low": 119, "close": 120.0,
        }])

    with database.get_session() as s:
        snap = run_mantainer(s, broker)
        # cash 90k + 100 shares * 120 (marked to market) = 102k
        assert snap.cash == pytest.approx(90_000)
        assert snap.total_value == pytest.approx(102_000)
        assert snap.positions[0]["symbol"] == "AAPL"

    with database.get_session() as s:
        assert repo.latest_portfolio_snapshot(s).total_value == pytest.approx(102_000)
