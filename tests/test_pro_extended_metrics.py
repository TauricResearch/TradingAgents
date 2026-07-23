"""Extended analytics (roadmap P5 / track T6): annualized return, Omega,
Ulcer index, MAR — derived from the equity curve and attached to every
PerformanceReport (additive, defaults keep old records/tests valid)."""

import math

import pytest

from tradingagents.pro.backtest import (
    annualized_return,
    mar_ratio,
    omega_ratio,
    performance_report,
    rolling_sharpe,
    ulcer_index,
)


class TestAnnualizedReturn:
    def test_doubling_over_one_year_of_daily_bars(self):
        # 253 points = 252 periods = 1 year; 100 → 200 ⇒ ~100% CAGR
        curve = [100.0 + 100.0 * i / 252 for i in range(253)]
        assert annualized_return(curve, periods_per_year=252) == pytest.approx(1.0, abs=0.02)

    def test_guards_wipeout_and_short_series(self):
        assert annualized_return([100.0], 252) == 0.0
        assert annualized_return([100.0, 0.0], 252) == 0.0  # terminal <= 0


class TestOmega:
    def test_all_gains_no_losses_is_infinite(self):
        assert omega_ratio([0.01, 0.02, 0.03]) == float("inf")

    def test_symmetric_returns_are_about_one(self):
        assert omega_ratio([0.01, -0.01, 0.01, -0.01]) == pytest.approx(1.0)

    def test_more_upside_mass_exceeds_one(self):
        assert omega_ratio([0.03, -0.01, 0.02, -0.01]) > 1.0


class TestUlcer:
    def test_monotonic_rise_has_zero_ulcer(self):
        assert ulcer_index([100, 101, 102, 103]) == 0.0

    def test_drawdown_produces_positive_ulcer(self):
        # dips to 80 (20% dd) then recovers → positive RMS drawdown
        ui = ulcer_index([100, 80, 100, 100])
        assert ui > 0
        assert ui == pytest.approx(math.sqrt((20.0 ** 2) / 4), abs=1e-9)


class TestMar:
    def test_return_over_drawdown(self):
        curve = [100.0 + 100.0 * i / 252 for i in range(253)]  # ~100% CAGR, ~0 dd
        # monotonic rise → no drawdown → guarded to 0
        assert mar_ratio(curve, 252) == 0.0

    def test_positive_when_there_is_a_drawdown(self):
        curve = [100.0 * (1.02 ** i) for i in range(253)]
        curve[130] = curve[129] * 0.9  # inject a dip → real drawdown
        m = mar_ratio(curve, 252)
        assert m > 0


class TestRollingSharpe:
    def test_windowed_length_and_short_series(self):
        returns = [0.01, -0.005, 0.02, -0.01, 0.015, -0.008, 0.012]
        roll = rolling_sharpe(returns, window=3, periods_per_year=252)
        assert len(roll) == len(returns) - 3 + 1
        assert rolling_sharpe([0.01, 0.02], window=5) == []  # too short

    def test_steady_positive_edge_is_stable(self):
        # a consistently rising curve → most rolling windows have Sharpe > 0
        curve = [100.0 * (1.01 ** i) for i in range(80)]
        report = performance_report(curve, trades=[], periods_per_year=252)
        assert report.sharpe_stability > 0.9


def test_report_carries_the_extended_metrics():
    curve = [100.0 * (1.01 ** i) for i in range(60)]
    report = performance_report(curve, trades=[], periods_per_year=252)
    d = report.as_dict()
    for key in ("annualized_return", "omega", "ulcer_index", "mar", "sharpe_stability"):
        assert key in d
    assert d["annualized_return"] > 0  # a rising curve compounds positive
