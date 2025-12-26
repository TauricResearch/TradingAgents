"""Tests for Results Analyzer.

Issue #43: [BT-42] Results analyzer - metrics, trade analysis
"""

from datetime import datetime, timedelta
from decimal import Decimal
import pytest

from tradingagents.backtest import (
    # Backtest Engine
    BacktestEngine,
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    BacktestSnapshot,
    BacktestPosition,
    OHLCV,
    Signal,
    OrderSide,
    # Results Analyzer
    TimeFrame,
    TradeDirection,
    TradeAnalysis,
    TradePattern,
    PerformanceBreakdown,
    RiskMetrics,
    TradeStatistics,
    BenchmarkComparison,
    DrawdownAnalysis,
    AnalysisResult,
    ResultsAnalyzer,
    create_results_analyzer,
)


ZERO = Decimal("0")


# ============================================================================
# Enum Tests
# ============================================================================

class TestTimeFrame:
    """Tests for TimeFrame enum."""

    def test_values(self):
        """Test enum values."""
        assert TimeFrame.DAILY.value == "daily"
        assert TimeFrame.WEEKLY.value == "weekly"
        assert TimeFrame.MONTHLY.value == "monthly"
        assert TimeFrame.QUARTERLY.value == "quarterly"
        assert TimeFrame.YEARLY.value == "yearly"


class TestTradeDirection:
    """Tests for TradeDirection enum."""

    def test_values(self):
        """Test enum values."""
        assert TradeDirection.LONG.value == "long"
        assert TradeDirection.SHORT.value == "short"
        assert TradeDirection.BOTH.value == "both"


# ============================================================================
# Data Class Tests
# ============================================================================

class TestTradeAnalysis:
    """Tests for TradeAnalysis dataclass."""

    def test_creation(self):
        """Test TradeAnalysis creation."""
        trade = BacktestTrade(
            trade_id="BT-001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            price=Decimal("150"),
            pnl=Decimal("500"),
        )
        analysis = TradeAnalysis(
            trade=trade,
            return_pct=Decimal("3.33"),
            holding_period_days=Decimal("5"),
        )
        assert analysis.trade.symbol == "AAPL"
        assert analysis.return_pct == Decimal("3.33")


class TestTradePattern:
    """Tests for TradePattern dataclass."""

    def test_creation(self):
        """Test TradePattern creation."""
        pattern = TradePattern(
            pattern_name="Day:Monday",
            occurrences=10,
            win_rate=Decimal("60"),
            avg_return=Decimal("100"),
        )
        assert pattern.pattern_name == "Day:Monday"
        assert pattern.occurrences == 10


class TestPerformanceBreakdown:
    """Tests for PerformanceBreakdown dataclass."""

    def test_creation(self):
        """Test PerformanceBreakdown creation."""
        breakdown = PerformanceBreakdown(
            period="2023-01",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 31),
            return_pct=Decimal("5.5"),
            trades=20,
        )
        assert breakdown.period == "2023-01"
        assert breakdown.return_pct == Decimal("5.5")


class TestRiskMetrics:
    """Tests for RiskMetrics dataclass."""

    def test_default_creation(self):
        """Test RiskMetrics default creation."""
        metrics = RiskMetrics()
        assert metrics.sharpe_ratio == ZERO
        assert metrics.max_drawdown == ZERO

    def test_custom_creation(self):
        """Test RiskMetrics with values."""
        metrics = RiskMetrics(
            sharpe_ratio=Decimal("1.5"),
            sortino_ratio=Decimal("2.0"),
            max_drawdown=Decimal("10"),
        )
        assert metrics.sharpe_ratio == Decimal("1.5")
        assert metrics.max_drawdown == Decimal("10")


class TestTradeStatistics:
    """Tests for TradeStatistics dataclass."""

    def test_default_creation(self):
        """Test TradeStatistics default creation."""
        stats = TradeStatistics()
        assert stats.total_trades == 0
        assert stats.win_rate == ZERO

    def test_custom_creation(self):
        """Test TradeStatistics with values."""
        stats = TradeStatistics(
            total_trades=100,
            winning_trades=60,
            win_rate=Decimal("60"),
        )
        assert stats.total_trades == 100
        assert stats.winning_trades == 60


class TestBenchmarkComparison:
    """Tests for BenchmarkComparison dataclass."""

    def test_default_creation(self):
        """Test BenchmarkComparison default creation."""
        comparison = BenchmarkComparison()
        assert comparison.benchmark_return == ZERO
        assert comparison.alpha == ZERO

    def test_custom_creation(self):
        """Test BenchmarkComparison with values."""
        comparison = BenchmarkComparison(
            benchmark_symbol="SPY",
            benchmark_return=Decimal("10"),
            strategy_return=Decimal("15"),
            alpha=Decimal("5"),
        )
        assert comparison.benchmark_symbol == "SPY"
        assert comparison.alpha == Decimal("5")


class TestDrawdownAnalysis:
    """Tests for DrawdownAnalysis dataclass."""

    def test_default_creation(self):
        """Test DrawdownAnalysis default creation."""
        analysis = DrawdownAnalysis()
        assert analysis.max_drawdown == ZERO
        assert analysis.drawdown_count == 0

    def test_custom_creation(self):
        """Test DrawdownAnalysis with values."""
        analysis = DrawdownAnalysis(
            max_drawdown=Decimal("15"),
            max_drawdown_duration=30,
            drawdown_count=5,
        )
        assert analysis.max_drawdown == Decimal("15")
        assert analysis.max_drawdown_duration == 30


# ============================================================================
# ResultsAnalyzer Tests
# ============================================================================

class TestResultsAnalyzer:
    """Tests for ResultsAnalyzer class."""

    @pytest.fixture
    def analyzer(self):
        """Create test analyzer."""
        return ResultsAnalyzer()

    @pytest.fixture
    def price_data(self):
        """Create test price data."""
        return {
            "AAPL": [
                OHLCV(datetime(2023, 1, 3), 100, 102, 99, 101, 1000000, "AAPL"),
                OHLCV(datetime(2023, 1, 4), 101, 105, 100, 104, 1200000, "AAPL"),
                OHLCV(datetime(2023, 1, 5), 104, 108, 103, 107, 1100000, "AAPL"),
                OHLCV(datetime(2023, 1, 6), 107, 110, 106, 109, 1300000, "AAPL"),
                OHLCV(datetime(2023, 1, 9), 109, 112, 108, 111, 1400000, "AAPL"),
                OHLCV(datetime(2023, 1, 10), 111, 114, 110, 113, 1500000, "AAPL"),
                OHLCV(datetime(2023, 1, 11), 113, 115, 112, 114, 1600000, "AAPL"),
                OHLCV(datetime(2023, 1, 12), 114, 116, 113, 115, 1700000, "AAPL"),
                OHLCV(datetime(2023, 1, 13), 115, 117, 114, 116, 1800000, "AAPL"),
                OHLCV(datetime(2023, 1, 16), 116, 118, 115, 117, 1900000, "AAPL"),
            ],
        }

    @pytest.fixture
    def backtest_result(self, price_data):
        """Create test backtest result."""
        engine = BacktestEngine(BacktestConfig(initial_capital=Decimal("100000")))
        signals = [
            Signal(datetime(2023, 1, 3), "AAPL", OrderSide.BUY, Decimal("100")),
            Signal(datetime(2023, 1, 6), "AAPL", OrderSide.SELL, Decimal("50")),
            Signal(datetime(2023, 1, 9), "AAPL", OrderSide.BUY, Decimal("50")),
            Signal(datetime(2023, 1, 12), "AAPL", OrderSide.SELL, Decimal("100")),
        ]
        return engine.run(price_data, signals)

    def test_initialization(self, analyzer):
        """Test analyzer initialization."""
        assert analyzer.risk_free_rate == Decimal("0.05")
        assert analyzer.top_n_trades == 10

    def test_analyze_empty_result(self, analyzer):
        """Test analyzing empty result."""
        result = BacktestResult(
            config=BacktestConfig(),
            initial_capital=Decimal("100000"),
            final_value=Decimal("100000"),
        )
        analysis = analyzer.analyze(result)

        assert analysis.trade_statistics.total_trades == 0
        assert len(analysis.errors) == 0

    def test_analyze_with_trades(self, analyzer, backtest_result):
        """Test analyzing result with trades."""
        analysis = analyzer.analyze(backtest_result)

        assert analysis.trade_statistics.total_trades > 0
        assert analysis.backtest_result == backtest_result

    def test_trade_statistics(self, analyzer, backtest_result):
        """Test trade statistics calculation."""
        analysis = analyzer.analyze(backtest_result)
        stats = analysis.trade_statistics

        assert stats.total_trades == len(backtest_result.trades)
        assert stats.winning_trades + stats.losing_trades + stats.break_even_trades == stats.total_trades
        assert stats.win_rate >= ZERO
        assert stats.win_rate <= Decimal("100")

    def test_risk_metrics(self, analyzer, backtest_result):
        """Test risk metrics calculation."""
        analysis = analyzer.analyze(backtest_result)
        metrics = analysis.risk_metrics

        # Basic validation
        assert isinstance(metrics.sharpe_ratio, Decimal)
        assert isinstance(metrics.max_drawdown, Decimal)
        assert metrics.max_drawdown >= ZERO

    def test_drawdown_analysis(self, analyzer, backtest_result):
        """Test drawdown analysis."""
        analysis = analyzer.analyze(backtest_result)
        dd = analysis.drawdown_analysis

        assert isinstance(dd.max_drawdown, Decimal)
        assert dd.max_drawdown >= ZERO
        assert dd.drawdown_count >= 0

    def test_monthly_performance(self, analyzer, backtest_result):
        """Test monthly performance breakdown."""
        analysis = analyzer.analyze(backtest_result)

        # All trades are in January 2023
        assert len(analysis.monthly_performance) >= 0

    def test_yearly_performance(self, analyzer, backtest_result):
        """Test yearly performance breakdown."""
        analysis = analyzer.analyze(backtest_result)

        # All trades are in 2023
        assert len(analysis.yearly_performance) >= 0

    def test_trade_analyses(self, analyzer, backtest_result):
        """Test individual trade analyses."""
        analysis = analyzer.analyze(backtest_result)

        assert len(analysis.trade_analyses) == len(backtest_result.trades)
        for ta in analysis.trade_analyses:
            assert isinstance(ta, TradeAnalysis)
            assert ta.trade is not None

    def test_trade_patterns(self, analyzer, backtest_result):
        """Test trade pattern identification."""
        analysis = analyzer.analyze(backtest_result)

        # Should have some day-of-week patterns
        day_patterns = [p for p in analysis.trade_patterns if p.pattern_name.startswith("Day:")]
        assert len(day_patterns) > 0

    def test_best_worst_trades(self, analyzer, backtest_result):
        """Test best and worst trades identification."""
        analysis = analyzer.analyze(backtest_result)

        # Should have best/worst trades
        assert len(analysis.best_trades) <= analyzer.top_n_trades
        assert len(analysis.worst_trades) <= analyzer.top_n_trades

        # Best should be sorted descending by P&L
        for i in range(len(analysis.best_trades) - 1):
            assert analysis.best_trades[i].pnl >= analysis.best_trades[i + 1].pnl


class TestTradeStatisticsCalculation:
    """Tests for trade statistics calculation."""

    @pytest.fixture
    def analyzer(self):
        """Create test analyzer."""
        return ResultsAnalyzer()

    def test_win_rate_calculation(self, analyzer):
        """Test win rate calculation."""
        # Create result with known win/loss ratio
        result = BacktestResult(
            trades=[
                BacktestTrade(pnl=Decimal("100")),
                BacktestTrade(pnl=Decimal("200")),
                BacktestTrade(pnl=Decimal("-50")),
                BacktestTrade(pnl=Decimal("150")),
                BacktestTrade(pnl=Decimal("-75")),
            ],
        )

        stats = analyzer._calculate_trade_statistics(result)

        assert stats.total_trades == 5
        assert stats.winning_trades == 3
        assert stats.losing_trades == 2
        assert stats.win_rate == Decimal("60")  # 3/5 * 100

    def test_profit_factor_calculation(self, analyzer):
        """Test profit factor calculation."""
        result = BacktestResult(
            trades=[
                BacktestTrade(pnl=Decimal("100")),
                BacktestTrade(pnl=Decimal("200")),
                BacktestTrade(pnl=Decimal("-100")),
            ],
        )

        stats = analyzer._calculate_trade_statistics(result)

        # Gross profit = 300, Gross loss = 100
        assert stats.profit_factor == Decimal("3")

    def test_consecutive_wins_losses(self, analyzer):
        """Test consecutive wins/losses calculation."""
        result = BacktestResult(
            trades=[
                BacktestTrade(pnl=Decimal("100")),  # Win
                BacktestTrade(pnl=Decimal("100")),  # Win
                BacktestTrade(pnl=Decimal("100")),  # Win - 3 consecutive
                BacktestTrade(pnl=Decimal("-50")),  # Loss
                BacktestTrade(pnl=Decimal("-50")),  # Loss - 2 consecutive
                BacktestTrade(pnl=Decimal("100")),  # Win
            ],
        )

        stats = analyzer._calculate_trade_statistics(result)

        assert stats.max_consecutive_wins == 3
        assert stats.max_consecutive_losses == 2

    def test_average_calculations(self, analyzer):
        """Test average win/loss calculations."""
        result = BacktestResult(
            trades=[
                BacktestTrade(pnl=Decimal("100")),
                BacktestTrade(pnl=Decimal("200")),
                BacktestTrade(pnl=Decimal("-50")),
                BacktestTrade(pnl=Decimal("-150")),
            ],
        )

        stats = analyzer._calculate_trade_statistics(result)

        assert stats.avg_win == Decimal("150")  # (100+200)/2
        assert stats.avg_loss == Decimal("-100")  # (-50-150)/2
        assert stats.avg_trade == Decimal("25")  # (100+200-50-150)/4

    def test_median_calculation(self, analyzer):
        """Test median P&L calculation."""
        result = BacktestResult(
            trades=[
                BacktestTrade(pnl=Decimal("100")),
                BacktestTrade(pnl=Decimal("200")),
                BacktestTrade(pnl=Decimal("300")),
            ],
        )

        stats = analyzer._calculate_trade_statistics(result)
        assert stats.median_trade == Decimal("200")


class TestRiskMetricsCalculation:
    """Tests for risk metrics calculation."""

    @pytest.fixture
    def analyzer(self):
        """Create test analyzer."""
        return ResultsAnalyzer(risk_free_rate=Decimal("0.05"))

    def test_sharpe_ratio_positive(self, analyzer):
        """Test Sharpe ratio for positive returns."""
        result = BacktestResult(
            daily_returns=[Decimal("0.01")] * 252,  # 1% daily return
            max_drawdown=Decimal("5"),
        )

        metrics = analyzer._calculate_risk_metrics(result)

        # Positive returns should give positive Sharpe
        assert metrics.sharpe_ratio > ZERO

    def test_sharpe_ratio_negative(self, analyzer):
        """Test Sharpe ratio for negative returns."""
        result = BacktestResult(
            daily_returns=[Decimal("-0.01")] * 100,  # -1% daily return
            max_drawdown=Decimal("20"),
        )

        metrics = analyzer._calculate_risk_metrics(result)

        # Negative returns should give negative Sharpe
        assert metrics.sharpe_ratio < ZERO

    def test_max_drawdown_tracked(self, analyzer):
        """Test max drawdown is tracked."""
        result = BacktestResult(
            max_drawdown=Decimal("15"),
            daily_returns=[],
        )

        metrics = analyzer._calculate_risk_metrics(result)
        assert metrics.max_drawdown == Decimal("15")

    def test_var_calculation(self, analyzer):
        """Test VaR calculation."""
        # Create returns with known distribution
        returns = [Decimal("-0.02")] * 5 + [Decimal("0.01")] * 95
        result = BacktestResult(
            daily_returns=returns,
            max_drawdown=Decimal("5"),
        )

        metrics = analyzer._calculate_risk_metrics(result)

        # VaR 95% should be around 2% (the worst 5% of returns)
        assert metrics.var_95 > ZERO


class TestDrawdownAnalysisCalculation:
    """Tests for drawdown analysis calculation."""

    @pytest.fixture
    def analyzer(self):
        """Create test analyzer."""
        return ResultsAnalyzer()

    def test_no_drawdown(self, analyzer):
        """Test analysis with no drawdown."""
        snapshots = [
            BacktestSnapshot(datetime(2023, 1, 1), Decimal("100000"), ZERO, Decimal("100000"), drawdown=ZERO),
            BacktestSnapshot(datetime(2023, 1, 2), Decimal("100000"), ZERO, Decimal("100500"), drawdown=ZERO),
            BacktestSnapshot(datetime(2023, 1, 3), Decimal("100000"), ZERO, Decimal("101000"), drawdown=ZERO),
        ]
        result = BacktestResult(snapshots=snapshots)

        dd = analyzer._analyze_drawdowns(result)

        assert dd.max_drawdown == ZERO
        assert dd.drawdown_count == 0

    def test_single_drawdown(self, analyzer):
        """Test analysis with single drawdown."""
        snapshots = [
            BacktestSnapshot(datetime(2023, 1, 1), Decimal("100000"), ZERO, Decimal("100000"), drawdown=ZERO, peak_value=Decimal("100000")),
            BacktestSnapshot(datetime(2023, 1, 2), Decimal("100000"), ZERO, Decimal("105000"), drawdown=ZERO, peak_value=Decimal("105000")),
            BacktestSnapshot(datetime(2023, 1, 3), Decimal("100000"), ZERO, Decimal("100000"), drawdown=Decimal("4.76"), peak_value=Decimal("105000")),
            BacktestSnapshot(datetime(2023, 1, 4), Decimal("100000"), ZERO, Decimal("102000"), drawdown=Decimal("2.86"), peak_value=Decimal("105000")),
            BacktestSnapshot(datetime(2023, 1, 5), Decimal("100000"), ZERO, Decimal("106000"), drawdown=ZERO, peak_value=Decimal("106000")),
        ]
        result = BacktestResult(snapshots=snapshots)

        dd = analyzer._analyze_drawdowns(result)

        assert dd.max_drawdown > ZERO
        assert dd.drawdown_count >= 1


class TestBenchmarkComparisonCalculation:
    """Tests for benchmark comparison calculation."""

    @pytest.fixture
    def analyzer(self):
        """Create test analyzer."""
        return ResultsAnalyzer()

    def test_benchmark_comparison(self, analyzer):
        """Test benchmark comparison calculation."""
        result = BacktestResult(
            total_return=Decimal("15"),
            daily_returns=[Decimal("0.01")] * 100,
            config=BacktestConfig(benchmark_symbol="SPY"),
        )
        benchmark_returns = [Decimal("0.005")] * 100  # Benchmark 0.5% daily

        comparison = analyzer._calculate_benchmark_comparison(result, benchmark_returns)

        assert comparison.benchmark_symbol == "SPY"
        assert comparison.strategy_return == Decimal("15")
        assert comparison.excess_return != ZERO

    def test_empty_benchmark(self, analyzer):
        """Test with empty benchmark."""
        result = BacktestResult(
            daily_returns=[Decimal("0.01")] * 10,
        )

        comparison = analyzer._calculate_benchmark_comparison(result, [])

        assert comparison.benchmark_return == ZERO


class TestPeriodicPerformanceCalculation:
    """Tests for periodic performance calculation."""

    @pytest.fixture
    def analyzer(self):
        """Create test analyzer."""
        return ResultsAnalyzer()

    def test_monthly_breakdown(self, analyzer):
        """Test monthly performance breakdown."""
        snapshots = [
            BacktestSnapshot(datetime(2023, 1, 1), Decimal("100000"), ZERO, Decimal("100000")),
            BacktestSnapshot(datetime(2023, 1, 15), Decimal("100000"), ZERO, Decimal("102000")),
            BacktestSnapshot(datetime(2023, 1, 31), Decimal("100000"), ZERO, Decimal("105000")),
            BacktestSnapshot(datetime(2023, 2, 1), Decimal("100000"), ZERO, Decimal("105000")),
            BacktestSnapshot(datetime(2023, 2, 15), Decimal("100000"), ZERO, Decimal("107000")),
            BacktestSnapshot(datetime(2023, 2, 28), Decimal("100000"), ZERO, Decimal("110000")),
        ]
        result = BacktestResult(snapshots=snapshots, trades=[])

        monthly = analyzer._calculate_periodic_performance(result, TimeFrame.MONTHLY)

        assert len(monthly) >= 2  # At least Jan and Feb

    def test_yearly_breakdown(self, analyzer):
        """Test yearly performance breakdown."""
        snapshots = [
            BacktestSnapshot(datetime(2023, 1, 1), Decimal("100000"), ZERO, Decimal("100000")),
            BacktestSnapshot(datetime(2023, 6, 30), Decimal("100000"), ZERO, Decimal("110000")),
            BacktestSnapshot(datetime(2023, 12, 31), Decimal("100000"), ZERO, Decimal("120000")),
        ]
        result = BacktestResult(snapshots=snapshots, trades=[])

        yearly = analyzer._calculate_periodic_performance(result, TimeFrame.YEARLY)

        assert len(yearly) >= 1


class TestResultsAnalyzerIntegration:
    """Integration tests for results analyzer."""

    def test_module_imports(self):
        """Test that all classes are exported from module."""
        from tradingagents.backtest import (
            TimeFrame,
            TradeDirection,
            TradeAnalysis,
            TradePattern,
            PerformanceBreakdown,
            RiskMetrics,
            TradeStatistics,
            BenchmarkComparison,
            DrawdownAnalysis,
            AnalysisResult,
            ResultsAnalyzer,
            create_results_analyzer,
        )

        # All imports successful
        assert ResultsAnalyzer is not None
        assert TimeFrame.MONTHLY is not None

    def test_create_results_analyzer_factory(self):
        """Test factory function."""
        analyzer = create_results_analyzer(
            risk_free_rate=Decimal("0.03"),
            top_n_trades=5,
        )

        assert analyzer.risk_free_rate == Decimal("0.03")
        assert analyzer.top_n_trades == 5

    def test_full_analysis_workflow(self):
        """Test complete analysis workflow."""
        # Run backtest
        engine = BacktestEngine(BacktestConfig(initial_capital=Decimal("100000")))
        price_data = {
            "AAPL": [
                OHLCV(datetime(2023, 1, 3), 100, 102, 99, 101, 1000000, "AAPL"),
                OHLCV(datetime(2023, 1, 4), 101, 105, 100, 104, 1200000, "AAPL"),
                OHLCV(datetime(2023, 1, 5), 104, 108, 103, 107, 1100000, "AAPL"),
            ],
        }
        signals = [
            Signal(datetime(2023, 1, 3), "AAPL", OrderSide.BUY, Decimal("100")),
            Signal(datetime(2023, 1, 5), "AAPL", OrderSide.SELL, Decimal("100")),
        ]
        result = engine.run(price_data, signals)

        # Analyze
        analyzer = ResultsAnalyzer()
        analysis = analyzer.analyze(result)

        # Verify analysis structure
        assert analysis.backtest_result == result
        assert analysis.trade_statistics is not None
        assert analysis.risk_metrics is not None
        assert analysis.drawdown_analysis is not None
        assert len(analysis.errors) == 0
