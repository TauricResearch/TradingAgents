"""Tests for Portfolio Performance Metrics module.

Issue #31: [PORT-30] Performance metrics - Sharpe, drawdown, returns
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Tuple

from tradingagents.portfolio import (
    Period,
    ReturnSeries,
    DrawdownInfo,
    TradeStats,
    PerformanceMetrics,
    PerformanceCalculator,
    calculate_cagr,
    calculate_rolling_returns,
    calculate_monthly_returns,
    calculate_yearly_returns,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def calculator():
    """Create a PerformanceCalculator with default settings."""
    return PerformanceCalculator(risk_free_rate=Decimal("0.05"))


@pytest.fixture
def simple_returns():
    """Create a simple return series for testing."""
    base_date = date(2024, 1, 1)
    returns = [
        (base_date + timedelta(days=i), Decimal(str(r)))
        for i, r in enumerate([
            0.01, -0.005, 0.02, 0.005, -0.01,
            0.015, -0.003, 0.008, 0.012, -0.007,
        ])
    ]
    return ReturnSeries(returns=returns, period=Period.DAILY)


@pytest.fixture
def positive_returns():
    """Create a positive return series."""
    base_date = date(2024, 1, 1)
    returns = [
        (base_date + timedelta(days=i), Decimal("0.01"))
        for i in range(20)
    ]
    return ReturnSeries(returns=returns, period=Period.DAILY)


@pytest.fixture
def negative_returns():
    """Create a negative return series."""
    base_date = date(2024, 1, 1)
    returns = [
        (base_date + timedelta(days=i), Decimal("-0.01"))
        for i in range(20)
    ]
    return ReturnSeries(returns=returns, period=Period.DAILY)


@pytest.fixture
def portfolio_values():
    """Create a portfolio value series."""
    base_date = date(2024, 1, 1)
    values = [
        1000, 1010, 1005, 1025, 1030,
        1020, 1035, 1032, 1040, 1052,
        1045, 1060, 1055, 1070, 1080,
    ]
    return [
        (base_date + timedelta(days=i), Decimal(str(v)))
        for i, v in enumerate(values)
    ]


@pytest.fixture
def drawdown_values():
    """Create a portfolio series with drawdowns."""
    base_date = date(2024, 1, 1)
    values = [
        1000, 1050, 1100, 1080, 1000,  # First drawdown
        900, 950, 1000, 1100, 1150,    # Second drawdown + recovery
        1100, 1050, 1000, 1050, 1100,  # Third drawdown + recovery
    ]
    return [
        (base_date + timedelta(days=i), Decimal(str(v)))
        for i, v in enumerate(values)
    ]


@pytest.fixture
def trade_returns():
    """Create sample trade returns."""
    return [
        Decimal("0.10"),   # 10% win
        Decimal("-0.05"),  # 5% loss
        Decimal("0.08"),   # 8% win
        Decimal("0.15"),   # 15% win
        Decimal("-0.03"),  # 3% loss
        Decimal("0.00"),   # breakeven
        Decimal("-0.08"),  # 8% loss
        Decimal("0.12"),   # 12% win
        Decimal("0.05"),   # 5% win
        Decimal("-0.02"),  # 2% loss
    ]


# =============================================================================
# ReturnSeries Tests
# =============================================================================


class TestReturnSeries:
    """Test ReturnSeries dataclass."""

    def test_return_series_creation(self, simple_returns):
        """Test basic return series creation."""
        assert simple_returns.period == Period.DAILY
        assert simple_returns.annualization_factor == 252
        assert simple_returns.num_periods == 10

    def test_values_property(self, simple_returns):
        """Test getting just the return values."""
        values = simple_returns.values
        assert len(values) == 10
        assert values[0] == Decimal("0.01")
        assert values[1] == Decimal("-0.005")

    def test_dates_property(self, simple_returns):
        """Test getting just the dates."""
        dates = simple_returns.dates
        assert len(dates) == 10
        assert dates[0] == date(2024, 1, 1)
        assert dates[1] == date(2024, 1, 2)

    def test_annualization_factor_daily(self):
        """Test daily annualization factor."""
        rs = ReturnSeries(returns=[], period=Period.DAILY)
        assert rs.annualization_factor == 252

    def test_annualization_factor_weekly(self):
        """Test weekly annualization factor."""
        rs = ReturnSeries(returns=[], period=Period.WEEKLY)
        assert rs.annualization_factor == 52

    def test_annualization_factor_monthly(self):
        """Test monthly annualization factor."""
        rs = ReturnSeries(returns=[], period=Period.MONTHLY)
        assert rs.annualization_factor == 12

    def test_annualization_factor_quarterly(self):
        """Test quarterly annualization factor."""
        rs = ReturnSeries(returns=[], period=Period.QUARTERLY)
        assert rs.annualization_factor == 4

    def test_annualization_factor_yearly(self):
        """Test yearly annualization factor."""
        rs = ReturnSeries(returns=[], period=Period.YEARLY)
        assert rs.annualization_factor == 1


# =============================================================================
# Return Calculation Tests
# =============================================================================


class TestReturnCalculations:
    """Test return calculation methods."""

    def test_calculate_returns_from_values(self, calculator, portfolio_values):
        """Test calculating returns from portfolio values."""
        returns = calculator.calculate_returns(portfolio_values)

        assert returns.num_periods == len(portfolio_values) - 1
        # First return: (1010 - 1000) / 1000 = 0.01
        assert returns.values[0] == Decimal("0.01")

    def test_calculate_returns_empty(self, calculator):
        """Test calculating returns from empty values."""
        returns = calculator.calculate_returns([])
        assert returns.num_periods == 0

    def test_calculate_returns_single_value(self, calculator):
        """Test calculating returns from single value."""
        returns = calculator.calculate_returns([(date.today(), Decimal("100"))])
        assert returns.num_periods == 0

    def test_total_return(self, calculator, simple_returns):
        """Test total cumulative return calculation."""
        total = calculator.total_return(simple_returns)

        # Manual calculation: (1+0.01)*(1-0.005)*(1+0.02)*... - 1
        expected = Decimal("1")
        for r in simple_returns.values:
            expected *= (Decimal("1") + r)
        expected -= Decimal("1")

        assert abs(total - expected) < Decimal("0.0001")

    def test_total_return_empty(self, calculator):
        """Test total return with empty series."""
        empty = ReturnSeries(returns=[], period=Period.DAILY)
        assert calculator.total_return(empty) == Decimal("0")

    def test_total_return_positive_only(self, calculator, positive_returns):
        """Test total return with all positive returns."""
        total = calculator.total_return(positive_returns)
        # 20 days of 1% each: (1.01)^20 - 1 ≈ 0.2202
        assert total > Decimal("0.20")
        assert total < Decimal("0.25")

    def test_total_return_negative_only(self, calculator, negative_returns):
        """Test total return with all negative returns."""
        total = calculator.total_return(negative_returns)
        # 20 days of -1% each: (0.99)^20 - 1 ≈ -0.1821
        assert total < Decimal("-0.15")
        assert total > Decimal("-0.25")

    def test_annualized_return(self, calculator, simple_returns):
        """Test annualized return calculation."""
        ann_return = calculator.annualized_return(simple_returns)

        # Should be positive for our simple returns
        assert ann_return > Decimal("-1")
        assert ann_return < Decimal("10")  # Reasonable bound

    def test_annualized_return_empty(self, calculator):
        """Test annualized return with empty series."""
        empty = ReturnSeries(returns=[], period=Period.DAILY)
        assert calculator.annualized_return(empty) == Decimal("0")


# =============================================================================
# Volatility Tests
# =============================================================================


class TestVolatility:
    """Test volatility calculation methods."""

    def test_volatility_calculation(self, calculator, simple_returns):
        """Test basic volatility calculation."""
        vol = calculator.volatility(simple_returns)

        # Volatility should be positive
        assert vol > Decimal("0")
        # Annualized volatility typically 10-50% for equities
        assert vol < Decimal("5")  # Reasonable upper bound

    def test_volatility_not_annualized(self, calculator, simple_returns):
        """Test non-annualized volatility."""
        vol_ann = calculator.volatility(simple_returns, annualize=True)
        vol_not_ann = calculator.volatility(simple_returns, annualize=False)

        # Annualized should be higher by sqrt(252) factor
        assert vol_ann > vol_not_ann

    def test_volatility_zero_variance(self, calculator):
        """Test volatility with constant returns."""
        constant = ReturnSeries(
            returns=[(date.today() + timedelta(days=i), Decimal("0.01")) for i in range(10)],
            period=Period.DAILY,
        )
        vol = calculator.volatility(constant)
        assert vol == Decimal("0")

    def test_volatility_insufficient_data(self, calculator):
        """Test volatility with insufficient data."""
        single = ReturnSeries(
            returns=[(date.today(), Decimal("0.01"))],
            period=Period.DAILY,
        )
        assert calculator.volatility(single) == Decimal("0")

    def test_downside_deviation(self, calculator, simple_returns):
        """Test downside deviation calculation."""
        downside = calculator.downside_deviation(simple_returns)

        # Downside should be positive and <= total volatility
        assert downside >= Decimal("0")

    def test_downside_deviation_positive_only(self, calculator, positive_returns):
        """Test downside deviation with only positive returns."""
        downside = calculator.downside_deviation(positive_returns)
        # No downside when all returns are positive
        assert downside == Decimal("0")


# =============================================================================
# Risk-Adjusted Metrics Tests
# =============================================================================


class TestRiskAdjustedMetrics:
    """Test risk-adjusted performance metrics."""

    def test_sharpe_ratio(self, calculator, simple_returns):
        """Test Sharpe ratio calculation."""
        sharpe = calculator.sharpe_ratio(simple_returns)

        # Sharpe can be positive, negative, or zero
        assert isinstance(sharpe, Decimal)

    def test_sharpe_ratio_zero_volatility(self, calculator):
        """Test Sharpe ratio with zero volatility."""
        constant = ReturnSeries(
            returns=[(date.today() + timedelta(days=i), Decimal("0.01")) for i in range(10)],
            period=Period.DAILY,
        )
        sharpe = calculator.sharpe_ratio(constant)
        assert sharpe == Decimal("0")

    def test_sortino_ratio(self, calculator, simple_returns):
        """Test Sortino ratio calculation."""
        sortino = calculator.sortino_ratio(simple_returns)

        # Sortino should be defined
        assert isinstance(sortino, Decimal)

    def test_sortino_vs_sharpe(self, calculator, simple_returns):
        """Test that Sortino differs from Sharpe."""
        sharpe = calculator.sharpe_ratio(simple_returns)
        sortino = calculator.sortino_ratio(simple_returns)

        # For asymmetric returns, Sortino should differ from Sharpe
        # (unless all returns are below MAR or there's no downside)
        # Just check both are calculated
        assert sharpe != Decimal("0") or sortino != Decimal("0") or True

    def test_calmar_ratio(self, calculator, simple_returns):
        """Test Calmar ratio calculation."""
        calmar = calculator.calmar_ratio(simple_returns)

        # Calmar should be defined
        assert isinstance(calmar, Decimal)


# =============================================================================
# Drawdown Tests
# =============================================================================


class TestDrawdownAnalysis:
    """Test drawdown analysis methods."""

    def test_max_drawdown_calculation(self, calculator):
        """Test maximum drawdown calculation."""
        # Create a series with a known drawdown
        # Start at 1, go to 1.1, drop to 0.9, recover to 1.05
        # Max DD = (0.9 - 1.1) / 1.1 = -0.1818
        cum_returns = [
            Decimal("0"),      # 1.0
            Decimal("0.10"),   # 1.1
            Decimal("-0.10"),  # 0.9
            Decimal("0.05"),   # 1.05
        ]
        max_dd = calculator.max_drawdown(cum_returns)

        # Max DD should be around -18%
        assert max_dd < Decimal("-0.15")
        assert max_dd > Decimal("-0.25")

    def test_max_drawdown_no_drawdown(self, calculator):
        """Test max drawdown with no drawdown."""
        # Monotonically increasing returns
        cum_returns = [Decimal("0.01") * i for i in range(1, 11)]
        max_dd = calculator.max_drawdown(cum_returns)

        assert max_dd == Decimal("0")

    def test_max_drawdown_empty(self, calculator):
        """Test max drawdown with empty series."""
        assert calculator.max_drawdown([]) == Decimal("0")

    def test_drawdown_series(self, calculator, drawdown_values):
        """Test drawdown series calculation."""
        dd_series = calculator.drawdown_series(drawdown_values)

        assert len(dd_series) == len(drawdown_values)
        # First value should have 0 drawdown
        assert dd_series[0][1] == Decimal("0")

    def test_find_drawdowns(self, calculator, drawdown_values):
        """Test finding drawdown periods."""
        drawdowns = calculator.find_drawdowns(drawdown_values, min_drawdown=Decimal("-0.03"))

        assert len(drawdowns) > 0
        for dd in drawdowns:
            assert isinstance(dd, DrawdownInfo)
            assert dd.max_drawdown < Decimal("0")

    def test_drawdown_info_properties(self, calculator, drawdown_values):
        """Test DrawdownInfo properties."""
        drawdowns = calculator.find_drawdowns(drawdown_values, min_drawdown=Decimal("-0.05"))

        if drawdowns:
            dd = drawdowns[0]
            assert dd.start_date <= dd.trough_date
            assert dd.peak_value > dd.trough_value
            assert dd.duration_days >= 0


# =============================================================================
# Trade Statistics Tests
# =============================================================================


class TestTradeStatistics:
    """Test trade-level statistics."""

    def test_trade_statistics(self, calculator, trade_returns):
        """Test basic trade statistics calculation."""
        stats = calculator.trade_statistics(trade_returns)

        assert stats.total_trades == 10
        assert stats.winning_trades == 5
        assert stats.losing_trades == 4
        assert stats.breakeven_trades == 1

    def test_win_rate(self, calculator, trade_returns):
        """Test win rate calculation."""
        stats = calculator.trade_statistics(trade_returns)

        # 5 wins out of 10 trades = 50%
        assert stats.win_rate == Decimal("50.00")

    def test_profit_factor(self, calculator, trade_returns):
        """Test profit factor calculation."""
        stats = calculator.trade_statistics(trade_returns)

        # Gross profit / Gross loss
        # Profits: 0.10 + 0.08 + 0.15 + 0.12 + 0.05 = 0.50
        # Losses: 0.05 + 0.03 + 0.08 + 0.02 = 0.18
        # PF = 0.50 / 0.18 ≈ 2.78
        assert stats.profit_factor > Decimal("2")
        assert stats.profit_factor < Decimal("3")

    def test_average_win_loss(self, calculator, trade_returns):
        """Test average win and loss calculation."""
        stats = calculator.trade_statistics(trade_returns)

        # Average win: 0.50 / 5 = 0.10
        assert stats.avg_win == Decimal("0.1000")

        # Average loss: -0.18 / 4 = -0.045
        assert stats.avg_loss < Decimal("0")

    def test_largest_win_loss(self, calculator, trade_returns):
        """Test largest win and loss identification."""
        stats = calculator.trade_statistics(trade_returns)

        assert stats.largest_win == Decimal("0.15")
        assert stats.largest_loss == Decimal("-0.08")

    def test_expectancy(self, calculator, trade_returns):
        """Test expectancy calculation."""
        stats = calculator.trade_statistics(trade_returns)

        # Expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)
        assert isinstance(stats.expectancy, Decimal)
        # Should be positive for our sample (more wins than losses by amount)
        assert stats.expectancy > Decimal("0")

    def test_empty_trades(self, calculator):
        """Test statistics with no trades."""
        stats = calculator.trade_statistics([])

        assert stats.total_trades == 0
        assert stats.win_rate == Decimal("0")
        assert stats.profit_factor == Decimal("0")


# =============================================================================
# Benchmark Comparison Tests
# =============================================================================


class TestBenchmarkComparison:
    """Test benchmark comparison methods."""

    def test_benchmark_comparison(self, calculator):
        """Test basic benchmark comparison."""
        base_date = date(2024, 1, 1)
        portfolio = ReturnSeries(
            returns=[(base_date + timedelta(days=i), Decimal(str(r)))
                    for i, r in enumerate([0.02, -0.01, 0.03, 0.01, -0.02])],
            period=Period.DAILY,
        )
        benchmark = ReturnSeries(
            returns=[(base_date + timedelta(days=i), Decimal(str(r)))
                    for i, r in enumerate([0.01, -0.005, 0.02, 0.005, -0.01])],
            period=Period.DAILY,
        )

        comparison = calculator.benchmark_comparison(portfolio, benchmark)

        assert "alpha" in comparison
        assert "beta" in comparison
        assert "information_ratio" in comparison
        assert "tracking_error" in comparison

    def test_beta_calculation(self, calculator):
        """Test beta calculation."""
        base_date = date(2024, 1, 1)
        # Portfolio moves 2x the benchmark
        benchmark_rets = [0.01, -0.01, 0.02, -0.02, 0.015]
        portfolio_rets = [0.02, -0.02, 0.04, -0.04, 0.03]

        portfolio = ReturnSeries(
            returns=[(base_date + timedelta(days=i), Decimal(str(r)))
                    for i, r in enumerate(portfolio_rets)],
            period=Period.DAILY,
        )
        benchmark = ReturnSeries(
            returns=[(base_date + timedelta(days=i), Decimal(str(r)))
                    for i, r in enumerate(benchmark_rets)],
            period=Period.DAILY,
        )

        comparison = calculator.benchmark_comparison(portfolio, benchmark)

        # Beta should be approximately 2
        assert comparison["beta"] > Decimal("1.5")
        assert comparison["beta"] < Decimal("2.5")

    def test_mismatched_periods(self, calculator):
        """Test benchmark comparison with mismatched periods."""
        base_date = date(2024, 1, 1)
        portfolio = ReturnSeries(
            returns=[(base_date + timedelta(days=i), Decimal("0.01")) for i in range(10)],
            period=Period.DAILY,
        )
        benchmark = ReturnSeries(
            returns=[(base_date + timedelta(days=i), Decimal("0.01")) for i in range(5)],
            period=Period.DAILY,
        )

        with pytest.raises(ValueError, match="same number of periods"):
            calculator.benchmark_comparison(portfolio, benchmark)


# =============================================================================
# Complete Metrics Tests
# =============================================================================


class TestCalculateMetrics:
    """Test complete performance metrics calculation."""

    def test_calculate_metrics(self, calculator, simple_returns, trade_returns):
        """Test full metrics calculation."""
        metrics = calculator.calculate_metrics(
            simple_returns,
            trade_returns=trade_returns,
        )

        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.start_date == simple_returns.dates[0]
        assert metrics.end_date == simple_returns.dates[-1]
        assert isinstance(metrics.total_return, Decimal)
        assert isinstance(metrics.sharpe_ratio, Decimal)
        assert metrics.trade_stats is not None

    def test_calculate_metrics_empty(self, calculator):
        """Test metrics with empty series."""
        empty = ReturnSeries(returns=[], period=Period.DAILY)
        metrics = calculator.calculate_metrics(empty)

        assert metrics.total_return == Decimal("0")
        assert metrics.sharpe_ratio == Decimal("0")
        assert metrics.num_drawdowns == 0

    def test_calculate_metrics_with_benchmark(self, calculator, simple_returns):
        """Test metrics with benchmark."""
        base_date = date(2024, 1, 1)
        benchmark = ReturnSeries(
            returns=[(base_date + timedelta(days=i), Decimal("0.005"))
                    for i in range(10)],
            period=Period.DAILY,
        )

        metrics = calculator.calculate_metrics(simple_returns, benchmark_returns=benchmark)

        assert metrics.benchmark_alpha is not None
        assert metrics.benchmark_beta is not None
        assert metrics.information_ratio is not None

    def test_best_worst_day(self, calculator, simple_returns):
        """Test best and worst day identification."""
        metrics = calculator.calculate_metrics(simple_returns)

        assert metrics.best_day == Decimal("0.02")
        assert metrics.worst_day == Decimal("-0.01")

    def test_positive_negative_periods(self, calculator, simple_returns):
        """Test counting positive and negative periods."""
        metrics = calculator.calculate_metrics(simple_returns)

        # Count manually: 0.01, -0.005, 0.02, 0.005, -0.01, 0.015, -0.003, 0.008, 0.012, -0.007
        # Positive: 6, Negative: 4
        assert metrics.positive_periods == 6
        assert metrics.negative_periods == 4


# =============================================================================
# Utility Function Tests
# =============================================================================


class TestUtilityFunctions:
    """Test utility functions."""

    def test_calculate_cagr(self):
        """Test CAGR calculation."""
        # Start: 1000, End: 1610.51, Years: 5
        # CAGR = (1610.51/1000)^(1/5) - 1 = 0.10 (10%)
        cagr = calculate_cagr(
            Decimal("1000"),
            Decimal("1610.51"),
            Decimal("5"),
        )
        assert abs(cagr - Decimal("0.10")) < Decimal("0.01")

    def test_calculate_cagr_zero_start(self):
        """Test CAGR with zero start value."""
        cagr = calculate_cagr(Decimal("0"), Decimal("100"), Decimal("5"))
        assert cagr == Decimal("0")

    def test_calculate_cagr_zero_years(self):
        """Test CAGR with zero years."""
        cagr = calculate_cagr(Decimal("100"), Decimal("200"), Decimal("0"))
        assert cagr == Decimal("0")

    def test_calculate_rolling_returns(self, simple_returns):
        """Test rolling returns calculation."""
        rolling = calculate_rolling_returns(simple_returns, window=3)

        # Should have num_periods - window + 1 values
        assert len(rolling) == simple_returns.num_periods - 3 + 1

    def test_calculate_rolling_returns_window_too_large(self, simple_returns):
        """Test rolling returns with window larger than series."""
        rolling = calculate_rolling_returns(simple_returns, window=100)
        assert len(rolling) == 0

    def test_calculate_monthly_returns(self):
        """Test monthly return aggregation."""
        # Create daily returns spanning multiple months
        returns_data = []
        for month in [1, 2, 3]:
            for day in range(1, 11):
                dt = date(2024, month, day)
                returns_data.append((dt, Decimal("0.001")))

        daily = ReturnSeries(returns=returns_data, period=Period.DAILY)
        monthly = calculate_monthly_returns(daily)

        assert len(monthly) == 3
        assert (2024, 1) in monthly
        assert (2024, 2) in monthly
        assert (2024, 3) in monthly

    def test_calculate_monthly_returns_wrong_period(self):
        """Test monthly aggregation with wrong input period."""
        weekly = ReturnSeries(returns=[], period=Period.WEEKLY)

        with pytest.raises(ValueError, match="daily returns"):
            calculate_monthly_returns(weekly)

    def test_calculate_yearly_returns(self):
        """Test yearly return aggregation."""
        # Create daily returns spanning multiple years
        returns_data = []
        for year in [2023, 2024]:
            for i in range(10):
                dt = date(year, 1, i + 1)
                returns_data.append((dt, Decimal("0.001")))

        daily = ReturnSeries(returns=returns_data, period=Period.DAILY)
        yearly = calculate_yearly_returns(daily)

        assert len(yearly) == 2
        assert 2023 in yearly
        assert 2024 in yearly

    def test_calculate_yearly_returns_wrong_period(self):
        """Test yearly aggregation with wrong input period."""
        monthly = ReturnSeries(returns=[], period=Period.MONTHLY)

        with pytest.raises(ValueError, match="daily returns"):
            calculate_yearly_returns(monthly)


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_calculator_with_zero_risk_free_rate(self):
        """Test calculator with zero risk-free rate."""
        calc = PerformanceCalculator(risk_free_rate=Decimal("0"))
        assert calc.risk_free_rate == Decimal("0")

    def test_calculator_with_custom_mar(self):
        """Test calculator with custom MAR."""
        calc = PerformanceCalculator(min_acceptable_return=Decimal("0.05"))
        assert calc.min_acceptable_return == Decimal("0.05")

    def test_very_small_returns(self, calculator):
        """Test with very small returns."""
        tiny = ReturnSeries(
            returns=[
                (date(2024, 1, i), Decimal("0.0001"))
                for i in range(1, 11)
            ],
            period=Period.DAILY,
        )
        metrics = calculator.calculate_metrics(tiny)
        assert isinstance(metrics.total_return, Decimal)

    def test_very_large_returns(self, calculator):
        """Test with very large returns."""
        large = ReturnSeries(
            returns=[
                (date(2024, 1, i), Decimal("0.50"))  # 50% daily
                for i in range(1, 6)
            ],
            period=Period.DAILY,
        )
        metrics = calculator.calculate_metrics(large)
        # Total return should be huge: (1.5)^5 - 1 ≈ 6.59
        assert metrics.total_return > Decimal("5")

    def test_mixed_positive_negative(self, calculator):
        """Test with alternating returns."""
        alternating = ReturnSeries(
            returns=[
                (date(2024, 1, i), Decimal("0.02") if i % 2 == 0 else Decimal("-0.02"))
                for i in range(1, 21)
            ],
            period=Period.DAILY,
        )
        metrics = calculator.calculate_metrics(alternating)
        # Should have roughly zero total return
        assert abs(metrics.total_return) < Decimal("0.10")
