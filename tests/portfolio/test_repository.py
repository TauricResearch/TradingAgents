"""Tests for tradingagents/portfolio/repository.py.

Tests the PortfolioRepository façade — business logic for holdings management,
cash accounting, avg-cost-basis updates, and snapshot creation.

Supabase integration tests are automatically skipped when ``SUPABASE_URL`` is
not set in the environment (use the ``requires_supabase`` fixture marker).

Unit tests use ``mock_supabase_client`` to avoid DB access.

Run (unit tests only)::

    pytest tests/portfolio/test_repository.py -v -k "not integration"

Run (with Supabase)::

    SUPABASE_URL=... SUPABASE_KEY=... pytest tests/portfolio/test_repository.py -v
"""

from __future__ import annotations

import pytest

from tests.portfolio.conftest import requires_supabase


# ---------------------------------------------------------------------------
# add_holding — new position
# ---------------------------------------------------------------------------


def test_add_holding_new_position(mock_supabase_client, report_store):
    """add_holding() on a ticker not yet held must create a new Holding."""
    # TODO: implement
    # repo = PortfolioRepository(client=mock_supabase_client, store=report_store)
    # mock portfolio with enough cash
    # repo.add_holding(portfolio_id, "AAPL", shares=10, price=200.0)
    # assert mock_supabase_client.upsert_holding.called
    raise NotImplementedError


# ---------------------------------------------------------------------------
# add_holding — avg cost basis update
# ---------------------------------------------------------------------------


def test_add_holding_updates_avg_cost(mock_supabase_client, report_store):
    """add_holding() on an existing position must update avg_cost correctly.

    Formula: new_avg_cost = (old_shares * old_avg_cost + new_shares * price)
                             / (old_shares + new_shares)
    """
    # TODO: implement
    # existing holding: 50 shares @ 190.0
    # buy 25 more @ 200.0
    # expected avg_cost = (50*190 + 25*200) / 75 = 193.33...
    raise NotImplementedError


# ---------------------------------------------------------------------------
# add_holding — insufficient cash
# ---------------------------------------------------------------------------


def test_add_holding_raises_insufficient_cash(mock_supabase_client, report_store):
    """add_holding() must raise InsufficientCashError when cash < shares * price."""
    # TODO: implement
    # portfolio with cash=500.0, try to buy 10 shares @ 200.0 (cost=2000)
    # with pytest.raises(InsufficientCashError):
    #     repo.add_holding(portfolio_id, "AAPL", shares=10, price=200.0)
    raise NotImplementedError


# ---------------------------------------------------------------------------
# remove_holding — full position
# ---------------------------------------------------------------------------


def test_remove_holding_full_position(mock_supabase_client, report_store):
    """remove_holding() selling all shares must delete the holding row."""
    # TODO: implement
    # holding: 50 shares
    # sell 50 shares → holding deleted, cash credited
    # assert mock_supabase_client.delete_holding.called
    raise NotImplementedError


# ---------------------------------------------------------------------------
# remove_holding — partial position
# ---------------------------------------------------------------------------


def test_remove_holding_partial_position(mock_supabase_client, report_store):
    """remove_holding() selling a subset must reduce shares, not delete."""
    # TODO: implement
    # holding: 50 shares
    # sell 20 → holding.shares == 30, avg_cost unchanged
    raise NotImplementedError


# ---------------------------------------------------------------------------
# remove_holding — errors
# ---------------------------------------------------------------------------


def test_remove_holding_raises_insufficient_shares(mock_supabase_client, report_store):
    """remove_holding() must raise InsufficientSharesError when shares > held."""
    # TODO: implement
    # holding: 10 shares
    # try sell 20 → InsufficientSharesError
    raise NotImplementedError


def test_remove_holding_raises_when_ticker_not_held(mock_supabase_client, report_store):
    """remove_holding() must raise HoldingNotFoundError for unknown tickers."""
    # TODO: implement
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Cash accounting
# ---------------------------------------------------------------------------


def test_add_holding_deducts_cash(mock_supabase_client, report_store):
    """add_holding() must reduce portfolio.cash by shares * price."""
    # TODO: implement
    # portfolio.cash = 10_000, buy 10 @ 200 → cash should be 8_000
    raise NotImplementedError


def test_remove_holding_credits_cash(mock_supabase_client, report_store):
    """remove_holding() must increase portfolio.cash by shares * price."""
    # TODO: implement
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Trade recording
# ---------------------------------------------------------------------------


def test_add_holding_records_buy_trade(mock_supabase_client, report_store):
    """add_holding() must call client.record_trade() with action='BUY'."""
    # TODO: implement
    raise NotImplementedError


def test_remove_holding_records_sell_trade(mock_supabase_client, report_store):
    """remove_holding() must call client.record_trade() with action='SELL'."""
    # TODO: implement
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def test_take_snapshot(mock_supabase_client, report_store):
    """take_snapshot() must enrich holdings and persist a PortfolioSnapshot."""
    # TODO: implement
    # assert mock_supabase_client.save_snapshot.called
    # snapshot.total_value == cash + equity
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Supabase integration tests (auto-skip without SUPABASE_URL)
# ---------------------------------------------------------------------------


@requires_supabase
def test_integration_create_and_get_portfolio():
    """Integration: create a portfolio, retrieve it, verify fields match."""
    # TODO: implement
    raise NotImplementedError


@requires_supabase
def test_integration_add_and_remove_holding():
    """Integration: add holding, verify DB row; remove, verify deletion."""
    # TODO: implement
    raise NotImplementedError


@requires_supabase
def test_integration_record_and_list_trades():
    """Integration: record BUY + SELL trades, list them, verify order."""
    # TODO: implement
    raise NotImplementedError


@requires_supabase
def test_integration_save_and_load_snapshot():
    """Integration: take snapshot, retrieve latest, verify total_value."""
    # TODO: implement
    raise NotImplementedError
