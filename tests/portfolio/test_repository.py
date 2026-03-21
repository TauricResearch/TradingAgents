"""Tests for tradingagents/portfolio/repository.py.

Unit tests use ``mock_supabase_client`` to avoid DB access.
Integration tests auto-skip when ``SUPABASE_CONNECTION_STRING`` is unset.

Run (unit tests only)::

    pytest tests/portfolio/test_repository.py -v -k "not integration"
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from tradingagents.portfolio.exceptions import (
    HoldingNotFoundError,
    InsufficientCashError,
    InsufficientSharesError,
)
from tradingagents.portfolio.models import Holding, Portfolio, Trade
from tradingagents.portfolio.repository import PortfolioRepository

# Define skip marker inline — avoids problematic absolute import from conftest
import os
requires_supabase = pytest.mark.skipif(
    not os.getenv("SUPABASE_CONNECTION_STRING"),
    reason="SUPABASE_CONNECTION_STRING not set -- skipping integration tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(mock_client, report_store):
    """Build a PortfolioRepository with mock client and real report store."""
    return PortfolioRepository(
        client=mock_client,
        store=report_store,
        config={"data_dir": "reports", "max_positions": 15,
                "max_position_pct": 0.15, "max_sector_pct": 0.35,
                "min_cash_pct": 0.05, "default_budget": 100_000.0,
                "supabase_connection_string": ""},
    )


def _mock_portfolio(pid="pid-1", cash=10_000.0):
    return Portfolio(
        portfolio_id=pid, name="Test", cash=cash,
        initial_cash=100_000.0, currency="USD",
    )


def _mock_holding(pid="pid-1", ticker="AAPL", shares=50.0, avg_cost=190.0):
    return Holding(
        holding_id="hid-1", portfolio_id=pid, ticker=ticker,
        shares=shares, avg_cost=avg_cost,
    )


# ---------------------------------------------------------------------------
# add_holding — new position
# ---------------------------------------------------------------------------


def test_add_holding_new_position(mock_supabase_client, report_store):
    """add_holding() on a ticker not yet held must create a new Holding."""
    mock_supabase_client.get_portfolio.return_value = _mock_portfolio(cash=10_000.0)
    mock_supabase_client.get_holding.return_value = None
    mock_supabase_client.upsert_holding.side_effect = lambda h: h
    mock_supabase_client.update_portfolio.side_effect = lambda p: p
    mock_supabase_client.record_trade.side_effect = lambda t: t

    repo = _make_repo(mock_supabase_client, report_store)
    holding = repo.add_holding("pid-1", "AAPL", shares=10, price=200.0)

    assert holding.ticker == "AAPL"
    assert holding.shares == 10
    assert holding.avg_cost == 200.0
    assert mock_supabase_client.upsert_holding.called


# ---------------------------------------------------------------------------
# add_holding — avg cost basis update
# ---------------------------------------------------------------------------


def test_add_holding_updates_avg_cost(mock_supabase_client, report_store):
    """add_holding() on existing position must update avg_cost correctly."""
    mock_supabase_client.get_portfolio.return_value = _mock_portfolio(cash=10_000.0)
    existing = _mock_holding(shares=50.0, avg_cost=190.0)
    mock_supabase_client.get_holding.return_value = existing
    mock_supabase_client.upsert_holding.side_effect = lambda h: h
    mock_supabase_client.update_portfolio.side_effect = lambda p: p
    mock_supabase_client.record_trade.side_effect = lambda t: t

    repo = _make_repo(mock_supabase_client, report_store)
    holding = repo.add_holding("pid-1", "AAPL", shares=25, price=200.0)

    # expected: (50*190 + 25*200) / 75 = 193.333...
    expected_avg = (50 * 190.0 + 25 * 200.0) / 75
    assert holding.shares == 75
    assert holding.avg_cost == pytest.approx(expected_avg)


# ---------------------------------------------------------------------------
# add_holding — insufficient cash
# ---------------------------------------------------------------------------


def test_add_holding_raises_insufficient_cash(mock_supabase_client, report_store):
    """add_holding() must raise InsufficientCashError when cash < shares * price."""
    mock_supabase_client.get_portfolio.return_value = _mock_portfolio(cash=500.0)

    repo = _make_repo(mock_supabase_client, report_store)
    with pytest.raises(InsufficientCashError):
        repo.add_holding("pid-1", "AAPL", shares=10, price=200.0)


# ---------------------------------------------------------------------------
# remove_holding — full position
# ---------------------------------------------------------------------------


def test_remove_holding_full_position(mock_supabase_client, report_store):
    """remove_holding() selling all shares must delete the holding row."""
    mock_supabase_client.get_holding.return_value = _mock_holding(shares=50.0)
    mock_supabase_client.get_portfolio.return_value = _mock_portfolio(cash=5_000.0)
    mock_supabase_client.delete_holding.return_value = None
    mock_supabase_client.update_portfolio.side_effect = lambda p: p
    mock_supabase_client.record_trade.side_effect = lambda t: t

    repo = _make_repo(mock_supabase_client, report_store)
    result = repo.remove_holding("pid-1", "AAPL", shares=50.0, price=200.0)

    assert result is None
    assert mock_supabase_client.delete_holding.called


# ---------------------------------------------------------------------------
# remove_holding — partial position
# ---------------------------------------------------------------------------


def test_remove_holding_partial_position(mock_supabase_client, report_store):
    """remove_holding() selling a subset must reduce shares, not delete."""
    mock_supabase_client.get_holding.return_value = _mock_holding(shares=50.0)
    mock_supabase_client.get_portfolio.return_value = _mock_portfolio(cash=5_000.0)
    mock_supabase_client.upsert_holding.side_effect = lambda h: h
    mock_supabase_client.update_portfolio.side_effect = lambda p: p
    mock_supabase_client.record_trade.side_effect = lambda t: t

    repo = _make_repo(mock_supabase_client, report_store)
    result = repo.remove_holding("pid-1", "AAPL", shares=20.0, price=200.0)

    assert result is not None
    assert result.shares == 30.0


# ---------------------------------------------------------------------------
# remove_holding — errors
# ---------------------------------------------------------------------------


def test_remove_holding_raises_insufficient_shares(mock_supabase_client, report_store):
    """remove_holding() must raise InsufficientSharesError when shares > held."""
    mock_supabase_client.get_holding.return_value = _mock_holding(shares=10.0)

    repo = _make_repo(mock_supabase_client, report_store)
    with pytest.raises(InsufficientSharesError):
        repo.remove_holding("pid-1", "AAPL", shares=20.0, price=200.0)


def test_remove_holding_raises_when_ticker_not_held(mock_supabase_client, report_store):
    """remove_holding() must raise HoldingNotFoundError for unknown tickers."""
    mock_supabase_client.get_holding.return_value = None

    repo = _make_repo(mock_supabase_client, report_store)
    with pytest.raises(HoldingNotFoundError):
        repo.remove_holding("pid-1", "ZZZZ", shares=10.0, price=100.0)


# ---------------------------------------------------------------------------
# Cash accounting
# ---------------------------------------------------------------------------


def test_add_holding_deducts_cash(mock_supabase_client, report_store):
    """add_holding() must reduce portfolio.cash by shares * price."""
    portfolio = _mock_portfolio(cash=10_000.0)
    mock_supabase_client.get_portfolio.return_value = portfolio
    mock_supabase_client.get_holding.return_value = None
    mock_supabase_client.upsert_holding.side_effect = lambda h: h
    mock_supabase_client.update_portfolio.side_effect = lambda p: p
    mock_supabase_client.record_trade.side_effect = lambda t: t

    repo = _make_repo(mock_supabase_client, report_store)
    repo.add_holding("pid-1", "AAPL", shares=10, price=200.0)

    # Check the portfolio passed to update_portfolio had cash deducted
    updated = mock_supabase_client.update_portfolio.call_args[0][0]
    assert updated.cash == pytest.approx(8_000.0)


def test_remove_holding_credits_cash(mock_supabase_client, report_store):
    """remove_holding() must increase portfolio.cash by shares * price."""
    portfolio = _mock_portfolio(cash=5_000.0)
    mock_supabase_client.get_holding.return_value = _mock_holding(shares=50.0)
    mock_supabase_client.get_portfolio.return_value = portfolio
    mock_supabase_client.upsert_holding.side_effect = lambda h: h
    mock_supabase_client.update_portfolio.side_effect = lambda p: p
    mock_supabase_client.record_trade.side_effect = lambda t: t

    repo = _make_repo(mock_supabase_client, report_store)
    repo.remove_holding("pid-1", "AAPL", shares=20.0, price=200.0)

    updated = mock_supabase_client.update_portfolio.call_args[0][0]
    assert updated.cash == pytest.approx(9_000.0)


# ---------------------------------------------------------------------------
# Trade recording
# ---------------------------------------------------------------------------


def test_add_holding_records_buy_trade(mock_supabase_client, report_store):
    """add_holding() must call client.record_trade() with action='BUY'."""
    mock_supabase_client.get_portfolio.return_value = _mock_portfolio(cash=10_000.0)
    mock_supabase_client.get_holding.return_value = None
    mock_supabase_client.upsert_holding.side_effect = lambda h: h
    mock_supabase_client.update_portfolio.side_effect = lambda p: p
    mock_supabase_client.record_trade.side_effect = lambda t: t

    repo = _make_repo(mock_supabase_client, report_store)
    repo.add_holding("pid-1", "AAPL", shares=10, price=200.0)

    trade = mock_supabase_client.record_trade.call_args[0][0]
    assert trade.action == "BUY"
    assert trade.ticker == "AAPL"
    assert trade.shares == 10
    assert trade.total_value == pytest.approx(2_000.0)


def test_remove_holding_records_sell_trade(mock_supabase_client, report_store):
    """remove_holding() must call client.record_trade() with action='SELL'."""
    mock_supabase_client.get_holding.return_value = _mock_holding(shares=50.0)
    mock_supabase_client.get_portfolio.return_value = _mock_portfolio(cash=5_000.0)
    mock_supabase_client.upsert_holding.side_effect = lambda h: h
    mock_supabase_client.update_portfolio.side_effect = lambda p: p
    mock_supabase_client.record_trade.side_effect = lambda t: t

    repo = _make_repo(mock_supabase_client, report_store)
    repo.remove_holding("pid-1", "AAPL", shares=20.0, price=200.0)

    trade = mock_supabase_client.record_trade.call_args[0][0]
    assert trade.action == "SELL"
    assert trade.ticker == "AAPL"
    assert trade.shares == 20.0


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def test_take_snapshot(mock_supabase_client, report_store):
    """take_snapshot() must enrich holdings and persist a PortfolioSnapshot."""
    portfolio = _mock_portfolio(cash=5_000.0)
    holding = _mock_holding(shares=50.0, avg_cost=190.0)
    mock_supabase_client.get_portfolio.return_value = portfolio
    mock_supabase_client.list_holdings.return_value = [holding]
    mock_supabase_client.save_snapshot.side_effect = lambda s: s

    repo = _make_repo(mock_supabase_client, report_store)
    snapshot = repo.take_snapshot("pid-1", prices={"AAPL": 200.0})

    assert mock_supabase_client.save_snapshot.called
    assert snapshot.cash == 5_000.0
    assert snapshot.num_positions == 1
    assert snapshot.total_value == pytest.approx(5_000.0 + 50.0 * 200.0)


# ---------------------------------------------------------------------------
# Supabase integration tests (auto-skip without SUPABASE_CONNECTION_STRING)
# ---------------------------------------------------------------------------


@requires_supabase
def test_integration_create_and_get_portfolio():
    """Integration: create a portfolio, retrieve it, verify fields match."""
    from tradingagents.portfolio.supabase_client import SupabaseClient
    client = SupabaseClient.get_instance()
    from tradingagents.portfolio.report_store import ReportStore
    store = ReportStore()

    repo = PortfolioRepository(client=client, store=store)
    portfolio = repo.create_portfolio("Integration Test", initial_cash=50_000.0)
    try:
        fetched = repo.get_portfolio(portfolio.portfolio_id)
        assert fetched.name == "Integration Test"
        assert fetched.cash == pytest.approx(50_000.0)
        assert fetched.initial_cash == pytest.approx(50_000.0)
    finally:
        client.delete_portfolio(portfolio.portfolio_id)


@requires_supabase
def test_integration_add_and_remove_holding():
    """Integration: add holding, verify; remove, verify deletion."""
    from tradingagents.portfolio.supabase_client import SupabaseClient
    client = SupabaseClient.get_instance()
    from tradingagents.portfolio.report_store import ReportStore
    store = ReportStore()

    repo = PortfolioRepository(client=client, store=store)
    portfolio = repo.create_portfolio("Hold Test", initial_cash=50_000.0)
    try:
        holding = repo.add_holding(
            portfolio.portfolio_id, "AAPL", shares=10, price=200.0,
            sector="Technology",
        )
        assert holding.ticker == "AAPL"
        assert holding.shares == 10

        # Verify cash deducted
        p = repo.get_portfolio(portfolio.portfolio_id)
        assert p.cash == pytest.approx(48_000.0)

        # Sell all
        result = repo.remove_holding(portfolio.portfolio_id, "AAPL", shares=10, price=210.0)
        assert result is None

        # Verify cash credited
        p = repo.get_portfolio(portfolio.portfolio_id)
        assert p.cash == pytest.approx(50_100.0)
    finally:
        client.delete_portfolio(portfolio.portfolio_id)


@requires_supabase
def test_integration_record_and_list_trades():
    """Integration: trades are recorded automatically via add/remove holding."""
    from tradingagents.portfolio.supabase_client import SupabaseClient
    client = SupabaseClient.get_instance()
    from tradingagents.portfolio.report_store import ReportStore
    store = ReportStore()

    repo = PortfolioRepository(client=client, store=store)
    portfolio = repo.create_portfolio("Trade Test", initial_cash=50_000.0)
    try:
        repo.add_holding(portfolio.portfolio_id, "MSFT", shares=5, price=400.0)
        repo.remove_holding(portfolio.portfolio_id, "MSFT", shares=5, price=410.0)

        trades = client.list_trades(portfolio.portfolio_id)
        assert len(trades) == 2
        assert trades[0].action == "SELL"  # newest first
        assert trades[1].action == "BUY"
    finally:
        client.delete_portfolio(portfolio.portfolio_id)


@requires_supabase
def test_integration_save_and_load_snapshot():
    """Integration: take snapshot, retrieve latest, verify total_value."""
    from tradingagents.portfolio.supabase_client import SupabaseClient
    client = SupabaseClient.get_instance()
    from tradingagents.portfolio.report_store import ReportStore
    store = ReportStore()

    repo = PortfolioRepository(client=client, store=store)
    portfolio = repo.create_portfolio("Snap Test", initial_cash=50_000.0)
    try:
        repo.add_holding(portfolio.portfolio_id, "AAPL", shares=10, price=200.0)
        snapshot = repo.take_snapshot(portfolio.portfolio_id, prices={"AAPL": 210.0})

        assert snapshot.num_positions == 1
        assert snapshot.cash == pytest.approx(48_000.0)
        assert snapshot.total_value == pytest.approx(48_000.0 + 10 * 210.0)

        latest = client.get_latest_snapshot(portfolio.portfolio_id)
        assert latest is not None
        assert latest.snapshot_id == snapshot.snapshot_id
    finally:
        client.delete_portfolio(portfolio.portfolio_id)
