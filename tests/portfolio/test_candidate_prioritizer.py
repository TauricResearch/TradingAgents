"""Tests for tradingagents/portfolio/candidate_prioritizer.py.

All pure Python — no mocks, no DB, no network calls.

Run::

    pytest tests/portfolio/test_candidate_prioritizer.py -v
"""

from __future__ import annotations

import pytest

from tradingagents.portfolio.models import Holding, Portfolio
from tradingagents.portfolio.candidate_prioritizer import (
    prioritize_candidates,
    score_candidate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_holding(ticker, shares=10.0, avg_cost=100.0, sector="Technology", current_value=None):
    h = Holding(
        holding_id="h-" + ticker,
        portfolio_id="p1",
        ticker=ticker,
        shares=shares,
        avg_cost=avg_cost,
        sector=sector,
    )
    h.current_value = current_value or shares * avg_cost
    return h


def _make_portfolio(cash=50_000.0, total_value=100_000.0):
    p = Portfolio(
        portfolio_id="p1",
        name="Test",
        cash=cash,
        initial_cash=100_000.0,
    )
    p.total_value = total_value
    p.equity_value = total_value - cash
    p.cash_pct = cash / total_value
    return p


_DEFAULT_CONFIG = {
    "max_positions": 15,
    "max_position_pct": 0.15,
    "max_sector_pct": 0.35,
    "min_cash_pct": 0.05,
}


def _make_candidate(
    ticker="AAPL",
    conviction="high",
    thesis_angle="growth",
    sector="Healthcare",
):
    return {
        "ticker": ticker,
        "conviction": conviction,
        "thesis_angle": thesis_angle,
        "sector": sector,
        "rationale": "Strong fundamentals",
    }


# ---------------------------------------------------------------------------
# score_candidate
# ---------------------------------------------------------------------------


def test_score_high_conviction_growth_new_sector():
    """high * growth * new_sector * not_held = 3*3*2*1 = 18."""
    candidate = _make_candidate(conviction="high", thesis_angle="growth", sector="Healthcare")
    portfolio = _make_portfolio(cash=50_000.0, total_value=100_000.0)
    result = score_candidate(candidate, [], portfolio.total_value, _DEFAULT_CONFIG)
    assert result == pytest.approx(18.0)


def test_score_already_held_penalty():
    """Penalty of 0.5 when ticker already in holdings."""
    candidate = _make_candidate(ticker="AAPL", conviction="high", thesis_angle="growth", sector="Healthcare")
    holdings = [_make_holding("AAPL", sector="Technology")]
    portfolio = _make_portfolio(cash=50_000.0, total_value=100_000.0)
    # score = 3 * 3 * 2 * 0.5 = 9
    result = score_candidate(candidate, holdings, portfolio.total_value, _DEFAULT_CONFIG)
    assert result == pytest.approx(9.0)


def test_score_zero_for_max_sector():
    """Sector at max exposure → diversification_factor = 0 → score = 0."""
    # Make Technology = 40% of 100k → 40_000 value in Technology
    h1 = _make_holding("AAPL", shares=200, avg_cost=100, sector="Technology", current_value=20_000)
    h2 = _make_holding("MSFT", shares=200, avg_cost=100, sector="Technology", current_value=20_000)
    candidate = _make_candidate(conviction="high", thesis_angle="growth", sector="Technology")
    result = score_candidate(candidate, [h1, h2], 100_000.0, _DEFAULT_CONFIG)
    assert result == pytest.approx(0.0)


def test_score_low_conviction_defensive():
    """low * defensive * new_sector * not_held = 1*1*2*1 = 2."""
    candidate = _make_candidate(conviction="low", thesis_angle="defensive", sector="Utilities")
    result = score_candidate(candidate, [], 100_000.0, _DEFAULT_CONFIG)
    assert result == pytest.approx(2.0)


def test_score_medium_momentum_existing_sector_under_70pct():
    """medium * momentum * under_70pct_of_max * not_held = 2*2.5*1*1 = 5."""
    # Technology at 10% of 100k → under 70% of 35% max (24.5%)
    h = _make_holding("AAPL", shares=100, avg_cost=100, sector="Technology", current_value=10_000)
    # Use a different ticker so it's not already held
    candidate = _make_candidate("GOOG", conviction="medium", thesis_angle="momentum", sector="Technology")
    result = score_candidate(candidate, [h], 100_000.0, _DEFAULT_CONFIG)
    assert result == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# prioritize_candidates
# ---------------------------------------------------------------------------


def test_prioritize_candidates_sorted():
    """Results are sorted by priority_score descending."""
    candidates = [
        _make_candidate("LOW", conviction="low", thesis_angle="defensive", sector="Utilities"),
        _make_candidate("HIGH", conviction="high", thesis_angle="growth", sector="Healthcare"),
        _make_candidate("MED", conviction="medium", thesis_angle="value", sector="Financials"),
    ]
    portfolio = _make_portfolio()
    result = prioritize_candidates(candidates, portfolio, [], _DEFAULT_CONFIG)
    scores = [r["priority_score"] for r in result]
    assert scores == sorted(scores, reverse=True)


def test_prioritize_candidates_top_n():
    """top_n=2 returns only 2 candidates."""
    candidates = [
        _make_candidate("A", conviction="high", thesis_angle="growth", sector="Healthcare"),
        _make_candidate("B", conviction="medium", thesis_angle="value", sector="Financials"),
        _make_candidate("C", conviction="low", thesis_angle="defensive", sector="Utilities"),
    ]
    portfolio = _make_portfolio()
    result = prioritize_candidates(candidates, portfolio, [], _DEFAULT_CONFIG, top_n=2)
    assert len(result) == 2


def test_prioritize_candidates_empty():
    """Empty candidates list → empty result."""
    portfolio = _make_portfolio()
    result = prioritize_candidates([], portfolio, [], _DEFAULT_CONFIG)
    assert result == []


def test_prioritize_candidates_adds_priority_score():
    """Every returned candidate has a priority_score field."""
    candidates = [
        _make_candidate("AAPL", conviction="high", thesis_angle="growth", sector="Technology"),
    ]
    portfolio = _make_portfolio()
    result = prioritize_candidates(candidates, portfolio, [], _DEFAULT_CONFIG)
    assert len(result) == 1
    assert "priority_score" in result[0]
    assert isinstance(result[0]["priority_score"], float)


def test_prioritize_candidates_skip_reason_for_zero_score():
    """Candidates with zero score (sector at max) receive a skip_reason."""
    # Fill Technology to 40% → at max
    h1 = _make_holding("AAPL", shares=200, avg_cost=100, sector="Technology", current_value=20_000)
    h2 = _make_holding("MSFT", shares=200, avg_cost=100, sector="Technology", current_value=20_000)
    candidates = [
        _make_candidate("GOOG", conviction="high", thesis_angle="growth", sector="Technology"),
    ]
    portfolio = _make_portfolio(cash=60_000.0, total_value=100_000.0)
    result = prioritize_candidates(candidates, portfolio, [h1, h2], _DEFAULT_CONFIG)
    assert len(result) == 1
    assert result[0]["priority_score"] == pytest.approx(0.0)
    assert "skip_reason" in result[0]
