"""Portfolio weights, timing, costs, and cross-sectional safety."""

import pandas as pd
import pytest

from tradingagents.portfolio_backtest import (
    aggregate_signal_records,
    baseline_portfolios,
    beta_attribution,
    cross_sectional_rank_ic,
    permutation_placebo,
    simulate_portfolio,
    target_weights,
)


def _frame(opens, closes=None):
    dates = pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-06", "2026-07-07"])
    return pd.DataFrame({"Open": opens, "Close": closes or opens}, index=dates)


@pytest.mark.unit
def test_long_only_weights_respect_gross_and_position_caps():
    weights = target_weights(
        {"A": 1.0, "B": 0.5, "C": 0.0, "D": -1.0},
        mode="long-only", gross_limit=1.0, max_weight=0.6,
    )
    assert weights == pytest.approx({"A": 0.6, "B": 0.4, "C": 0.0, "D": 0.0})
    assert sum(abs(value) for value in weights.values()) == pytest.approx(1.0)


@pytest.mark.unit
def test_market_neutral_weights_have_balanced_long_and_short_books():
    weights = target_weights(
        {"A": 1.0, "B": 0.0, "C": -1.0},
        mode="market-neutral", gross_limit=1.0, max_weight=0.5,
    )
    assert weights == pytest.approx({"A": 0.5, "B": 0.0, "C": -0.5})
    assert sum(weights.values()) == pytest.approx(0.0)


@pytest.mark.unit
def test_market_neutral_remains_neutral_when_one_side_hits_position_caps():
    weights = target_weights(
        {"A": 1.0, "B": 0.0, "C": 0.0},
        mode="market-neutral", gross_limit=1.0, max_weight=0.25,
    )
    assert sum(weights.values()) == pytest.approx(0.0)
    assert weights == pytest.approx({"A": 0.25, "B": -0.125, "C": -0.125})


@pytest.mark.unit
def test_replicate_ratings_are_averaged_by_date_and_ticker():
    records = [
        {"decision_date": "2026-07-01", "ticker": "A", "action": "Buy"},
        {"decision_date": "2026-07-01", "ticker": "A", "action": "Hold"},
        {"decision_date": "2026-07-01", "ticker": "B", "action": "Sell"},
    ]
    assert aggregate_signal_records(records, ["A", "B"]) == {
        "2026-07-01": {"A": 0.5, "B": -1.0}
    }


@pytest.mark.unit
def test_portfolio_enters_next_open_and_charges_turnover_cost():
    result = simulate_portfolio(
        signals={"2026-07-01": {"A": 1.0, "B": 0.0}},
        prices={"A": _frame([50, 100, 110, 110]), "B": _frame([20, 20, 20, 20])},
        benchmark_prices=_frame([100, 100, 100, 100]),
        mode="long-only",
        gross_limit=1.0,
        max_weight=1.0,
        trading_cost_bps=5,
        slippage_bps=5,
        tail_sessions=1,
    )

    # The decision-day A open (50) is never used. Entry is July 2 at 100,
    # turnover costs 10 bps, then A gains 10% open-to-open.
    assert result.equity[0]["date"] == "2026-07-02"
    assert result.equity[0]["nav"] == pytest.approx(0.999)
    assert result.equity[1]["date"] == "2026-07-06"
    assert result.metrics.total_return == pytest.approx(0.0989)
    assert result.metrics.total_turnover == pytest.approx(1.0)
    assert result.metrics.rebalances == 1


@pytest.mark.unit
def test_short_book_pays_daily_borrow_cost():
    result = simulate_portfolio(
        signals={"2026-07-01": {"A": -1.0, "B": 1.0}},
        prices={"A": _frame([100, 100, 100, 100]), "B": _frame([100, 100, 100, 100])},
        benchmark_prices=_frame([100, 100, 100, 100]),
        mode="market-neutral",
        gross_limit=1.0,
        max_weight=0.5,
        trading_cost_bps=0,
        slippage_bps=0,
        annual_borrow_bps=252,
        tail_sessions=1,
    )
    assert result.metrics.estimated_borrow_cost == pytest.approx(0.00005)
    assert result.metrics.total_return == pytest.approx(-0.00005)


@pytest.mark.unit
def test_portfolio_rejects_incomplete_cross_section():
    with pytest.raises(ValueError, match="incomplete cross-section"):
        simulate_portfolio(
            signals={"2026-07-01": {"A": 1.0}},
            prices={"A": _frame([1, 1, 1, 1]), "B": _frame([1, 1, 1, 1])},
            benchmark_prices=_frame([1, 1, 1, 1]),
            max_weight=1.0,
        )


@pytest.mark.unit
def test_rank_ic_rewards_correct_cross_sectional_ordering():
    prices = {
        "A": _frame([100, 100, 120, 120], [100, 100, 120, 120]),
        "B": _frame([100, 100, 110, 110], [100, 100, 110, 110]),
        "C": _frame([100, 100, 90, 90], [100, 100, 90, 90]),
    }
    diagnostic = cross_sectional_rank_ic(
        {"2026-07-01": {"A": 1.0, "B": 0.0, "C": -1.0}},
        prices,
        holding_sessions=2,
    )
    assert diagnostic["mean_rank_ic"] == pytest.approx(1.0)
    assert diagnostic["dates"] == 1


@pytest.mark.unit
def test_beta_attribution_identifies_benchmark_exposure():
    result = simulate_portfolio(
        signals={"2026-07-01": {"A": 1.0}},
        prices={"A": _frame([100, 100, 110, 132])},
        benchmark_prices=_frame([100, 100, 110, 132]),
        max_weight=1.0,
        trading_cost_bps=0,
        slippage_bps=0,
        tail_sessions=2,
    )
    attribution = beta_attribution(result)
    assert attribution["beta"] == pytest.approx(1.0)
    assert attribution["annualized_residual_alpha"] == pytest.approx(0.0)


@pytest.mark.unit
def test_ticker_permutation_placebo_is_deterministic():
    prices = {
        "A": _frame([100, 100, 120, 120]),
        "B": _frame([100, 100, 100, 100]),
    }
    kwargs = {
        "max_weight": 1.0,
        "trading_cost_bps": 0,
        "slippage_bps": 0,
        "tail_sessions": 1,
    }
    payload = {
        "signals": {"2026-07-01": {"A": 1.0, "B": 0.0}},
        "prices": prices,
        "benchmark_prices": _frame([100, 100, 100, 100]),
        "observed_return": 0.2,
        "trials": 10,
        "seed": 7,
        "simulation_kwargs": kwargs,
    }
    assert permutation_placebo(**payload) == permutation_placebo(**payload)
    assert permutation_placebo(**payload)["trials"] == 10


@pytest.mark.unit
def test_baselines_use_same_execution_and_cost_model():
    prices = {
        "A": _frame([100, 100, 110, 110]),
        "B": _frame([100, 100, 100, 100]),
    }
    baselines = baseline_portfolios(
        signals={"2026-07-01": {"A": 1.0, "B": 0.0}},
        prices=prices,
        benchmark_prices=_frame([100, 100, 100, 100]),
        observed_return=0.10,
        momentum_lookback_sessions=1,
        simulation_kwargs={
            "max_weight": 0.5,
            "trading_cost_bps": 0,
            "slippage_bps": 0,
            "tail_sessions": 1,
        },
    )
    assert baselines["equal_weight"]["total_return"] == pytest.approx(0.05)
    assert baselines["equal_weight"]["observed_minus_baseline_return"] == pytest.approx(0.05)
