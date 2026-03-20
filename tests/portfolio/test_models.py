"""Tests for tradingagents/portfolio/models.py.

Tests the four dataclass models: Portfolio, Holding, Trade, PortfolioSnapshot.

Coverage targets:
- to_dict() / from_dict() round-trips
- enrich() computed-field logic
- Edge cases (zero cost basis, zero portfolio value)

Run::

    pytest tests/portfolio/test_models.py -v
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Portfolio round-trip
# ---------------------------------------------------------------------------


def test_portfolio_to_dict_round_trip(sample_portfolio):
    """Portfolio.to_dict() -> Portfolio.from_dict() must be lossless."""
    # TODO: implement
    # d = sample_portfolio.to_dict()
    # restored = Portfolio.from_dict(d)
    # assert restored.portfolio_id == sample_portfolio.portfolio_id
    # assert restored.cash == sample_portfolio.cash
    # ... all stored fields
    raise NotImplementedError


def test_portfolio_to_dict_excludes_runtime_fields(sample_portfolio):
    """to_dict() must not include computed fields (total_value, equity_value, cash_pct)."""
    # TODO: implement
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Holding round-trip
# ---------------------------------------------------------------------------


def test_holding_to_dict_round_trip(sample_holding):
    """Holding.to_dict() -> Holding.from_dict() must be lossless."""
    # TODO: implement
    raise NotImplementedError


def test_holding_to_dict_excludes_runtime_fields(sample_holding):
    """to_dict() must not include current_price, current_value, weight, etc."""
    # TODO: implement
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Trade round-trip
# ---------------------------------------------------------------------------


def test_trade_to_dict_round_trip(sample_trade):
    """Trade.to_dict() -> Trade.from_dict() must be lossless."""
    # TODO: implement
    raise NotImplementedError


# ---------------------------------------------------------------------------
# PortfolioSnapshot round-trip
# ---------------------------------------------------------------------------


def test_snapshot_to_dict_round_trip(sample_snapshot):
    """PortfolioSnapshot.to_dict() -> PortfolioSnapshot.from_dict() round-trip."""
    # TODO: implement
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Holding.enrich()
# ---------------------------------------------------------------------------


def test_holding_enrich_computes_current_value(sample_holding):
    """enrich() must set current_value = current_price * shares."""
    # TODO: implement
    # sample_holding.enrich(current_price=200.0, portfolio_total_value=100_000.0)
    # assert sample_holding.current_value == 200.0 * sample_holding.shares
    raise NotImplementedError


def test_holding_enrich_computes_unrealized_pnl(sample_holding):
    """enrich() must set unrealized_pnl = current_value - cost_basis."""
    # TODO: implement
    raise NotImplementedError


def test_holding_enrich_computes_weight(sample_holding):
    """enrich() must set weight = current_value / portfolio_total_value."""
    # TODO: implement
    raise NotImplementedError


def test_holding_enrich_handles_zero_cost(sample_holding):
    """When avg_cost == 0, unrealized_pnl_pct must be 0 (no ZeroDivisionError)."""
    # TODO: implement
    raise NotImplementedError


def test_holding_enrich_handles_zero_portfolio_value(sample_holding):
    """When portfolio_total_value == 0, weight must be 0 (no ZeroDivisionError)."""
    # TODO: implement
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Portfolio.enrich()
# ---------------------------------------------------------------------------


def test_portfolio_enrich_computes_total_value(sample_portfolio, sample_holding):
    """Portfolio.enrich() must compute total_value = cash + sum(holding.current_value)."""
    # TODO: implement
    raise NotImplementedError


def test_portfolio_enrich_computes_cash_pct(sample_portfolio, sample_holding):
    """Portfolio.enrich() must compute cash_pct = cash / total_value."""
    # TODO: implement
    raise NotImplementedError
