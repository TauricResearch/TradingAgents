"""Portfolio Performance Metrics.

This module provides comprehensive portfolio performance calculations:
- Returns (daily, monthly, yearly, cumulative)
- Risk-adjusted metrics (Sharpe, Sortino, Calmar)
- Drawdown analysis
- Trade statistics (win rate, profit factor)
- Benchmark comparison

Issue #31: [PORT-30] Performance metrics - Sharpe, drawdown, returns

Design Principles:
    - Industry-standard calculations
    - Vectorized operations for efficiency
    - Support for various time periods
    - Benchmark-relative metrics
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import math


class Period(Enum):
    """Time period for performance calculations."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


@dataclass
class ReturnSeries:
    """A series of returns over time.

    Attributes:
        returns: List of (date, return) tuples
        period: The time period between returns
        annualization_factor: Factor for annualizing metrics
    """
    returns: List[Tuple[date, Decimal]]
    period: Period = Period.DAILY
    annualization_factor: int = 252  # Trading days per year

    def __post_init__(self):
        # Set appropriate annualization factor based on period
        if self.period == Period.DAILY:
            self.annualization_factor = 252
        elif self.period == Period.WEEKLY:
            self.annualization_factor = 52
        elif self.period == Period.MONTHLY:
            self.annualization_factor = 12
        elif self.period == Period.QUARTERLY:
            self.annualization_factor = 4
        elif self.period == Period.YEARLY:
            self.annualization_factor = 1

    @property
    def values(self) -> List[Decimal]:
        """Get just the return values."""
        return [r[1] for r in self.returns]

    @property
    def dates(self) -> List[date]:
        """Get just the dates."""
        return [r[0] for r in self.returns]

    @property
    def num_periods(self) -> int:
        """Number of periods in the series."""
        return len(self.returns)


@dataclass
class DrawdownInfo:
    """Information about a drawdown period.

    Attributes:
        start_date: When the drawdown began
        trough_date: Date of maximum drawdown
        end_date: When the drawdown recovered (None if ongoing)
        peak_value: Portfolio value at peak
        trough_value: Portfolio value at trough
        max_drawdown: Maximum drawdown percentage
        duration_days: Total duration in days
        recovery_days: Days from trough to recovery (None if ongoing)
    """
    start_date: date
    trough_date: date
    end_date: Optional[date]
    peak_value: Decimal
    trough_value: Decimal
    max_drawdown: Decimal
    duration_days: int
    recovery_days: Optional[int] = None

    @property
    def is_recovered(self) -> bool:
        """Check if drawdown has recovered."""
        return self.end_date is not None


@dataclass
class TradeStats:
    """Trade-level statistics.

    Attributes:
        total_trades: Total number of trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        breakeven_trades: Number of breakeven trades
        win_rate: Percentage of winning trades
        loss_rate: Percentage of losing trades
        avg_win: Average winning trade return
        avg_loss: Average losing trade return
        largest_win: Largest winning trade
        largest_loss: Largest losing trade
        profit_factor: Gross profit / Gross loss
        avg_trade: Average trade return
        expectancy: Expected value per trade
    """
    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: Decimal
    loss_rate: Decimal
    avg_win: Decimal
    avg_loss: Decimal
    largest_win: Decimal
    largest_loss: Decimal
    profit_factor: Decimal
    avg_trade: Decimal
    expectancy: Decimal


@dataclass
class PerformanceMetrics:
    """Complete performance metrics summary.

    Attributes:
        start_date: Analysis start date
        end_date: Analysis end date
        total_return: Total cumulative return
        annualized_return: Annualized return
        volatility: Annualized volatility (std dev of returns)
        sharpe_ratio: Risk-adjusted return (return / volatility)
        sortino_ratio: Downside risk-adjusted return
        calmar_ratio: Return / max drawdown
        max_drawdown: Maximum peak-to-trough decline
        current_drawdown: Current drawdown from peak
        avg_drawdown: Average drawdown
        num_drawdowns: Number of drawdown periods
        best_day: Best single-day return
        worst_day: Worst single-day return
        positive_periods: Number of positive return periods
        negative_periods: Number of negative return periods
        trade_stats: Trade-level statistics (if available)
        benchmark_alpha: Alpha vs benchmark (if available)
        benchmark_beta: Beta vs benchmark (if available)
        information_ratio: Risk-adjusted excess return vs benchmark
        tracking_error: Std dev of excess returns vs benchmark
    """
    start_date: date
    end_date: date
    total_return: Decimal
    annualized_return: Decimal
    volatility: Decimal
    sharpe_ratio: Decimal
    sortino_ratio: Decimal
    calmar_ratio: Decimal
    max_drawdown: Decimal
    current_drawdown: Decimal
    avg_drawdown: Decimal
    num_drawdowns: int
    best_day: Decimal
    worst_day: Decimal
    positive_periods: int
    negative_periods: int
    trade_stats: Optional[TradeStats] = None
    benchmark_alpha: Optional[Decimal] = None
    benchmark_beta: Optional[Decimal] = None
    information_ratio: Optional[Decimal] = None
    tracking_error: Optional[Decimal] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PerformanceCalculator:
    """Calculator for portfolio performance metrics.

    Provides industry-standard performance calculations including:
    - Returns and volatility
    - Risk-adjusted metrics (Sharpe, Sortino, Calmar)
    - Drawdown analysis
    - Trade statistics
    - Benchmark comparison

    Example:
        >>> calculator = PerformanceCalculator(risk_free_rate=Decimal("0.05"))
        >>> returns = ReturnSeries([
        ...     (date(2024, 1, 1), Decimal("0.01")),
        ...     (date(2024, 1, 2), Decimal("-0.005")),
        ...     (date(2024, 1, 3), Decimal("0.02")),
        ... ])
        >>> metrics = calculator.calculate_metrics(returns)
        >>> print(f"Sharpe: {metrics.sharpe_ratio}")
    """

    def __init__(
        self,
        risk_free_rate: Decimal = Decimal("0.05"),
        min_acceptable_return: Optional[Decimal] = None,
    ):
        """Initialize the calculator.

        Args:
            risk_free_rate: Annual risk-free rate for Sharpe calculation
            min_acceptable_return: MAR for Sortino (defaults to 0)
        """
        self.risk_free_rate = risk_free_rate
        self.min_acceptable_return = min_acceptable_return or Decimal("0")

    def calculate_returns(
        self,
        values: List[Tuple[date, Decimal]],
        period: Period = Period.DAILY,
    ) -> ReturnSeries:
        """Calculate returns from a series of portfolio values.

        Args:
            values: List of (date, value) tuples representing portfolio NAV
            period: Time period of the values

        Returns:
            ReturnSeries with calculated returns
        """
        if len(values) < 2:
            return ReturnSeries(returns=[], period=period)

        returns = []
        for i in range(1, len(values)):
            prev_date, prev_value = values[i - 1]
            curr_date, curr_value = values[i]

            if prev_value != 0:
                ret = (curr_value - prev_value) / prev_value
            else:
                ret = Decimal("0")

            returns.append((curr_date, ret))

        return ReturnSeries(returns=returns, period=period)

    def total_return(self, returns: ReturnSeries) -> Decimal:
        """Calculate total cumulative return.

        Uses geometric linking: (1 + r1) * (1 + r2) * ... - 1
        """
        if not returns.values:
            return Decimal("0")

        cumulative = Decimal("1")
        for r in returns.values:
            cumulative *= (Decimal("1") + r)

        return (cumulative - Decimal("1")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def annualized_return(self, returns: ReturnSeries) -> Decimal:
        """Calculate annualized return.

        Annualized = (1 + total_return) ^ (periods_per_year / num_periods) - 1
        """
        if returns.num_periods == 0:
            return Decimal("0")

        total = self.total_return(returns)
        cumulative = Decimal("1") + total

        # Calculate annualization exponent
        years = Decimal(returns.num_periods) / Decimal(returns.annualization_factor)
        if years <= 0:
            return Decimal("0")

        # (1 + total)^(1/years) - 1
        try:
            annualized = Decimal(float(cumulative) ** float(Decimal("1") / years)) - Decimal("1")
            # Handle extreme values that can't be quantized
            if annualized > Decimal("1e10") or annualized < Decimal("-1e10"):
                return annualized.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            return annualized.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        except (OverflowError, InvalidOperation):
            # Return the unquantized value for extreme cases
            return Decimal(str(float(cumulative) ** float(Decimal("1") / years) - 1))

    def volatility(self, returns: ReturnSeries, annualize: bool = True) -> Decimal:
        """Calculate volatility (standard deviation of returns).

        Args:
            returns: ReturnSeries to analyze
            annualize: Whether to annualize the volatility

        Returns:
            Volatility as a decimal (0.20 = 20%)
        """
        if returns.num_periods < 2:
            return Decimal("0")

        values = [float(r) for r in returns.values]
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        std_dev = math.sqrt(variance)

        if annualize:
            std_dev *= math.sqrt(returns.annualization_factor)

        return Decimal(str(std_dev)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def downside_deviation(self, returns: ReturnSeries, annualize: bool = True) -> Decimal:
        """Calculate downside deviation (only negative returns).

        Used for Sortino ratio calculation.
        """
        if returns.num_periods < 2:
            return Decimal("0")

        # Only consider returns below MAR
        mar = float(self.min_acceptable_return)
        downside_returns = [float(r) for r in returns.values if float(r) < mar]

        if len(downside_returns) < 2:
            return Decimal("0")

        # Calculate semi-variance
        variance = sum((r - mar) ** 2 for r in downside_returns) / len(downside_returns)
        std_dev = math.sqrt(variance)

        if annualize:
            std_dev *= math.sqrt(returns.annualization_factor)

        return Decimal(str(std_dev)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def sharpe_ratio(self, returns: ReturnSeries) -> Decimal:
        """Calculate Sharpe ratio.

        Sharpe = (Annualized Return - Risk Free Rate) / Annualized Volatility
        """
        ann_return = self.annualized_return(returns)
        vol = self.volatility(returns)

        if vol == 0:
            return Decimal("0")

        sharpe = (ann_return - self.risk_free_rate) / vol
        return sharpe.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def sortino_ratio(self, returns: ReturnSeries) -> Decimal:
        """Calculate Sortino ratio.

        Sortino = (Annualized Return - MAR) / Downside Deviation

        Similar to Sharpe but only penalizes downside volatility.
        """
        ann_return = self.annualized_return(returns)
        downside = self.downside_deviation(returns)

        if downside == 0:
            return Decimal("0")

        sortino = (ann_return - self.min_acceptable_return) / downside
        return sortino.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def calmar_ratio(self, returns: ReturnSeries, max_dd: Optional[Decimal] = None) -> Decimal:
        """Calculate Calmar ratio.

        Calmar = Annualized Return / Max Drawdown

        Measures return relative to worst-case loss.
        """
        ann_return = self.annualized_return(returns)

        if max_dd is None:
            # Calculate from cumulative returns
            cum_returns = self._cumulative_returns(returns.values)
            max_dd = self.max_drawdown(cum_returns)

        if max_dd == 0:
            return Decimal("0")

        calmar = ann_return / abs(max_dd)
        return calmar.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _cumulative_returns(self, returns: List[Decimal]) -> List[Decimal]:
        """Calculate cumulative returns from simple returns."""
        cumulative = []
        cum = Decimal("1")
        for r in returns:
            cum *= (Decimal("1") + r)
            cumulative.append(cum - Decimal("1"))
        return cumulative

    def max_drawdown(self, cumulative_returns: List[Decimal]) -> Decimal:
        """Calculate maximum drawdown from cumulative returns.

        Max Drawdown = (Trough - Peak) / Peak

        Args:
            cumulative_returns: List of cumulative returns (0.10 = 10% gain)

        Returns:
            Maximum drawdown as a negative decimal (-0.20 = -20% drawdown)
        """
        if not cumulative_returns:
            return Decimal("0")

        # Convert to portfolio values (starting at 1)
        values = [Decimal("1") + r for r in cumulative_returns]

        peak = values[0]
        max_dd = Decimal("0")

        for value in values:
            if value > peak:
                peak = value
            dd = (value - peak) / peak
            if dd < max_dd:
                max_dd = dd

        return max_dd.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def drawdown_series(
        self,
        values: List[Tuple[date, Decimal]]
    ) -> List[Tuple[date, Decimal]]:
        """Calculate drawdown for each date.

        Args:
            values: List of (date, portfolio_value) tuples

        Returns:
            List of (date, drawdown) tuples
        """
        if not values:
            return []

        result = []
        peak = values[0][1]

        for dt, value in values:
            if value > peak:
                peak = value
            dd = (value - peak) / peak if peak != 0 else Decimal("0")
            result.append((dt, dd))

        return result

    def find_drawdowns(
        self,
        values: List[Tuple[date, Decimal]],
        min_drawdown: Decimal = Decimal("-0.05"),
    ) -> List[DrawdownInfo]:
        """Find all drawdown periods.

        Args:
            values: List of (date, portfolio_value) tuples
            min_drawdown: Minimum drawdown to include (-0.05 = -5%)

        Returns:
            List of DrawdownInfo objects
        """
        if len(values) < 2:
            return []

        dd_series = self.drawdown_series(values)
        drawdowns = []

        peak_value = values[0][1]
        peak_date = values[0][0]
        trough_value = peak_value
        trough_date = peak_date
        in_drawdown = False
        current_dd = Decimal("0")

        for i, (dt, dd) in enumerate(dd_series):
            value = values[i][1]

            if not in_drawdown:
                if dd < min_drawdown:
                    # Start of new drawdown
                    in_drawdown = True
                    peak_date = dd_series[i - 1][0] if i > 0 else dt
                    peak_value = values[i - 1][1] if i > 0 else value
                    trough_date = dt
                    trough_value = value
                    current_dd = dd
            else:
                if dd < current_dd:
                    # New trough
                    trough_date = dt
                    trough_value = value
                    current_dd = dd

                if value >= peak_value:
                    # Recovered
                    drawdowns.append(DrawdownInfo(
                        start_date=peak_date,
                        trough_date=trough_date,
                        end_date=dt,
                        peak_value=peak_value,
                        trough_value=trough_value,
                        max_drawdown=current_dd,
                        duration_days=(dt - peak_date).days,
                        recovery_days=(dt - trough_date).days,
                    ))
                    in_drawdown = False
                    peak_value = value
                    peak_date = dt

            # Update peak if not in drawdown
            if not in_drawdown and value > peak_value:
                peak_value = value
                peak_date = dt

        # Handle ongoing drawdown
        if in_drawdown:
            final_date = dd_series[-1][0]
            drawdowns.append(DrawdownInfo(
                start_date=peak_date,
                trough_date=trough_date,
                end_date=None,
                peak_value=peak_value,
                trough_value=trough_value,
                max_drawdown=current_dd,
                duration_days=(final_date - peak_date).days,
                recovery_days=None,
            ))

        return drawdowns

    def trade_statistics(self, trade_returns: List[Decimal]) -> TradeStats:
        """Calculate trade-level statistics.

        Args:
            trade_returns: List of individual trade returns (P&L / cost)

        Returns:
            TradeStats with comprehensive trade analysis
        """
        if not trade_returns:
            return TradeStats(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                breakeven_trades=0,
                win_rate=Decimal("0"),
                loss_rate=Decimal("0"),
                avg_win=Decimal("0"),
                avg_loss=Decimal("0"),
                largest_win=Decimal("0"),
                largest_loss=Decimal("0"),
                profit_factor=Decimal("0"),
                avg_trade=Decimal("0"),
                expectancy=Decimal("0"),
            )

        winning = [r for r in trade_returns if r > 0]
        losing = [r for r in trade_returns if r < 0]
        breakeven = [r for r in trade_returns if r == 0]

        total = len(trade_returns)
        num_wins = len(winning)
        num_losses = len(losing)
        num_be = len(breakeven)

        win_rate = Decimal(num_wins) / Decimal(total) * 100 if total > 0 else Decimal("0")
        loss_rate = Decimal(num_losses) / Decimal(total) * 100 if total > 0 else Decimal("0")

        avg_win = sum(winning) / len(winning) if winning else Decimal("0")
        avg_loss = sum(losing) / len(losing) if losing else Decimal("0")

        largest_win = max(winning) if winning else Decimal("0")
        largest_loss = min(losing) if losing else Decimal("0")

        gross_profit = sum(winning)
        gross_loss = abs(sum(losing)) if losing else Decimal("0")
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else Decimal("0")

        avg_trade = sum(trade_returns) / len(trade_returns)

        # Expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        expectancy = (win_rate / 100 * avg_win) + (loss_rate / 100 * avg_loss)

        return TradeStats(
            total_trades=total,
            winning_trades=num_wins,
            losing_trades=num_losses,
            breakeven_trades=num_be,
            win_rate=win_rate.quantize(Decimal("0.01")),
            loss_rate=loss_rate.quantize(Decimal("0.01")),
            avg_win=avg_win.quantize(Decimal("0.0001")),
            avg_loss=avg_loss.quantize(Decimal("0.0001")),
            largest_win=largest_win.quantize(Decimal("0.0001")),
            largest_loss=largest_loss.quantize(Decimal("0.0001")),
            profit_factor=profit_factor.quantize(Decimal("0.01")),
            avg_trade=avg_trade.quantize(Decimal("0.0001")),
            expectancy=expectancy.quantize(Decimal("0.0001")),
        )

    def benchmark_comparison(
        self,
        portfolio_returns: ReturnSeries,
        benchmark_returns: ReturnSeries,
    ) -> Dict[str, Decimal]:
        """Compare portfolio performance against a benchmark.

        Calculates:
        - Alpha: Excess return not explained by beta
        - Beta: Sensitivity to benchmark movements
        - Information Ratio: Risk-adjusted excess return
        - Tracking Error: Volatility of excess returns
        - Up Capture: Performance when benchmark is up
        - Down Capture: Performance when benchmark is down

        Args:
            portfolio_returns: Portfolio return series
            benchmark_returns: Benchmark return series

        Returns:
            Dictionary with comparison metrics
        """
        if portfolio_returns.num_periods != benchmark_returns.num_periods:
            raise ValueError("Portfolio and benchmark must have same number of periods")

        if portfolio_returns.num_periods < 2:
            return {
                "alpha": Decimal("0"),
                "beta": Decimal("0"),
                "information_ratio": Decimal("0"),
                "tracking_error": Decimal("0"),
                "up_capture": Decimal("0"),
                "down_capture": Decimal("0"),
            }

        port_vals = [float(r) for r in portfolio_returns.values]
        bench_vals = [float(r) for r in benchmark_returns.values]

        # Calculate beta using covariance / variance
        n = len(port_vals)
        port_mean = sum(port_vals) / n
        bench_mean = sum(bench_vals) / n

        covariance = sum((port_vals[i] - port_mean) * (bench_vals[i] - bench_mean)
                        for i in range(n)) / (n - 1)
        bench_variance = sum((x - bench_mean) ** 2 for x in bench_vals) / (n - 1)

        beta = covariance / bench_variance if bench_variance != 0 else 0

        # Calculate alpha using CAPM: alpha = port_return - (rf + beta * (bench - rf))
        port_ann_return = float(self.annualized_return(portfolio_returns))
        bench_ann_return = float(self.annualized_return(benchmark_returns))
        rf = float(self.risk_free_rate)

        alpha = port_ann_return - (rf + beta * (bench_ann_return - rf))

        # Calculate excess returns and tracking error
        excess_returns = [port_vals[i] - bench_vals[i] for i in range(n)]
        excess_mean = sum(excess_returns) / n
        tracking_error = math.sqrt(
            sum((x - excess_mean) ** 2 for x in excess_returns) / (n - 1)
        )
        tracking_error *= math.sqrt(portfolio_returns.annualization_factor)

        # Information ratio
        information_ratio = (port_ann_return - bench_ann_return) / tracking_error if tracking_error != 0 else 0

        # Up/Down capture
        up_periods = [(port_vals[i], bench_vals[i]) for i in range(n) if bench_vals[i] > 0]
        down_periods = [(port_vals[i], bench_vals[i]) for i in range(n) if bench_vals[i] < 0]

        up_capture = Decimal("0")
        if up_periods:
            avg_port_up = sum(p[0] for p in up_periods) / len(up_periods)
            avg_bench_up = sum(p[1] for p in up_periods) / len(up_periods)
            up_capture = Decimal(str(avg_port_up / avg_bench_up * 100)) if avg_bench_up != 0 else Decimal("0")

        down_capture = Decimal("0")
        if down_periods:
            avg_port_down = sum(p[0] for p in down_periods) / len(down_periods)
            avg_bench_down = sum(p[1] for p in down_periods) / len(down_periods)
            down_capture = Decimal(str(avg_port_down / avg_bench_down * 100)) if avg_bench_down != 0 else Decimal("0")

        return {
            "alpha": Decimal(str(alpha)).quantize(Decimal("0.0001")),
            "beta": Decimal(str(beta)).quantize(Decimal("0.01")),
            "information_ratio": Decimal(str(information_ratio)).quantize(Decimal("0.01")),
            "tracking_error": Decimal(str(tracking_error)).quantize(Decimal("0.0001")),
            "up_capture": up_capture.quantize(Decimal("0.01")),
            "down_capture": down_capture.quantize(Decimal("0.01")),
        }

    def calculate_metrics(
        self,
        returns: ReturnSeries,
        trade_returns: Optional[List[Decimal]] = None,
        benchmark_returns: Optional[ReturnSeries] = None,
    ) -> PerformanceMetrics:
        """Calculate complete performance metrics.

        Args:
            returns: Portfolio return series
            trade_returns: Optional list of individual trade returns
            benchmark_returns: Optional benchmark return series

        Returns:
            Complete PerformanceMetrics
        """
        if returns.num_periods == 0:
            return PerformanceMetrics(
                start_date=date.today(),
                end_date=date.today(),
                total_return=Decimal("0"),
                annualized_return=Decimal("0"),
                volatility=Decimal("0"),
                sharpe_ratio=Decimal("0"),
                sortino_ratio=Decimal("0"),
                calmar_ratio=Decimal("0"),
                max_drawdown=Decimal("0"),
                current_drawdown=Decimal("0"),
                avg_drawdown=Decimal("0"),
                num_drawdowns=0,
                best_day=Decimal("0"),
                worst_day=Decimal("0"),
                positive_periods=0,
                negative_periods=0,
            )

        # Calculate cumulative returns for drawdown analysis
        cum_returns = self._cumulative_returns(returns.values)
        max_dd = self.max_drawdown(cum_returns)

        # Current drawdown
        if cum_returns:
            values = [Decimal("1") + r for r in cum_returns]
            peak = max(values)
            current_dd = (values[-1] - peak) / peak
        else:
            current_dd = Decimal("0")

        # Find drawdown periods
        portfolio_values = [(returns.dates[i], Decimal("1") + cum_returns[i])
                          for i in range(len(cum_returns))]
        drawdowns = self.find_drawdowns(portfolio_values, min_drawdown=Decimal("-0.01"))

        avg_dd = Decimal("0")
        if drawdowns:
            avg_dd = sum(d.max_drawdown for d in drawdowns) / len(drawdowns)

        # Best/worst days
        best_day = max(returns.values) if returns.values else Decimal("0")
        worst_day = min(returns.values) if returns.values else Decimal("0")

        # Positive/negative periods
        positive = sum(1 for r in returns.values if r > 0)
        negative = sum(1 for r in returns.values if r < 0)

        # Trade statistics
        trade_stats = None
        if trade_returns:
            trade_stats = self.trade_statistics(trade_returns)

        # Benchmark comparison
        benchmark_alpha = None
        benchmark_beta = None
        information_ratio = None
        tracking_error = None

        if benchmark_returns:
            bench_metrics = self.benchmark_comparison(returns, benchmark_returns)
            benchmark_alpha = bench_metrics["alpha"]
            benchmark_beta = bench_metrics["beta"]
            information_ratio = bench_metrics["information_ratio"]
            tracking_error = bench_metrics["tracking_error"]

        return PerformanceMetrics(
            start_date=returns.dates[0],
            end_date=returns.dates[-1],
            total_return=self.total_return(returns),
            annualized_return=self.annualized_return(returns),
            volatility=self.volatility(returns),
            sharpe_ratio=self.sharpe_ratio(returns),
            sortino_ratio=self.sortino_ratio(returns),
            calmar_ratio=self.calmar_ratio(returns, max_dd),
            max_drawdown=max_dd,
            current_drawdown=current_dd.quantize(Decimal("0.0001")),
            avg_drawdown=avg_dd.quantize(Decimal("0.0001")),
            num_drawdowns=len(drawdowns),
            best_day=best_day.quantize(Decimal("0.0001")),
            worst_day=worst_day.quantize(Decimal("0.0001")),
            positive_periods=positive,
            negative_periods=negative,
            trade_stats=trade_stats,
            benchmark_alpha=benchmark_alpha,
            benchmark_beta=benchmark_beta,
            information_ratio=information_ratio,
            tracking_error=tracking_error,
        )


def calculate_cagr(
    start_value: Decimal,
    end_value: Decimal,
    years: Decimal,
) -> Decimal:
    """Calculate Compound Annual Growth Rate.

    CAGR = (End Value / Start Value)^(1/Years) - 1

    Args:
        start_value: Initial portfolio value
        end_value: Final portfolio value
        years: Number of years

    Returns:
        CAGR as a decimal (0.10 = 10%)
    """
    if start_value <= 0 or years <= 0:
        return Decimal("0")

    ratio = float(end_value / start_value)
    cagr = ratio ** (1 / float(years)) - 1
    return Decimal(str(cagr)).quantize(Decimal("0.0001"))


def calculate_rolling_returns(
    returns: ReturnSeries,
    window: int,
) -> List[Tuple[date, Decimal]]:
    """Calculate rolling cumulative returns.

    Args:
        returns: Return series
        window: Rolling window size in periods

    Returns:
        List of (date, rolling_return) tuples
    """
    if returns.num_periods < window:
        return []

    result = []
    for i in range(window - 1, returns.num_periods):
        window_returns = returns.values[i - window + 1:i + 1]
        cumulative = Decimal("1")
        for r in window_returns:
            cumulative *= (Decimal("1") + r)
        result.append((returns.dates[i], cumulative - Decimal("1")))

    return result


def calculate_monthly_returns(
    returns: ReturnSeries,
) -> Dict[Tuple[int, int], Decimal]:
    """Aggregate daily returns to monthly.

    Args:
        returns: Daily return series

    Returns:
        Dictionary of (year, month) -> monthly return
    """
    if returns.period != Period.DAILY:
        raise ValueError("Input must be daily returns")

    monthly: Dict[Tuple[int, int], Decimal] = {}

    for dt, ret in returns.returns:
        key = (dt.year, dt.month)
        if key not in monthly:
            monthly[key] = Decimal("1")
        monthly[key] *= (Decimal("1") + ret)

    # Convert back to returns
    return {k: v - Decimal("1") for k, v in monthly.items()}


def calculate_yearly_returns(
    returns: ReturnSeries,
) -> Dict[int, Decimal]:
    """Aggregate daily returns to yearly.

    Args:
        returns: Daily return series

    Returns:
        Dictionary of year -> yearly return
    """
    if returns.period != Period.DAILY:
        raise ValueError("Input must be daily returns")

    yearly: Dict[int, Decimal] = {}

    for dt, ret in returns.returns:
        if dt.year not in yearly:
            yearly[dt.year] = Decimal("1")
        yearly[dt.year] *= (Decimal("1") + ret)

    # Convert back to returns
    return {k: v - Decimal("1") for k, v in yearly.items()}
