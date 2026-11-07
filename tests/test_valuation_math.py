"""The valuation arithmetic, checked against figures worked out by hand."""

import numpy as np
import pandas as pd
import pytest

from tradingagents.valuation import dcf, multiples, wacc
from tradingagents.valuation.wacc import ValuationError


def _weekly(returns, start="2023-01-06", level=100.0):
    dates = pd.date_range(start, periods=len(returns) + 1, freq="W-FRI")
    return pd.Series(level * np.concatenate([[1.0], np.cumprod(1 + np.asarray(returns))]), index=dates)


@pytest.mark.unit
def test_beta_is_the_slope_of_stock_returns_on_benchmark_returns():
    bench_returns = np.random.default_rng(1).normal(0.002, 0.02, 80)
    result = wacc.beta_from_closes(_weekly(1.5 * bench_returns), _weekly(bench_returns))
    assert result.beta == pytest.approx(1.5)
    assert result.weeks == 80


@pytest.mark.unit
def test_beta_refuses_too_little_history():
    bench_returns = np.random.default_rng(2).normal(0, 0.02, 20)
    with pytest.raises(ValuationError, match="at least 52 weeks"):
        wacc.beta_from_closes(_weekly(bench_returns), _weekly(bench_returns))


@pytest.mark.unit
def test_cost_of_equity_is_capm():
    # 4% + 1.2 x 5.5% = 10.6%
    assert wacc.cost_of_equity(0.04, 1.2, 0.055) == pytest.approx(0.106)


@pytest.mark.unit
def test_effective_tax_rate_is_clamped_and_falls_back_to_the_default():
    assert wacc.effective_tax_rate(20, 100, 0.21)[0] == pytest.approx(0.20)
    rate, note = wacc.effective_tax_rate(60, 100, 0.21)
    assert rate == 0.35 and "clamped" in note
    rate, note = wacc.effective_tax_rate(10, -5, 0.21)
    assert rate == 0.21 and "default" in note
    assert wacc.effective_tax_rate(None, 100, 0.21)[0] == 0.21


@pytest.mark.unit
def test_wacc_weights_equity_at_market_and_debt_at_book():
    # E=800, D=200, Ke=10%, Kd after tax 4% -> 0.8 x 10% + 0.2 x 4% = 8.8%
    kd = wacc.after_tax_cost_of_debt(interest_expense=10, total_debt=200, tax_rate=0.20)
    assert kd == pytest.approx(0.04)
    result = wacc.wacc(800, 200, 0.10, kd)
    assert result.wacc == pytest.approx(0.088)
    assert (result.equity_weight, result.debt_weight) == (pytest.approx(0.8), pytest.approx(0.2))


@pytest.mark.unit
def test_wacc_with_no_debt_is_the_cost_of_equity():
    assert wacc.after_tax_cost_of_debt(None, 200, 0.2) is None
    assert wacc.after_tax_cost_of_debt(10, 0, 0.2) is None
    result = wacc.wacc(800, 0, 0.10, None)
    assert result.wacc == pytest.approx(0.10) and result.debt_weight == 0


@pytest.mark.unit
def test_growth_fades_linearly_from_initial_to_terminal():
    assert dcf.fade_growth(0.10, 0.02, 5) == pytest.approx([0.10, 0.08, 0.06, 0.04, 0.02])


@pytest.mark.unit
def test_historical_growth_is_the_clamped_cagr_of_positive_fcf():
    growth, note = dcf.historical_growth([100, 110, 121], -0.05, 0.25)
    assert growth == pytest.approx(0.10) and "2-year" in note
    assert dcf.historical_growth([100, 200, 400], -0.05, 0.25)[0] == 0.25
    assert dcf.historical_growth([100], -0.05, 0.25)[0] is None
    assert dcf.historical_growth([-5, 10, 20], -0.05, 0.25)[0] is None


@pytest.mark.unit
def test_dcf_matches_a_hand_worked_example():
    # Base FCF 100, growth 10/8/6/4/2%, WACC 9%, terminal growth 2%, debt 300, cash 100, 50 shares.
    growth = [0.10, 0.08, 0.06, 0.04, 0.02]
    result = dcf.run_dcf(100, growth, 0.09, 0.02, total_debt=300, cash=100, shares=50)

    fcf = [110.0, 118.8, 125.928, 130.96512, 133.5844224]
    assert result.fcf == pytest.approx(fcf)
    pv = [cf / 1.09 ** t for t, cf in enumerate(fcf, start=1)]
    assert result.pv_fcf == pytest.approx(pv)
    tv = 133.5844224 * 1.02 / (0.09 - 0.02)
    assert result.terminal_value == pytest.approx(tv)
    assert result.pv_terminal == pytest.approx(tv / 1.09 ** 5)
    ev = sum(pv) + tv / 1.09 ** 5
    assert result.enterprise_value == pytest.approx(ev)
    assert result.equity_value == pytest.approx(ev - 300 + 100)
    assert result.value_per_share == pytest.approx((ev - 200) / 50)
    # EV = 477.75 + 1265.10 = 1742.85; equity = 1542.85; per share = 30.86
    assert round(result.enterprise_value, 2) == 1742.85
    assert round(result.value_per_share, 2) == 30.86


@pytest.mark.unit
def test_dcf_refuses_what_it_cannot_value():
    with pytest.raises(ValuationError, match="not positive"):
        dcf.run_dcf(-10, [0.05] * 5, 0.09, 0.02, 0, 0, 10)
    with pytest.raises(ValuationError, match="must exceed terminal growth"):
        dcf.run_dcf(100, [0.05] * 5, 0.022, 0.02, 0, 0, 10)


@pytest.mark.unit
def test_sensitivity_grid_is_5x5_centred_on_the_base_case():
    growth = dcf.fade_growth(0.08, 0.025, 5)
    base = dcf.run_dcf(100, growth, 0.09, 0.025, 300, 100, 50)
    rates, growths, grid = dcf.sensitivity(100, growth, 0.09, 0.025, 300, 100, 50)
    assert len(rates) == len(growths) == 5 and all(len(row) == 5 for row in grid)
    assert grid[2][2] == pytest.approx(base.value_per_share)
    # Higher WACC lowers the value; higher terminal growth raises it.
    assert grid[0][2] > grid[2][2] > grid[4][2]
    assert grid[2][0] < grid[2][2] < grid[2][4]


@pytest.mark.unit
def test_sensitivity_marks_cells_where_wacc_does_not_exceed_growth():
    _, _, grid = dcf.sensitivity(100, [0.05] * 5, 0.03, 0.025, 0, 0, 10)
    assert grid[0][2] is None      # WACC 1% vs terminal growth 2.5%
    assert grid[4][2] is not None


@pytest.mark.unit
def test_peer_median_ignores_missing_and_non_positive_multiples():
    assert multiples.peer_median([10, 20, 30, None, -5, 0]) == (20, 3)
    assert multiples.peer_median([None, -1]) == (None, 0)


@pytest.mark.unit
def test_implied_prices_from_peer_medians():
    target = {"eps": 5.0, "book_value_per_share": 20.0, "revenue": 1000.0, "shares": 100.0,
              "ebitda": 200.0, "total_debt": 300.0, "total_cash": 100.0}
    peers = [{"pe": 10, "ev_ebitda": 8, "ps": 1, "pb": 1.5}, {"pe": 20, "ev_ebitda": 12, "ps": 3, "pb": 2.5},
             {"pe": 30, "ev_ebitda": 10, "ps": 2, "pb": 2.0}]
    by_key = {i.multiple: i for i in multiples.implied_prices(60.0, target, peers, include_enterprise=True)}
    assert by_key["pe"].implied_price == pytest.approx(20 * 5.0)                       # 100
    assert by_key["pb"].implied_price == pytest.approx(2.0 * 20.0)                     # 40
    assert by_key["ps"].implied_price == pytest.approx(2 * 1000 / 100)                 # 20
    assert by_key["ev_ebitda"].implied_price == pytest.approx((10 * 200 - 300 + 100) / 100)  # 18
    assert by_key["pe"].own == pytest.approx(12.0)
    assert by_key["ev_ebitda"].own == pytest.approx((60 * 100 + 300 - 100) / 200)


@pytest.mark.unit
def test_implied_prices_skip_what_the_company_cannot_support():
    target = {"eps": -1.0, "book_value_per_share": 20.0, "revenue": 1000.0, "shares": 100.0}
    peers = [{"pe": 10, "pb": 2.0}] * 3
    by_key = {i.multiple: i for i in multiples.implied_prices(60.0, target, peers, include_enterprise=False)}
    assert by_key["pe"].implied_price is None and "EPS" in by_key["pe"].reason
    assert by_key["pb"].implied_price == pytest.approx(40.0)
    assert by_key["ps"].implied_price is None


@pytest.mark.unit
def test_bank_ratios_and_justified_price_to_book():
    ratios = multiples.bank_ratios(price=30.0, equity=1000.0, net_income=120.0, shares=50.0)
    assert ratios.book_value_per_share == pytest.approx(20.0)
    assert ratios.pb == pytest.approx(1.5) and ratios.pe == pytest.approx(30 / 2.4)
    assert ratios.roe == pytest.approx(0.12)
    # (12% - 3%) / (10% - 3%) = 1.2857x
    assert multiples.justified_pb(0.12, 0.10, 0.03) == pytest.approx(9 / 7)
    assert multiples.justified_pb(0.12, 0.03, 0.03) is None
