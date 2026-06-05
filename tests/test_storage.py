"""Acceptance tests for the persistence layer (the data-layer contract).

These encode "the storage matches the wiki design": one coherent spine across
the four logical areas + the ticker card + sealed research_state. Run with::

    pytest tests/test_storage.py
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo


@pytest.fixture()
def db(tmp_path):
    """Fresh file-backed SQLite database per test, then dispose the engine."""
    url = f"sqlite:///{tmp_path / 'test.db'}"
    init_db(url)
    yield url
    reset_engine()


pytestmark = pytest.mark.unit


def test_instrument_and_ticker_card_roundtrip(db):
    with database.get_session() as s:
        repo.upsert_instrument(s, "AAPL", name="Apple Inc.", sector="Technology")
        repo.upsert_ticker_card(s, "AAPL", screening_score=0.82, rank=1, in_portfolio=True)

    # Update path: upsert again with new score
    with database.get_session() as s:
        repo.upsert_ticker_card(s, "AAPL", screening_score=0.91)

    with database.get_session() as s:
        card = repo.get_ticker_card(s, "AAPL")
        assert card is not None
        assert card.screening_score == 0.91  # updated, not duplicated
        assert card.in_portfolio is True


def test_top_screened_orders_by_score(db):
    with database.get_session() as s:
        repo.upsert_ticker_card(s, "AAPL", screening_score=0.5)
        repo.upsert_ticker_card(s, "MSFT", screening_score=0.9)
        repo.upsert_ticker_card(s, "NVDA", screening_score=0.7)
        repo.upsert_ticker_card(s, "TSLA")  # no score -> excluded

    with database.get_session() as s:
        ranked = [c.symbol for c in repo.top_screened(s, limit=10)]
        assert ranked == ["MSFT", "NVDA", "AAPL"]


def test_research_state_seal_and_read(db):
    payload = {
        "ticker": "AAPL",
        "proposal": {"direction": "buy", "entry_price": 180.0, "stop_loss": 170.0},
        "agent_opinions": [{"agent": "technical", "suggested_direction": "buy"}],
    }
    with database.get_session() as s:
        repo.save_research_state(
            s, "AAPL", payload, direction="buy", conviction="buy", status="approved"
        )

    with database.get_session() as s:
        state = repo.latest_research_state(s, "AAPL")
        assert state is not None
        assert state.status == "approved"
        assert state.payload["proposal"]["entry_price"] == 180.0


def test_price_bars_and_latest(db):
    bars = [
        {"ts": datetime(2026, 6, 1, tzinfo=timezone.utc), "open": 1, "high": 2, "low": 1, "close": 1.5},
        {"ts": datetime(2026, 6, 2, tzinfo=timezone.utc), "open": 1.5, "high": 3, "low": 1.4, "close": 2.8},
    ]
    with database.get_session() as s:
        added = repo.insert_price_bars(s, "AAPL", bars)
        assert added == 2

    with database.get_session() as s:
        last = repo.latest_price(s, "AAPL")
        assert last is not None
        assert last.close == 2.8


def test_portfolio_snapshot_roundtrip(db):
    with database.get_session() as s:
        repo.save_portfolio_snapshot(
            s,
            cash=10000.0,
            total_value=25000.0,
            positions=[{"symbol": "AAPL", "qty": 50}],
            pnl=1200.0,
        )

    with database.get_session() as s:
        snap = repo.latest_portfolio_snapshot(s)
        assert snap is not None
        assert snap.cash == 10000.0
        assert snap.positions[0]["symbol"] == "AAPL"


def test_trade_idempotency_lookup(db):
    with database.get_session() as s:
        repo.record_trade(
            s, "AAPL", "buy", quantity=10, entry_price=180.0, client_order_id="coid-123"
        )

    with database.get_session() as s:
        found = repo.trade_by_client_order_id(s, "coid-123")
        assert found is not None
        assert found.action == "buy"
        assert repo.trade_by_client_order_id(s, "missing") is None


def test_charter_rule_set_and_get(db):
    with database.get_session() as s:
        repo.set_charter_rule(s, "max_portfolio_var", 0.10, "VaR cap of portfolio")
        repo.set_charter_rule(s, "cash_reserve_pct", 0.10)

    with database.get_session() as s:
        assert repo.get_charter_rule(s, "max_portfolio_var") == 0.10
        assert repo.get_charter_rule(s, "missing", default=0.0) == 0.0
