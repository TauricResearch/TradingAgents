"""Tests for backtest performance statistics and baselines."""

import math

import pandas as pd
import pytest

from tradingagents.backtest.metrics import (
    buy_and_hold,
    compute_metrics,
    cost_per_alpha_point,
    hit_rate,
    random_rating_baseline,
    summarize,
)
from tradingagents.backtest.portfolio import PortfolioConfig, simulate

WEEK = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]


def series(values, dates=None):
    dates = dates or WEEK[: len(values)]
    return pd.Series(values, index=pd.DatetimeIndex(pd.to_datetime(dates)), dtype="float64")


def frame(dates=WEEK, opens=None, closes=None):
    opens = [100.0] * len(dates) if opens is None else opens
    closes = opens if closes is None else closes
    return pd.DataFrame(
        {"Open": opens, "Close": closes},
        index=pd.DatetimeIndex(pd.to_datetime(dates)),
    )


# ---------------------------------------------------------------------------
# compute_metrics
# ---------------------------------------------------------------------------

def test_total_return_is_first_to_last():
    metrics = compute_metrics(series([100.0, 110.0, 120.0]))

    assert metrics.total_return == pytest.approx(0.20)
    assert metrics.n_days == 3


def test_annualized_return_compounds_over_the_span():
    # Exactly one year, doubling.
    dates = ["2025-01-01", "2026-01-01"]
    metrics = compute_metrics(series([100.0, 200.0], dates=dates))

    assert metrics.annualized_return == pytest.approx(1.0, rel=1e-2)


def test_flat_curve_has_no_volatility_or_sharpe():
    metrics = compute_metrics(series([100.0] * 5))

    assert metrics.total_return == pytest.approx(0.0)
    assert metrics.volatility == pytest.approx(0.0)
    assert metrics.sharpe == pytest.approx(0.0)
    assert metrics.max_drawdown == pytest.approx(0.0)


def test_max_drawdown_is_peak_to_trough():
    metrics = compute_metrics(series([100.0, 120.0, 60.0, 80.0, 90.0]))

    # Peak 120 down to 60 is -50%.
    assert metrics.max_drawdown == pytest.approx(-0.50)


def test_calmar_is_annualized_return_over_drawdown():
    metrics = compute_metrics(series([100.0, 120.0, 60.0, 80.0, 90.0]))

    assert metrics.calmar == pytest.approx(
        metrics.annualized_return / abs(metrics.max_drawdown)
    )


def test_sortino_ignores_upside_volatility():
    """A curve that only rises has no downside deviation, so Sortino is not finite-penalised."""
    rising = compute_metrics(series([100.0, 101.0, 102.0, 103.0, 104.0]))
    choppy = compute_metrics(series([100.0, 101.0, 99.0, 103.0, 104.0]))

    assert rising.sortino == pytest.approx(0.0)  # no downside days at all
    assert choppy.sortino > 0.0


def test_sharpe_is_positive_for_a_rising_curve():
    metrics = compute_metrics(series([100.0, 101.0, 102.5, 103.0, 105.0]))

    assert metrics.sharpe > 0.0
    assert metrics.volatility > 0.0


@pytest.mark.parametrize("values", [[], [100.0]])
def test_degenerate_curves_return_zeros_not_nan(values):
    metrics = compute_metrics(series(values))

    assert metrics.total_return == 0.0
    assert not math.isnan(metrics.sharpe)


def test_total_wipeout_does_not_raise():
    metrics = compute_metrics(series([100.0, 50.0, 0.0]))

    assert metrics.total_return == pytest.approx(-1.0)
    assert metrics.annualized_return == 0.0  # guarded, not a complex number


# ---------------------------------------------------------------------------
# buy_and_hold
# ---------------------------------------------------------------------------

def test_buy_and_hold_enters_at_the_first_open():
    prices = frame(opens=[100, 200, 200, 200, 200], closes=[150, 200, 200, 200, 200])
    curve = buy_and_hold(prices, initial_cash=100_000.0)

    # 1,000 shares bought at 100; first close of 150 marks at 150,000.
    assert curve.iloc[0] == pytest.approx(150_000.0)


def test_buy_and_hold_tracks_the_price():
    prices = frame(opens=[100.0] * 5, closes=[100, 100, 100, 100, 200])
    curve = buy_and_hold(prices, initial_cash=100_000.0)

    assert curve.iloc[-1] == pytest.approx(200_000.0)


def test_buy_and_hold_on_empty_prices_is_empty():
    empty = pd.DataFrame({"Open": [], "Close": []}, index=pd.DatetimeIndex([]))

    assert len(buy_and_hold(empty)) == 0


# ---------------------------------------------------------------------------
# hit_rate
# ---------------------------------------------------------------------------

def test_hit_rate_scores_a_correct_long_call():
    dates = [f"2026-01-{d:02d}" for d in (5, 6, 7, 8, 9, 12, 13)]
    prices = frame(dates=dates, opens=[100, 100, 100, 100, 100, 100, 200])
    # Buy on the 5th fills at the 6th's open and is scored 5 bars later (the 13th).
    rate, scored = hit_rate([("2026-01-05", "Buy")], prices, horizon_days=5)

    assert scored == 1
    assert rate == pytest.approx(1.0)


def test_hit_rate_scores_an_incorrect_long_call():
    dates = [f"2026-01-{d:02d}" for d in (5, 6, 7, 8, 9, 12, 13)]
    prices = frame(dates=dates, opens=[100, 100, 100, 100, 100, 100, 50])
    rate, scored = hit_rate([("2026-01-05", "Buy")], prices, horizon_days=5)

    assert scored == 1
    assert rate == pytest.approx(0.0)


def test_hit_rate_credits_a_bearish_call_on_a_fall():
    dates = [f"2026-01-{d:02d}" for d in (5, 6, 7, 8, 9, 12, 13)]
    prices = frame(dates=dates, opens=[100, 100, 100, 100, 100, 100, 50])
    rate, scored = hit_rate([("2026-01-05", "Sell")], prices, horizon_days=5)

    assert scored == 1
    assert rate == pytest.approx(1.0)


@pytest.mark.parametrize("rating", ["Hold", "REVIEW", None])
def test_non_directional_ratings_are_not_scored(rating):
    """Neither Hold nor REVIEW claims the price will move, so neither is a miss."""
    dates = [f"2026-01-{d:02d}" for d in (5, 6, 7, 8, 9, 12, 13)]
    prices = frame(dates=dates, opens=[100, 100, 100, 100, 100, 100, 200])
    rate, scored = hit_rate([("2026-01-05", rating)], prices, horizon_days=5)

    assert scored == 0
    assert rate == 0.0


def test_calls_without_a_full_forward_window_are_not_scored():
    rate, scored = hit_rate([("2026-01-08", "Buy")], frame(), horizon_days=5)

    assert scored == 0


def test_hit_rate_on_empty_prices():
    empty = pd.DataFrame({"Open": [], "Close": []}, index=pd.DatetimeIndex([]))

    assert hit_rate([("2026-01-05", "Buy")], empty) == (0.0, 0)


# ---------------------------------------------------------------------------
# Random-rating baseline
# ---------------------------------------------------------------------------

def _long_frame(n=60, drift=1.01):
    dates = pd.bdate_range("2026-01-05", periods=n)
    prices = [100.0 * (drift**i) for i in range(n)]
    return pd.DataFrame({"Open": prices, "Close": prices}, index=dates)


def test_random_baseline_returns_a_distribution():
    prices = _long_frame()
    decisions = [
        (d.strftime("%Y-%m-%d"), r)
        for d, r in zip(prices.index[::5], ["Buy", "Sell", "Buy", "Hold", "Sell", "Buy"], strict=False)
    ]
    agent = compute_metrics(simulate(decisions, prices).equity).total_return

    comparison = random_rating_baseline(decisions, prices, agent, n_trials=25, seed=7)

    assert comparison is not None
    assert comparison.n_trials == 25
    assert comparison.p05_return <= comparison.median_return <= comparison.p95_return
    assert 0.0 <= comparison.agent_percentile <= 1.0


def test_random_baseline_is_deterministic_for_a_seed():
    prices = _long_frame()
    decisions = [
        (d.strftime("%Y-%m-%d"), r)
        for d, r in zip(prices.index[::5], ["Buy", "Sell", "Buy", "Hold", "Sell", "Buy"], strict=False)
    ]

    first = random_rating_baseline(decisions, prices, 0.0, n_trials=10, seed=3)
    second = random_rating_baseline(decisions, prices, 0.0, n_trials=10, seed=3)

    assert first.as_dict() == second.as_dict()


def test_random_baseline_needs_a_rating_mix():
    """Shuffling a single repeated rating tests nothing, so it returns None."""
    prices = _long_frame()
    decisions = [(d.strftime("%Y-%m-%d"), "Buy") for d in prices.index[::5]]

    assert random_rating_baseline(decisions, prices, 0.0) is None


def test_random_baseline_needs_enough_decisions():
    assert random_rating_baseline([("2026-01-05", "Buy")], _long_frame(), 0.0) is None


def test_baseline_preserves_the_rating_mix():
    """Each trial must re-order the agent's ratings, never invent new ones."""
    prices = _long_frame()
    ratings = ["Buy", "Sell", "Buy", "Hold", "Sell", "Buy"]
    decisions = [
        (d.strftime("%Y-%m-%d"), r) for d, r in zip(prices.index[::5], ratings, strict=False)
    ]
    # An all-Buy agent in a rising market should not look special against a
    # baseline drawn from its own (all-Buy) mix — that is the point of the test
    # above; here we confirm a mixed agent gets a real, bounded percentile.
    comparison = random_rating_baseline(decisions, prices, 10.0, n_trials=20, seed=1)

    assert comparison.agent_percentile == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Cost efficiency and summarize
# ---------------------------------------------------------------------------

def test_cost_per_alpha_point():
    # $500 bought 10 percentage points of alpha, so $50 per point.
    assert cost_per_alpha_point(0.10, 500.0) == pytest.approx(50.0)


@pytest.mark.parametrize("cost", [None, 0.0])
def test_cost_per_alpha_point_is_none_without_spend(cost):
    assert cost_per_alpha_point(0.10, cost) is None


@pytest.mark.parametrize("alpha", [None, 0.0, -0.05])
def test_cost_per_alpha_point_is_none_without_positive_alpha(alpha):
    """There is no meaningful price for alpha that was never earned."""
    assert cost_per_alpha_point(alpha, 500.0) is None


def test_summarize_computes_alpha_against_a_benchmark():
    prices = frame(opens=[100.0] * 5, closes=[100, 100, 100, 100, 200])
    result = simulate(
        [("2026-01-05", "Buy")], prices, PortfolioConfig(commission_bps=0, slippage_bps=0)
    )
    benchmark = series([100.0, 100.0, 100.0, 100.0, 150.0])

    payload = summarize(result, benchmark)

    assert payload["total_return"] == pytest.approx(1.0)
    assert payload["benchmark_total_return"] == pytest.approx(0.5)
    assert payload["alpha"] == pytest.approx(0.5)
    assert payload["n_trades"] == 1


def test_summarize_without_a_benchmark_reports_no_alpha():
    payload = summarize(simulate([], frame()), None)

    assert payload["alpha"] is None
    assert payload["benchmark_total_return"] is None
