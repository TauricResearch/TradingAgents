"""Tests for tradingagents/portfolio/risk_evaluator.py.

All pure Python — no mocks, no DB, no network calls.

Run::

    pytest tests/portfolio/test_risk_evaluator.py -v
"""

from __future__ import annotations

import math

import pytest

from tradingagents.portfolio.models import Holding, Portfolio
from tradingagents.portfolio.risk_evaluator import (
    beta,
    check_constraints,
    compute_portfolio_risk,
    compute_returns,
    max_drawdown,
    sector_concentration,
    sharpe_ratio,
    sortino_ratio,
    value_at_risk,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_holding(ticker, shares=10.0, avg_cost=100.0, sector=None, current_value=None):
    h = Holding(
        holding_id="h-" + ticker,
        portfolio_id="p1",
        ticker=ticker,
        shares=shares,
        avg_cost=avg_cost,
        sector=sector,
    )
    h.current_value = current_value
    return h


def _make_portfolio(cash=50_000.0, total_value=None):
    p = Portfolio(
        portfolio_id="p1",
        name="Test",
        cash=cash,
        initial_cash=100_000.0,
    )
    p.total_value = total_value or cash
    p.equity_value = 0.0
    p.cash_pct = 1.0
    return p


# ---------------------------------------------------------------------------
# compute_returns
# ---------------------------------------------------------------------------


def test_compute_returns_basic():
    """[100, 110] → one return ≈ ln(110/100) ≈ 0.0953."""
    result = compute_returns([100.0, 110.0])
    assert len(result) == 1
    assert abs(result[0] - math.log(110 / 100)) < 1e-9


def test_compute_returns_insufficient():
    """Single price → empty list."""
    assert compute_returns([100.0]) == []


def test_compute_returns_empty():
    assert compute_returns([]) == []


def test_compute_returns_three_prices():
    prices = [100.0, 110.0, 121.0]
    result = compute_returns(prices)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# sharpe_ratio
# ---------------------------------------------------------------------------


def test_sharpe_ratio_basic():
    """Positive varying returns → finite Sharpe value."""
    returns = [0.01, 0.02, -0.005, 0.015, 0.01, 0.02, -0.01, 0.015, 0.01, 0.02] * 3
    result = sharpe_ratio(returns)
    assert result is not None
    assert math.isfinite(result)


def test_sharpe_ratio_zero_std():
    """All identical returns → None (division by zero)."""
    # All same value → stdev = 0
    returns = [0.005] * 20
    result = sharpe_ratio(returns)
    assert result is None


def test_sharpe_ratio_insufficient():
    assert sharpe_ratio([0.01]) is None
    assert sharpe_ratio([]) is None


# ---------------------------------------------------------------------------
# sortino_ratio
# ---------------------------------------------------------------------------


def test_sortino_ratio_mixed():
    """Mix of positive and negative returns → finite Sortino value."""
    returns = [0.02, -0.01, 0.015, -0.005, 0.01, -0.02, 0.025]
    result = sortino_ratio(returns)
    assert result is not None
    assert math.isfinite(result)


def test_sortino_ratio_all_positive():
    """No downside returns → None."""
    returns = [0.01, 0.02, 0.03]
    assert sortino_ratio(returns) is None


# ---------------------------------------------------------------------------
# value_at_risk
# ---------------------------------------------------------------------------


def test_value_at_risk():
    """5th percentile of sorted returns."""
    returns = list(range(-10, 10))  # -10 ... 9
    result = value_at_risk(returns, percentile=0.05)
    assert result is not None
    assert result <= -9  # should be in the tail


def test_value_at_risk_empty():
    assert value_at_risk([]) is None


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------


def test_max_drawdown_decline():
    """[100, 90, 80] → 20% drawdown."""
    result = max_drawdown([100.0, 90.0, 80.0])
    assert result is not None
    assert abs(result - 0.2) < 1e-9


def test_max_drawdown_recovery():
    """[100, 80, 110] → 20% drawdown (peak 100 → trough 80)."""
    result = max_drawdown([100.0, 80.0, 110.0])
    assert result is not None
    assert abs(result - 0.2) < 1e-9


def test_max_drawdown_no_drawdown():
    """Monotonically rising series → 0 drawdown."""
    result = max_drawdown([100.0, 110.0, 120.0])
    assert result == 0.0


def test_max_drawdown_insufficient():
    assert max_drawdown([100.0]) is None
    assert max_drawdown([]) is None


# ---------------------------------------------------------------------------
# beta
# ---------------------------------------------------------------------------


def test_beta_positive_correlation():
    """Asset moves identically to benchmark → beta ≈ 1.0."""
    returns = [0.01, -0.02, 0.015, -0.005, 0.02]
    result = beta(returns, returns)
    assert result is not None
    assert abs(result - 1.0) < 1e-9


def test_beta_zero_benchmark_variance():
    """Flat benchmark → None."""
    asset = [0.01, 0.02, 0.03]
    bm = [0.0, 0.0, 0.0]
    assert beta(asset, bm) is None


def test_beta_length_mismatch():
    assert beta([0.01, 0.02], [0.01]) is None


# ---------------------------------------------------------------------------
# sector_concentration
# ---------------------------------------------------------------------------


def test_sector_concentration_single():
    """One sector holding occupies its share of total value."""
    h = _make_holding("AAPL", shares=10, avg_cost=100, sector="Technology")
    result = sector_concentration([h], portfolio_total_value=1000.0)
    assert "Technology" in result
    assert abs(result["Technology"] - 1.0) < 1e-9


def test_sector_concentration_multi():
    """Two sectors → proportional fractions summing to < 1 (cash excluded)."""
    h1 = _make_holding("AAPL", shares=10, avg_cost=100, sector="Technology")  # 1000
    h2 = _make_holding("JPM", shares=5, avg_cost=100, sector="Financials")    # 500
    result = sector_concentration([h1, h2], portfolio_total_value=2000.0)
    assert abs(result["Technology"] - 0.5) < 1e-9
    assert abs(result["Financials"] - 0.25) < 1e-9


def test_sector_concentration_unknown_sector():
    """Holding with no sector → bucketed as 'Unknown'."""
    h = _make_holding("XYZ", shares=10, avg_cost=100, sector=None)
    result = sector_concentration([h], portfolio_total_value=1000.0)
    assert "Unknown" in result


def test_sector_concentration_zero_total():
    """Zero portfolio value → empty dict."""
    h = _make_holding("AAPL", shares=10, avg_cost=100, sector="Technology")
    result = sector_concentration([h], portfolio_total_value=0.0)
    assert result == {}


# ---------------------------------------------------------------------------
# check_constraints
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "max_positions": 3,
    "max_position_pct": 0.20,
    "max_sector_pct": 0.40,
    "min_cash_pct": 0.05,
}


def test_check_constraints_clean():
    """No violations when portfolio is within limits."""
    p = _make_portfolio(cash=9_000.0, total_value=10_000.0)
    h = _make_holding("AAPL", shares=10, avg_cost=100, sector="Technology")
    h.current_value = 1000.0
    violations = check_constraints(p, [h], _DEFAULT_CONFIG)
    assert violations == []


def test_check_constraints_max_positions():
    """Adding a 4th distinct position to a max-3 portfolio → violation."""
    p = _make_portfolio(cash=5_000.0, total_value=8_000.0)
    holdings = [
        _make_holding("AAPL", sector="Technology"),
        _make_holding("MSFT", sector="Technology"),
        _make_holding("GOOG", sector="Technology"),
    ]
    violations = check_constraints(
        p, holdings, _DEFAULT_CONFIG,
        new_ticker="AMZN", new_shares=5, new_price=200, new_sector="Technology"
    )
    assert any("Max positions" in v for v in violations)


def test_check_constraints_min_cash():
    """BUY that would drain cash below 5 % → violation."""
    p = _make_portfolio(cash=500.0, total_value=10_000.0)
    violations = check_constraints(
        p, [], _DEFAULT_CONFIG,
        new_ticker="AAPL", new_shares=2, new_price=200, new_sector="Technology"
    )
    assert any("Min cash" in v for v in violations)


def test_check_constraints_max_position_size():
    """BUY that would exceed 20 % position limit → violation."""
    p = _make_portfolio(cash=9_000.0, total_value=10_000.0)
    # Buying 25 % worth of total_value
    violations = check_constraints(
        p, [], _DEFAULT_CONFIG,
        new_ticker="AAPL", new_shares=25, new_price=100, new_sector="Technology"
    )
    assert any("Max position size" in v for v in violations)


# ---------------------------------------------------------------------------
# compute_portfolio_risk
# ---------------------------------------------------------------------------


def test_compute_portfolio_risk_empty():
    """No holdings → should not raise, returns structure with None metrics."""
    p = _make_portfolio(cash=100_000.0, total_value=100_000.0)
    result = compute_portfolio_risk(p, [], {})
    assert "portfolio_sharpe" in result
    assert result["num_positions"] == 0


def test_compute_portfolio_risk_single_holding():
    """Single holding with price history → computes holding metrics."""
    p = _make_portfolio(cash=5_000.0, total_value=6_000.0)
    h = _make_holding("AAPL", shares=10, avg_cost=100, sector="Technology")
    h.current_value = 1000.0
    prices = [100.0, 102.0, 99.0, 105.0, 108.0]
    result = compute_portfolio_risk(p, [h], {"AAPL": prices})
    assert result["num_positions"] == 1
    assert len(result["holdings"]) == 1
    assert result["holdings"][0]["ticker"] == "AAPL"
