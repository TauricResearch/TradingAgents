"""Results Analyzer for backtest trade analysis.

Issue #43: [BT-42] Results analyzer - metrics, trade analysis

This module provides detailed analysis of backtest results:
- Trade-by-trade analysis
- Performance metrics calculation
- Risk metrics computation
- Monthly/yearly performance breakdowns
- Trade pattern analysis
- Benchmark comparison

Classes:
    TimeFrame: Analysis time frame enum
    TradeAnalysis: Individual trade analysis
    PerformanceBreakdown: Performance by period
    RiskMetrics: Risk-related metrics
    BenchmarkComparison: Comparison to benchmark
    AnalysisResult: Complete analysis result
    ResultsAnalyzer: Main analyzer class

Example:
    >>> from tradingagents.backtest import BacktestResult
    >>> from tradingagents.backtest.results_analyzer import ResultsAnalyzer
    >>>
    >>> analyzer = ResultsAnalyzer()
    >>> analysis = analyzer.analyze(backtest_result)
    >>> print(f"Sharpe: {analysis.risk_metrics.sharpe_ratio}")
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
import logging
import math

from .backtest_engine import (
    BacktestResult,
    BacktestTrade,
    BacktestSnapshot,
    OrderSide,
    ZERO,
    ONE,
    HUNDRED,
)


logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class TimeFrame(Enum):
    """Analysis time frame."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class TradeDirection(Enum):
    """Trade direction for analysis."""
    LONG = "long"
    SHORT = "short"
    BOTH = "both"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TradeAnalysis:
    """Analysis of an individual trade.

    Attributes:
        trade: Original trade record
        holding_period_days: Days position was held
        return_pct: Return percentage
        mae: Maximum Adverse Excursion
        mfe: Maximum Favorable Excursion
        efficiency: MFE capture efficiency
        r_multiple: R-multiple (if stop loss defined)
        edge_ratio: MFE/MAE ratio
    """
    trade: BacktestTrade
    holding_period_days: Decimal = ZERO
    return_pct: Decimal = ZERO
    mae: Decimal = ZERO  # Max Adverse Excursion
    mfe: Decimal = ZERO  # Max Favorable Excursion
    efficiency: Decimal = ZERO  # Profit/MFE
    r_multiple: Decimal = ZERO
    edge_ratio: Decimal = ZERO  # MFE/MAE


@dataclass
class TradePattern:
    """Trade pattern statistics.

    Attributes:
        pattern_name: Pattern identifier
        occurrences: Number of times pattern occurred
        win_rate: Win rate for this pattern
        avg_return: Average return
        total_pnl: Total P&L from pattern
    """
    pattern_name: str
    occurrences: int = 0
    win_rate: Decimal = ZERO
    avg_return: Decimal = ZERO
    total_pnl: Decimal = ZERO


@dataclass
class PerformanceBreakdown:
    """Performance breakdown by period.

    Attributes:
        period: Period identifier (e.g., "2023-01", "2023-Q1")
        start_date: Period start date
        end_date: Period end date
        return_pct: Return for period
        trades: Number of trades
        winning_trades: Number of winners
        pnl: Total P&L
        max_drawdown: Max drawdown in period
    """
    period: str
    start_date: datetime
    end_date: datetime
    return_pct: Decimal = ZERO
    trades: int = 0
    winning_trades: int = 0
    pnl: Decimal = ZERO
    max_drawdown: Decimal = ZERO


@dataclass
class RiskMetrics:
    """Risk-related metrics.

    Attributes:
        sharpe_ratio: Sharpe ratio
        sortino_ratio: Sortino ratio
        calmar_ratio: Calmar ratio (return / max drawdown)
        omega_ratio: Omega ratio
        tail_ratio: Tail ratio (95th / 5th percentile)
        var_95: Value at Risk (95%)
        cvar_95: Conditional VaR (95%)
        max_drawdown: Maximum drawdown percentage
        max_drawdown_duration: Duration of max drawdown in days
        recovery_factor: Total return / max drawdown
        ulcer_index: Ulcer index (pain index)
        pain_ratio: Pain ratio
        gain_to_pain_ratio: Gain to pain ratio
    """
    sharpe_ratio: Decimal = ZERO
    sortino_ratio: Decimal = ZERO
    calmar_ratio: Decimal = ZERO
    omega_ratio: Decimal = ZERO
    tail_ratio: Decimal = ZERO
    var_95: Decimal = ZERO
    cvar_95: Decimal = ZERO
    max_drawdown: Decimal = ZERO
    max_drawdown_duration: int = 0
    recovery_factor: Decimal = ZERO
    ulcer_index: Decimal = ZERO
    pain_ratio: Decimal = ZERO
    gain_to_pain_ratio: Decimal = ZERO


@dataclass
class TradeStatistics:
    """Comprehensive trade statistics.

    Attributes:
        total_trades: Total number of trades
        winning_trades: Number of winners
        losing_trades: Number of losers
        break_even_trades: Trades with zero P&L
        win_rate: Win rate percentage
        loss_rate: Loss rate percentage
        avg_win: Average winning trade
        avg_loss: Average losing trade
        max_win: Largest win
        max_loss: Largest loss
        avg_trade: Average trade
        median_trade: Median trade P&L
        profit_factor: Gross profit / gross loss
        expectancy: Expected value per trade
        payoff_ratio: Average win / average loss
        avg_holding_period: Average days held
        max_consecutive_wins: Max winning streak
        max_consecutive_losses: Max losing streak
        long_trades: Number of long trades
        short_trades: Number of short trades
        long_win_rate: Win rate for long trades
        short_win_rate: Win rate for short trades
    """
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    break_even_trades: int = 0
    win_rate: Decimal = ZERO
    loss_rate: Decimal = ZERO
    avg_win: Decimal = ZERO
    avg_loss: Decimal = ZERO
    max_win: Decimal = ZERO
    max_loss: Decimal = ZERO
    avg_trade: Decimal = ZERO
    median_trade: Decimal = ZERO
    profit_factor: Decimal = ZERO
    expectancy: Decimal = ZERO
    payoff_ratio: Decimal = ZERO
    avg_holding_period: Decimal = ZERO
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    long_trades: int = 0
    short_trades: int = 0
    long_win_rate: Decimal = ZERO
    short_win_rate: Decimal = ZERO


@dataclass
class BenchmarkComparison:
    """Comparison to benchmark.

    Attributes:
        benchmark_symbol: Benchmark symbol
        benchmark_return: Benchmark total return
        strategy_return: Strategy total return
        excess_return: Strategy - benchmark return
        alpha: Alpha (risk-adjusted excess return)
        beta: Beta (market sensitivity)
        correlation: Correlation with benchmark
        tracking_error: Standard deviation of excess returns
        information_ratio: Excess return / tracking error
        up_capture: Upside capture ratio
        down_capture: Downside capture ratio
        capture_ratio: Up/down capture ratio
    """
    benchmark_symbol: str = ""
    benchmark_return: Decimal = ZERO
    strategy_return: Decimal = ZERO
    excess_return: Decimal = ZERO
    alpha: Decimal = ZERO
    beta: Decimal = ZERO
    correlation: Decimal = ZERO
    tracking_error: Decimal = ZERO
    information_ratio: Decimal = ZERO
    up_capture: Decimal = ZERO
    down_capture: Decimal = ZERO
    capture_ratio: Decimal = ZERO


@dataclass
class DrawdownAnalysis:
    """Drawdown analysis.

    Attributes:
        current_drawdown: Current drawdown percentage
        max_drawdown: Maximum drawdown percentage
        max_drawdown_start: When max drawdown started
        max_drawdown_end: When max drawdown ended
        max_drawdown_duration: Duration in days
        recovery_time: Time to recover from max drawdown
        avg_drawdown: Average drawdown
        drawdown_count: Number of drawdown periods
        underwater_periods: List of (start, end, depth) tuples
    """
    current_drawdown: Decimal = ZERO
    max_drawdown: Decimal = ZERO
    max_drawdown_start: Optional[datetime] = None
    max_drawdown_end: Optional[datetime] = None
    max_drawdown_duration: int = 0
    recovery_time: int = 0
    avg_drawdown: Decimal = ZERO
    drawdown_count: int = 0
    underwater_periods: list[tuple[datetime, datetime, Decimal]] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Complete analysis result.

    Attributes:
        backtest_result: Original backtest result
        trade_statistics: Trade statistics
        risk_metrics: Risk metrics
        drawdown_analysis: Drawdown analysis
        monthly_performance: Monthly breakdown
        yearly_performance: Yearly breakdown
        benchmark_comparison: Benchmark comparison
        trade_analyses: Individual trade analyses
        trade_patterns: Identified trade patterns
        best_trades: Top N best trades
        worst_trades: Top N worst trades
        errors: Any analysis errors
    """
    backtest_result: BacktestResult
    trade_statistics: TradeStatistics = field(default_factory=TradeStatistics)
    risk_metrics: RiskMetrics = field(default_factory=RiskMetrics)
    drawdown_analysis: DrawdownAnalysis = field(default_factory=DrawdownAnalysis)
    monthly_performance: list[PerformanceBreakdown] = field(default_factory=list)
    yearly_performance: list[PerformanceBreakdown] = field(default_factory=list)
    benchmark_comparison: Optional[BenchmarkComparison] = None
    trade_analyses: list[TradeAnalysis] = field(default_factory=list)
    trade_patterns: list[TradePattern] = field(default_factory=list)
    best_trades: list[BacktestTrade] = field(default_factory=list)
    worst_trades: list[BacktestTrade] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ============================================================================
# Results Analyzer
# ============================================================================

class ResultsAnalyzer:
    """Analyzer for backtest results.

    Attributes:
        risk_free_rate: Annual risk-free rate for calculations
        top_n_trades: Number of best/worst trades to track
    """

    def __init__(
        self,
        risk_free_rate: Decimal = Decimal("0.05"),
        top_n_trades: int = 10,
    ):
        """Initialize analyzer.

        Args:
            risk_free_rate: Annual risk-free rate
            top_n_trades: Number of top trades to track
        """
        self.risk_free_rate = risk_free_rate
        self.top_n_trades = top_n_trades

    def analyze(
        self,
        result: BacktestResult,
        benchmark_returns: Optional[list[Decimal]] = None,
    ) -> AnalysisResult:
        """Perform complete analysis of backtest result.

        Args:
            result: Backtest result to analyze
            benchmark_returns: Optional benchmark returns for comparison

        Returns:
            AnalysisResult with all metrics
        """
        errors = []

        # Calculate trade statistics
        trade_stats = self._calculate_trade_statistics(result)

        # Calculate risk metrics
        risk_metrics = self._calculate_risk_metrics(result)

        # Analyze drawdowns
        drawdown_analysis = self._analyze_drawdowns(result)

        # Calculate monthly performance
        monthly = self._calculate_periodic_performance(result, TimeFrame.MONTHLY)

        # Calculate yearly performance
        yearly = self._calculate_periodic_performance(result, TimeFrame.YEARLY)

        # Benchmark comparison
        benchmark = None
        if benchmark_returns:
            try:
                benchmark = self._calculate_benchmark_comparison(
                    result, benchmark_returns
                )
            except Exception as e:
                errors.append(f"Benchmark comparison failed: {e}")

        # Analyze individual trades
        trade_analyses = self._analyze_trades(result)

        # Identify patterns
        patterns = self._identify_patterns(result)

        # Get best and worst trades
        best_trades, worst_trades = self._get_extreme_trades(result)

        return AnalysisResult(
            backtest_result=result,
            trade_statistics=trade_stats,
            risk_metrics=risk_metrics,
            drawdown_analysis=drawdown_analysis,
            monthly_performance=monthly,
            yearly_performance=yearly,
            benchmark_comparison=benchmark,
            trade_analyses=trade_analyses,
            trade_patterns=patterns,
            best_trades=best_trades,
            worst_trades=worst_trades,
            errors=result.errors + errors,
        )

    def _calculate_trade_statistics(self, result: BacktestResult) -> TradeStatistics:
        """Calculate comprehensive trade statistics.

        Args:
            result: Backtest result

        Returns:
            TradeStatistics
        """
        trades = result.trades
        if not trades:
            return TradeStatistics()

        # Basic counts
        total = len(trades)
        winners = [t for t in trades if t.pnl > ZERO]
        losers = [t for t in trades if t.pnl < ZERO]
        break_even = [t for t in trades if t.pnl == ZERO]

        winning_count = len(winners)
        losing_count = len(losers)
        break_even_count = len(break_even)

        # Win/loss rates
        win_rate = Decimal(str(winning_count)) / Decimal(str(total)) * HUNDRED if total > 0 else ZERO
        loss_rate = Decimal(str(losing_count)) / Decimal(str(total)) * HUNDRED if total > 0 else ZERO

        # Averages
        win_pnls = [t.pnl for t in winners]
        loss_pnls = [t.pnl for t in losers]
        all_pnls = [t.pnl for t in trades]

        avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else ZERO
        avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else ZERO
        avg_trade = sum(all_pnls) / len(all_pnls) if all_pnls else ZERO

        # Max win/loss
        max_win = max(win_pnls) if win_pnls else ZERO
        max_loss = min(loss_pnls) if loss_pnls else ZERO

        # Median
        sorted_pnls = sorted(all_pnls)
        median_idx = len(sorted_pnls) // 2
        if len(sorted_pnls) % 2 == 0:
            median_trade = (sorted_pnls[median_idx - 1] + sorted_pnls[median_idx]) / 2 if sorted_pnls else ZERO
        else:
            median_trade = sorted_pnls[median_idx] if sorted_pnls else ZERO

        # Profit factor
        gross_profit = sum(win_pnls)
        gross_loss = abs(sum(loss_pnls))
        profit_factor = gross_profit / gross_loss if gross_loss > ZERO else ZERO

        # Expectancy
        expectancy = avg_trade

        # Payoff ratio
        payoff_ratio = abs(avg_win / avg_loss) if avg_loss != ZERO else ZERO

        # Consecutive wins/losses
        max_consec_wins, max_consec_losses = self._calculate_streaks(trades)

        # Long/short breakdown
        long_trades = [t for t in trades if t.side == OrderSide.BUY]
        short_trades = [t for t in trades if t.side == OrderSide.SELL]
        long_winners = [t for t in long_trades if t.pnl > ZERO]
        short_winners = [t for t in short_trades if t.pnl > ZERO]

        long_win_rate = Decimal(str(len(long_winners))) / Decimal(str(len(long_trades))) * HUNDRED if long_trades else ZERO
        short_win_rate = Decimal(str(len(short_winners))) / Decimal(str(len(short_trades))) * HUNDRED if short_trades else ZERO

        return TradeStatistics(
            total_trades=total,
            winning_trades=winning_count,
            losing_trades=losing_count,
            break_even_trades=break_even_count,
            win_rate=win_rate,
            loss_rate=loss_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_win=max_win,
            max_loss=max_loss,
            avg_trade=avg_trade,
            median_trade=median_trade,
            profit_factor=profit_factor,
            expectancy=expectancy,
            payoff_ratio=payoff_ratio,
            max_consecutive_wins=max_consec_wins,
            max_consecutive_losses=max_consec_losses,
            long_trades=len(long_trades),
            short_trades=len(short_trades),
            long_win_rate=long_win_rate,
            short_win_rate=short_win_rate,
        )

    def _calculate_streaks(self, trades: list[BacktestTrade]) -> tuple[int, int]:
        """Calculate maximum consecutive wins and losses.

        Args:
            trades: List of trades

        Returns:
            Tuple of (max_wins, max_losses)
        """
        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for trade in trades:
            if trade.pnl > ZERO:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif trade.pnl < ZERO:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                # Break even doesn't break streak
                pass

        return max_wins, max_losses

    def _calculate_risk_metrics(self, result: BacktestResult) -> RiskMetrics:
        """Calculate risk-related metrics.

        Args:
            result: Backtest result

        Returns:
            RiskMetrics
        """
        returns = result.daily_returns
        if not returns:
            return RiskMetrics(max_drawdown=result.max_drawdown)

        # Convert to float for calculations
        returns_float = [float(r) for r in returns]

        # Basic statistics
        n = len(returns_float)
        avg_return = sum(returns_float) / n
        variance = sum((r - avg_return) ** 2 for r in returns_float) / n
        std_dev = variance ** 0.5 if variance > 0 else 0.001

        # Daily risk-free rate
        daily_rf = float(self.risk_free_rate) / 252

        # Sharpe ratio (annualized)
        if std_dev > 0:
            sharpe = (avg_return - daily_rf) / std_dev * (252 ** 0.5)
        else:
            sharpe = 0

        # Sortino ratio (downside deviation)
        negative_returns = [r for r in returns_float if r < 0]
        if negative_returns:
            downside_variance = sum(r ** 2 for r in negative_returns) / len(negative_returns)
            downside_dev = downside_variance ** 0.5
            sortino = (avg_return - daily_rf) / downside_dev * (252 ** 0.5) if downside_dev > 0 else 0
        else:
            sortino = 0

        # Calmar ratio
        max_dd = float(result.max_drawdown)
        annual_return = float(result.annualized_return)
        calmar = annual_return / max_dd if max_dd > 0 else 0

        # VaR and CVaR (95%)
        sorted_returns = sorted(returns_float)
        var_idx = int(n * 0.05)
        var_95 = abs(sorted_returns[var_idx]) if var_idx < n else 0
        cvar_95 = abs(sum(sorted_returns[:var_idx + 1]) / (var_idx + 1)) if var_idx > 0 else var_95

        # Tail ratio
        upper_idx = int(n * 0.95)
        if var_idx < n and upper_idx < n and sorted_returns[var_idx] != 0:
            tail_ratio = abs(sorted_returns[upper_idx] / sorted_returns[var_idx])
        else:
            tail_ratio = 0

        # Omega ratio (threshold = 0)
        gains = sum(r for r in returns_float if r > 0)
        losses = abs(sum(r for r in returns_float if r < 0))
        omega = gains / losses if losses > 0 else 0

        # Recovery factor
        total_return = float(result.total_return)
        recovery = total_return / max_dd if max_dd > 0 else 0

        # Ulcer index (pain index)
        drawdowns = [float(s.drawdown) for s in result.snapshots if s.drawdown > ZERO]
        if drawdowns:
            ulcer_squared = sum(d ** 2 for d in drawdowns) / len(drawdowns)
            ulcer = ulcer_squared ** 0.5
        else:
            ulcer = 0

        # Pain ratio
        pain = sum(drawdowns) / len(drawdowns) if drawdowns else 0
        pain_ratio = (annual_return - float(self.risk_free_rate) * 100) / pain if pain > 0 else 0

        # Gain to pain ratio
        total_pnl = sum(t.pnl for t in result.trades)
        total_abs_pnl = sum(abs(t.pnl) for t in result.trades if t.pnl < ZERO)
        gain_to_pain = float(total_pnl) / float(total_abs_pnl) if total_abs_pnl > ZERO else 0

        # Max drawdown duration
        dd_duration = self._calculate_drawdown_duration(result.snapshots)

        return RiskMetrics(
            sharpe_ratio=Decimal(str(round(sharpe, 4))),
            sortino_ratio=Decimal(str(round(sortino, 4))),
            calmar_ratio=Decimal(str(round(calmar, 4))),
            omega_ratio=Decimal(str(round(omega, 4))),
            tail_ratio=Decimal(str(round(tail_ratio, 4))),
            var_95=Decimal(str(round(var_95 * 100, 4))),  # As percentage
            cvar_95=Decimal(str(round(cvar_95 * 100, 4))),
            max_drawdown=result.max_drawdown,
            max_drawdown_duration=dd_duration,
            recovery_factor=Decimal(str(round(recovery, 4))),
            ulcer_index=Decimal(str(round(ulcer, 4))),
            pain_ratio=Decimal(str(round(pain_ratio, 4))),
            gain_to_pain_ratio=Decimal(str(round(gain_to_pain, 4))),
        )

    def _calculate_drawdown_duration(self, snapshots: list[BacktestSnapshot]) -> int:
        """Calculate maximum drawdown duration.

        Args:
            snapshots: Portfolio snapshots

        Returns:
            Duration in days
        """
        if not snapshots:
            return 0

        max_duration = 0
        current_duration = 0
        in_drawdown = False

        for snapshot in snapshots:
            if snapshot.drawdown > ZERO:
                if not in_drawdown:
                    in_drawdown = True
                    current_duration = 1
                else:
                    current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                in_drawdown = False
                current_duration = 0

        return max_duration

    def _analyze_drawdowns(self, result: BacktestResult) -> DrawdownAnalysis:
        """Analyze drawdown periods.

        Args:
            result: Backtest result

        Returns:
            DrawdownAnalysis
        """
        snapshots = result.snapshots
        if not snapshots:
            return DrawdownAnalysis()

        # Current drawdown
        current_dd = snapshots[-1].drawdown if snapshots else ZERO

        # Max drawdown tracking
        max_dd = ZERO
        max_dd_start: Optional[datetime] = None
        max_dd_end: Optional[datetime] = None
        max_dd_duration = 0

        # Track underwater periods
        underwater_periods = []
        in_drawdown = False
        dd_start: Optional[datetime] = None
        current_dd_depth = ZERO
        current_duration = 0

        for snapshot in snapshots:
            if snapshot.drawdown > ZERO:
                if not in_drawdown:
                    in_drawdown = True
                    dd_start = snapshot.timestamp
                    current_dd_depth = snapshot.drawdown
                    current_duration = 1
                else:
                    current_duration += 1
                    current_dd_depth = max(current_dd_depth, snapshot.drawdown)

                # Track max drawdown
                if snapshot.drawdown > max_dd:
                    max_dd = snapshot.drawdown
                    max_dd_start = dd_start
                    max_dd_duration = current_duration
            else:
                if in_drawdown and dd_start:
                    underwater_periods.append((dd_start, snapshot.timestamp, current_dd_depth))
                    max_dd_end = snapshot.timestamp
                in_drawdown = False
                dd_start = None
                current_dd_depth = ZERO
                current_duration = 0

        # If still in drawdown at end
        if in_drawdown and dd_start:
            underwater_periods.append((dd_start, snapshots[-1].timestamp, current_dd_depth))

        # Average drawdown
        all_dds = [s.drawdown for s in snapshots if s.drawdown > ZERO]
        avg_dd = sum(all_dds) / len(all_dds) if all_dds else ZERO

        return DrawdownAnalysis(
            current_drawdown=current_dd,
            max_drawdown=max_dd,
            max_drawdown_start=max_dd_start,
            max_drawdown_end=max_dd_end,
            max_drawdown_duration=max_dd_duration,
            avg_drawdown=avg_dd,
            drawdown_count=len(underwater_periods),
            underwater_periods=underwater_periods,
        )

    def _calculate_periodic_performance(
        self,
        result: BacktestResult,
        timeframe: TimeFrame,
    ) -> list[PerformanceBreakdown]:
        """Calculate performance breakdown by period.

        Args:
            result: Backtest result
            timeframe: Time frame for breakdown

        Returns:
            List of PerformanceBreakdown
        """
        snapshots = result.snapshots
        trades = result.trades
        if not snapshots:
            return []

        # Group snapshots by period
        periods: dict[str, list[BacktestSnapshot]] = {}

        for snapshot in snapshots:
            if timeframe == TimeFrame.MONTHLY:
                period_key = snapshot.timestamp.strftime("%Y-%m")
            elif timeframe == TimeFrame.YEARLY:
                period_key = snapshot.timestamp.strftime("%Y")
            elif timeframe == TimeFrame.QUARTERLY:
                quarter = (snapshot.timestamp.month - 1) // 3 + 1
                period_key = f"{snapshot.timestamp.year}-Q{quarter}"
            elif timeframe == TimeFrame.WEEKLY:
                period_key = snapshot.timestamp.strftime("%Y-W%W")
            else:
                period_key = snapshot.timestamp.strftime("%Y-%m-%d")

            if period_key not in periods:
                periods[period_key] = []
            periods[period_key].append(snapshot)

        # Calculate metrics for each period
        breakdowns = []
        for period_key in sorted(periods.keys()):
            period_snapshots = periods[period_key]
            if len(period_snapshots) < 2:
                continue

            start_value = period_snapshots[0].total_value
            end_value = period_snapshots[-1].total_value
            return_pct = (end_value - start_value) / start_value * HUNDRED if start_value > ZERO else ZERO

            # Count trades in period
            period_start = period_snapshots[0].timestamp
            period_end = period_snapshots[-1].timestamp
            period_trades = [t for t in trades if period_start <= t.timestamp <= period_end]
            period_winners = [t for t in period_trades if t.pnl > ZERO]
            period_pnl = sum(t.pnl for t in period_trades)

            # Max drawdown in period
            period_dd = max(s.drawdown for s in period_snapshots)

            breakdowns.append(PerformanceBreakdown(
                period=period_key,
                start_date=period_start,
                end_date=period_end,
                return_pct=return_pct,
                trades=len(period_trades),
                winning_trades=len(period_winners),
                pnl=period_pnl,
                max_drawdown=period_dd,
            ))

        return breakdowns

    def _calculate_benchmark_comparison(
        self,
        result: BacktestResult,
        benchmark_returns: list[Decimal],
    ) -> BenchmarkComparison:
        """Calculate benchmark comparison metrics.

        Args:
            result: Backtest result
            benchmark_returns: Benchmark daily returns

        Returns:
            BenchmarkComparison
        """
        strategy_returns = result.daily_returns
        if not strategy_returns or not benchmark_returns:
            return BenchmarkComparison()

        # Align lengths
        min_len = min(len(strategy_returns), len(benchmark_returns))
        strat = [float(r) for r in strategy_returns[:min_len]]
        bench = [float(r) for r in benchmark_returns[:min_len]]

        n = len(strat)
        if n < 2:
            return BenchmarkComparison()

        # Returns
        strat_total = float(result.total_return)
        bench_total = (1 + sum(bench)) - 1
        excess = strat_total - bench_total * 100

        # Correlation and beta
        strat_mean = sum(strat) / n
        bench_mean = sum(bench) / n

        covariance = sum((s - strat_mean) * (b - bench_mean) for s, b in zip(strat, bench)) / n
        bench_variance = sum((b - bench_mean) ** 2 for b in bench) / n
        strat_variance = sum((s - strat_mean) ** 2 for s in strat) / n

        beta = covariance / bench_variance if bench_variance > 0 else 0
        correlation = covariance / ((strat_variance ** 0.5) * (bench_variance ** 0.5)) if strat_variance > 0 and bench_variance > 0 else 0

        # Alpha (annualized)
        daily_rf = float(self.risk_free_rate) / 252
        alpha = (strat_mean - daily_rf - beta * (bench_mean - daily_rf)) * 252

        # Tracking error
        excess_returns = [s - b for s, b in zip(strat, bench)]
        excess_mean = sum(excess_returns) / n
        tracking_variance = sum((e - excess_mean) ** 2 for e in excess_returns) / n
        tracking_error = (tracking_variance ** 0.5) * (252 ** 0.5)

        # Information ratio
        info_ratio = excess / (tracking_error * 100) if tracking_error > 0 else 0

        # Capture ratios
        up_strat = [s for s, b in zip(strat, bench) if b > 0]
        up_bench = [b for b in bench if b > 0]
        down_strat = [s for s, b in zip(strat, bench) if b < 0]
        down_bench = [b for b in bench if b < 0]

        up_capture = (sum(up_strat) / sum(up_bench) * 100) if up_bench and sum(up_bench) != 0 else 0
        down_capture = (sum(down_strat) / sum(down_bench) * 100) if down_bench and sum(down_bench) != 0 else 0
        capture_ratio = up_capture / down_capture if down_capture != 0 else 0

        return BenchmarkComparison(
            benchmark_symbol=result.config.benchmark_symbol,
            benchmark_return=Decimal(str(round(bench_total * 100, 4))),
            strategy_return=result.total_return,
            excess_return=Decimal(str(round(excess, 4))),
            alpha=Decimal(str(round(alpha * 100, 4))),
            beta=Decimal(str(round(beta, 4))),
            correlation=Decimal(str(round(correlation, 4))),
            tracking_error=Decimal(str(round(tracking_error * 100, 4))),
            information_ratio=Decimal(str(round(info_ratio, 4))),
            up_capture=Decimal(str(round(up_capture, 4))),
            down_capture=Decimal(str(round(down_capture, 4))),
            capture_ratio=Decimal(str(round(capture_ratio, 4))),
        )

    def _analyze_trades(self, result: BacktestResult) -> list[TradeAnalysis]:
        """Analyze individual trades.

        Args:
            result: Backtest result

        Returns:
            List of TradeAnalysis
        """
        analyses = []

        for trade in result.trades:
            # Calculate return percentage
            trade_cost = trade.base_price * trade.quantity
            return_pct = trade.pnl / trade_cost * HUNDRED if trade_cost > ZERO else ZERO

            # Efficiency (how much of the move was captured)
            # Would need intraday data for proper MAE/MFE calculation
            # Using simplified version
            efficiency = Decimal("1") if trade.pnl > ZERO else ZERO

            analyses.append(TradeAnalysis(
                trade=trade,
                return_pct=return_pct,
                efficiency=efficiency,
            ))

        return analyses

    def _identify_patterns(self, result: BacktestResult) -> list[TradePattern]:
        """Identify trade patterns.

        Args:
            result: Backtest result

        Returns:
            List of TradePattern
        """
        patterns = []

        # Day of week pattern
        day_stats: dict[int, list[BacktestTrade]] = {i: [] for i in range(7)}
        for trade in result.trades:
            day_stats[trade.timestamp.weekday()].append(trade)

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day, trades in day_stats.items():
            if trades:
                winners = sum(1 for t in trades if t.pnl > ZERO)
                win_rate = Decimal(str(winners)) / Decimal(str(len(trades))) * HUNDRED
                avg_return = sum(t.pnl for t in trades) / len(trades)
                patterns.append(TradePattern(
                    pattern_name=f"Day:{day_names[day]}",
                    occurrences=len(trades),
                    win_rate=win_rate,
                    avg_return=avg_return,
                    total_pnl=sum(t.pnl for t in trades),
                ))

        # Hour of day pattern (if trades have time component)
        hour_stats: dict[int, list[BacktestTrade]] = {}
        for trade in result.trades:
            hour = trade.timestamp.hour
            if hour not in hour_stats:
                hour_stats[hour] = []
            hour_stats[hour].append(trade)

        for hour, trades in sorted(hour_stats.items()):
            if len(trades) >= 3:  # Minimum sample size
                winners = sum(1 for t in trades if t.pnl > ZERO)
                win_rate = Decimal(str(winners)) / Decimal(str(len(trades))) * HUNDRED
                avg_return = sum(t.pnl for t in trades) / len(trades)
                patterns.append(TradePattern(
                    pattern_name=f"Hour:{hour:02d}:00",
                    occurrences=len(trades),
                    win_rate=win_rate,
                    avg_return=avg_return,
                    total_pnl=sum(t.pnl for t in trades),
                ))

        return patterns

    def _get_extreme_trades(
        self,
        result: BacktestResult,
    ) -> tuple[list[BacktestTrade], list[BacktestTrade]]:
        """Get best and worst trades.

        Args:
            result: Backtest result

        Returns:
            Tuple of (best_trades, worst_trades)
        """
        sorted_trades = sorted(result.trades, key=lambda t: t.pnl, reverse=True)

        best = sorted_trades[: self.top_n_trades]
        worst = sorted_trades[-self.top_n_trades:] if len(sorted_trades) >= self.top_n_trades else sorted_trades

        return best, worst


# ============================================================================
# Factory Functions
# ============================================================================

def create_results_analyzer(
    risk_free_rate: Decimal = Decimal("0.05"),
    top_n_trades: int = 10,
) -> ResultsAnalyzer:
    """Create a configured results analyzer.

    Args:
        risk_free_rate: Annual risk-free rate
        top_n_trades: Number of extreme trades to track

    Returns:
        Configured ResultsAnalyzer
    """
    return ResultsAnalyzer(
        risk_free_rate=risk_free_rate,
        top_n_trades=top_n_trades,
    )
