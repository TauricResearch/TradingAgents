"""
Performance analysis for backtesting.

This module computes comprehensive performance metrics and statistics
for backtest results, including returns, risk metrics, and drawdowns.
"""

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple

import pandas as pd
import numpy as np
from scipy import stats

from .exceptions import PerformanceError, InsufficientDataError


logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """
    Container for performance metrics.

    Attributes:
        total_return: Total return over backtest period
        annualized_return: Annualized return
        sharpe_ratio: Sharpe ratio
        sortino_ratio: Sortino ratio
        calmar_ratio: Calmar ratio
        max_drawdown: Maximum drawdown
        max_drawdown_duration: Max drawdown duration in days
        avg_drawdown: Average drawdown
        volatility: Annualized volatility
        downside_deviation: Downside deviation
        win_rate: Percentage of winning trades
        profit_factor: Ratio of gross profit to gross loss
        avg_win: Average winning trade
        avg_loss: Average losing trade
        total_trades: Total number of trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        alpha: Alpha vs benchmark
        beta: Beta vs benchmark
        correlation: Correlation with benchmark
        tracking_error: Tracking error vs benchmark
        information_ratio: Information ratio vs benchmark
    """
    # Return metrics
    total_return: float
    annualized_return: float
    cumulative_return: float

    # Risk-adjusted metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    omega_ratio: float

    # Risk metrics
    volatility: float
    downside_deviation: float
    max_drawdown: float
    avg_drawdown: float
    max_drawdown_duration: int

    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    avg_trade: float
    best_trade: float
    worst_trade: float

    # Benchmark comparison
    alpha: Optional[float] = None
    beta: Optional[float] = None
    correlation: Optional[float] = None
    tracking_error: Optional[float] = None
    information_ratio: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return asdict(self)

    def __str__(self) -> str:
        """String representation of metrics."""
        lines = [
            "Performance Metrics",
            "=" * 50,
            f"Total Return:        {self.total_return:>10.2%}",
            f"Annualized Return:   {self.annualized_return:>10.2%}",
            f"Sharpe Ratio:        {self.sharpe_ratio:>10.2f}",
            f"Sortino Ratio:       {self.sortino_ratio:>10.2f}",
            f"Max Drawdown:        {self.max_drawdown:>10.2%}",
            f"Volatility:          {self.volatility:>10.2%}",
            f"Win Rate:            {self.win_rate:>10.2%}",
            f"Total Trades:        {self.total_trades:>10}",
        ]

        if self.alpha is not None:
            lines.extend([
                "",
                "Benchmark Comparison",
                "-" * 50,
                f"Alpha:               {self.alpha:>10.2%}",
                f"Beta:                {self.beta:>10.2f}",
                f"Correlation:         {self.correlation:>10.2f}",
            ])

        return "\n".join(lines)


class PerformanceAnalyzer:
    """
    Analyzes backtest performance.

    Computes comprehensive metrics including returns, risk, drawdowns,
    and trade statistics.
    """

    def __init__(self, risk_free_rate: Decimal = Decimal("0.02")):
        """
        Initialize performance analyzer.

        Args:
            risk_free_rate: Annual risk-free rate
        """
        self.risk_free_rate = float(risk_free_rate)
        logger.info("PerformanceAnalyzer initialized")

    def analyze(
        self,
        equity_curve: pd.Series,
        trades: pd.DataFrame,
        benchmark: Optional[pd.Series] = None,
    ) -> PerformanceMetrics:
        """
        Analyze performance and compute metrics.

        Args:
            equity_curve: Time series of portfolio value
            trades: DataFrame with trade information
            benchmark: Optional benchmark returns

        Returns:
            PerformanceMetrics object

        Raises:
            InsufficientDataError: If insufficient data for analysis
        """
        if len(equity_curve) < 2:
            raise InsufficientDataError("Insufficient data for performance analysis")

        logger.info(f"Analyzing performance over {len(equity_curve)} periods")

        # Calculate returns
        returns = equity_curve.pct_change().dropna()

        # Return metrics
        total_return = self._calculate_total_return(equity_curve)
        annualized_return = self._calculate_annualized_return(returns)
        cumulative_return = self._calculate_cumulative_return(equity_curve)

        # Risk metrics
        volatility = self._calculate_volatility(returns)
        downside_deviation = self._calculate_downside_deviation(returns)

        # Risk-adjusted metrics
        sharpe_ratio = self._calculate_sharpe_ratio(returns, volatility)
        sortino_ratio = self._calculate_sortino_ratio(returns, downside_deviation)
        calmar_ratio = self._calculate_calmar_ratio(annualized_return, equity_curve)
        omega_ratio = self._calculate_omega_ratio(returns)

        # Drawdown metrics
        drawdowns = self._calculate_drawdowns(equity_curve)
        max_drawdown = self._calculate_max_drawdown(drawdowns)
        avg_drawdown = self._calculate_avg_drawdown(drawdowns)
        max_dd_duration = self._calculate_max_drawdown_duration(drawdowns)

        # Trade statistics
        trade_stats = self._calculate_trade_statistics(trades)

        # Benchmark comparison
        alpha, beta, correlation, tracking_error, info_ratio = None, None, None, None, None
        if benchmark is not None and len(benchmark) > 0:
            benchmark_returns = benchmark.pct_change().dropna()
            alpha, beta = self._calculate_alpha_beta(returns, benchmark_returns)
            correlation = self._calculate_correlation(returns, benchmark_returns)
            tracking_error = self._calculate_tracking_error(returns, benchmark_returns)
            info_ratio = self._calculate_information_ratio(returns, benchmark_returns, tracking_error)

        metrics = PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            cumulative_return=cumulative_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            omega_ratio=omega_ratio,
            volatility=volatility,
            downside_deviation=downside_deviation,
            max_drawdown=max_drawdown,
            avg_drawdown=avg_drawdown,
            max_drawdown_duration=max_dd_duration,
            alpha=alpha,
            beta=beta,
            correlation=correlation,
            tracking_error=tracking_error,
            information_ratio=info_ratio,
            **trade_stats
        )

        logger.info("Performance analysis complete")
        return metrics

    def _calculate_total_return(self, equity_curve: pd.Series) -> float:
        """Calculate total return."""
        return float((equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1)

    def _calculate_annualized_return(self, returns: pd.Series) -> float:
        """Calculate annualized return."""
        if len(returns) == 0:
            return 0.0

        # Assume daily returns, 252 trading days per year
        periods_per_year = 252
        n_periods = len(returns)
        years = n_periods / periods_per_year

        if years == 0:
            return 0.0

        cumulative_return = (1 + returns).prod()
        annualized = float(cumulative_return ** (1 / years) - 1)

        return annualized

    def _calculate_cumulative_return(self, equity_curve: pd.Series) -> float:
        """Calculate cumulative return."""
        return float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1)

    def _calculate_volatility(self, returns: pd.Series) -> float:
        """Calculate annualized volatility."""
        if len(returns) == 0:
            return 0.0

        # Assume daily returns, annualize with sqrt(252)
        daily_vol = returns.std()
        annualized_vol = float(daily_vol * np.sqrt(252))

        return annualized_vol

    def _calculate_downside_deviation(self, returns: pd.Series) -> float:
        """Calculate downside deviation (semi-deviation)."""
        if len(returns) == 0:
            return 0.0

        # Only consider returns below risk-free rate
        daily_rf = self.risk_free_rate / 252
        downside_returns = returns[returns < daily_rf]

        if len(downside_returns) == 0:
            return 0.0

        downside_dev = float(downside_returns.std() * np.sqrt(252))
        return downside_dev

    def _calculate_sharpe_ratio(self, returns: pd.Series, volatility: float) -> float:
        """Calculate Sharpe ratio."""
        if volatility == 0:
            return 0.0

        # Annualized excess return / annualized volatility
        daily_rf = self.risk_free_rate / 252
        excess_returns = returns - daily_rf
        annualized_excess = float(excess_returns.mean() * 252)

        sharpe = annualized_excess / volatility

        return sharpe

    def _calculate_sortino_ratio(self, returns: pd.Series, downside_deviation: float) -> float:
        """Calculate Sortino ratio."""
        if downside_deviation == 0:
            return 0.0

        daily_rf = self.risk_free_rate / 252
        excess_returns = returns - daily_rf
        annualized_excess = float(excess_returns.mean() * 252)

        sortino = annualized_excess / downside_deviation

        return sortino

    def _calculate_calmar_ratio(self, annualized_return: float, equity_curve: pd.Series) -> float:
        """Calculate Calmar ratio."""
        drawdowns = self._calculate_drawdowns(equity_curve)
        max_dd = abs(self._calculate_max_drawdown(drawdowns))

        if max_dd == 0:
            return 0.0

        return annualized_return / max_dd

    def _calculate_omega_ratio(self, returns: pd.Series, threshold: float = 0.0) -> float:
        """Calculate Omega ratio."""
        if len(returns) == 0:
            return 0.0

        returns_above = returns[returns > threshold].sum()
        returns_below = abs(returns[returns < threshold].sum())

        if returns_below == 0:
            return float('inf') if returns_above > 0 else 0.0

        return float(returns_above / returns_below)

    def _calculate_drawdowns(self, equity_curve: pd.Series) -> pd.Series:
        """Calculate drawdown series."""
        cumulative_max = equity_curve.expanding().max()
        drawdowns = (equity_curve - cumulative_max) / cumulative_max
        return drawdowns

    def _calculate_max_drawdown(self, drawdowns: pd.Series) -> float:
        """Calculate maximum drawdown."""
        return float(drawdowns.min())

    def _calculate_avg_drawdown(self, drawdowns: pd.Series) -> float:
        """Calculate average drawdown."""
        # Only consider periods in drawdown
        in_drawdown = drawdowns[drawdowns < 0]

        if len(in_drawdown) == 0:
            return 0.0

        return float(in_drawdown.mean())

    def _calculate_max_drawdown_duration(self, drawdowns: pd.Series) -> int:
        """Calculate maximum drawdown duration in days."""
        if len(drawdowns) == 0:
            return 0

        # Find drawdown periods
        in_drawdown = drawdowns < 0
        drawdown_periods = []
        current_duration = 0

        for dd in in_drawdown:
            if dd:
                current_duration += 1
            else:
                if current_duration > 0:
                    drawdown_periods.append(current_duration)
                current_duration = 0

        if current_duration > 0:
            drawdown_periods.append(current_duration)

        return max(drawdown_periods) if drawdown_periods else 0

    def _calculate_trade_statistics(self, trades: pd.DataFrame) -> Dict[str, Any]:
        """Calculate trade statistics."""
        if trades.empty:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'avg_trade': 0.0,
                'best_trade': 0.0,
                'worst_trade': 0.0,
            }

        # Calculate P&L for each trade
        # Assuming trades DataFrame has 'pnl' column or we calculate it
        if 'pnl' not in trades.columns:
            # If no PnL column, we can't calculate trade stats
            logger.warning("No PnL column in trades DataFrame")
            return {
                'total_trades': len(trades),
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'avg_trade': 0.0,
                'best_trade': 0.0,
                'worst_trade': 0.0,
            }

        pnl = trades['pnl']
        winning_trades = pnl[pnl > 0]
        losing_trades = pnl[pnl < 0]

        total_trades = len(trades)
        num_winning = len(winning_trades)
        num_losing = len(losing_trades)
        win_rate = num_winning / total_trades if total_trades > 0 else 0.0

        avg_win = float(winning_trades.mean()) if len(winning_trades) > 0 else 0.0
        avg_loss = float(losing_trades.mean()) if len(losing_trades) > 0 else 0.0
        avg_trade = float(pnl.mean()) if len(pnl) > 0 else 0.0

        gross_profit = float(winning_trades.sum()) if len(winning_trades) > 0 else 0.0
        gross_loss = abs(float(losing_trades.sum())) if len(losing_trades) > 0 else 0.0

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        best_trade = float(pnl.max()) if len(pnl) > 0 else 0.0
        worst_trade = float(pnl.min()) if len(pnl) > 0 else 0.0

        return {
            'total_trades': total_trades,
            'winning_trades': num_winning,
            'losing_trades': num_losing,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'avg_trade': avg_trade,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
        }

    def _calculate_alpha_beta(
        self,
        returns: pd.Series,
        benchmark_returns: pd.Series
    ) -> Tuple[float, float]:
        """Calculate alpha and beta vs benchmark."""
        # Align returns
        aligned = pd.concat([returns, benchmark_returns], axis=1, join='inner')
        if len(aligned) < 2:
            return 0.0, 0.0

        strategy_returns = aligned.iloc[:, 0]
        bench_returns = aligned.iloc[:, 1]

        # Calculate beta using covariance
        covariance = strategy_returns.cov(bench_returns)
        benchmark_variance = bench_returns.var()

        if benchmark_variance == 0:
            beta = 0.0
        else:
            beta = float(covariance / benchmark_variance)

        # Calculate alpha
        daily_rf = self.risk_free_rate / 252
        strategy_excess = (strategy_returns.mean() - daily_rf) * 252
        benchmark_excess = (bench_returns.mean() - daily_rf) * 252

        alpha = float(strategy_excess - beta * benchmark_excess)

        return alpha, beta

    def _calculate_correlation(
        self,
        returns: pd.Series,
        benchmark_returns: pd.Series
    ) -> float:
        """Calculate correlation with benchmark."""
        aligned = pd.concat([returns, benchmark_returns], axis=1, join='inner')
        if len(aligned) < 2:
            return 0.0

        return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))

    def _calculate_tracking_error(
        self,
        returns: pd.Series,
        benchmark_returns: pd.Series
    ) -> float:
        """Calculate tracking error vs benchmark."""
        aligned = pd.concat([returns, benchmark_returns], axis=1, join='inner')
        if len(aligned) < 2:
            return 0.0

        difference = aligned.iloc[:, 0] - aligned.iloc[:, 1]
        tracking_error = float(difference.std() * np.sqrt(252))

        return tracking_error

    def _calculate_information_ratio(
        self,
        returns: pd.Series,
        benchmark_returns: pd.Series,
        tracking_error: float
    ) -> float:
        """Calculate information ratio."""
        if tracking_error == 0:
            return 0.0

        aligned = pd.concat([returns, benchmark_returns], axis=1, join='inner')
        if len(aligned) < 2:
            return 0.0

        excess_returns = aligned.iloc[:, 0] - aligned.iloc[:, 1]
        annualized_excess = float(excess_returns.mean() * 252)

        return annualized_excess / tracking_error

    def calculate_rolling_metrics(
        self,
        equity_curve: pd.Series,
        window: int = 252,
    ) -> pd.DataFrame:
        """
        Calculate rolling performance metrics.

        Args:
            equity_curve: Portfolio value time series
            window: Rolling window size (default: 252 trading days = 1 year)

        Returns:
            DataFrame with rolling metrics
        """
        returns = equity_curve.pct_change().dropna()

        rolling_metrics = pd.DataFrame(index=returns.index)

        # Rolling return
        rolling_metrics['return'] = returns.rolling(window).apply(
            lambda x: (1 + x).prod() - 1, raw=True
        )

        # Rolling volatility
        rolling_metrics['volatility'] = returns.rolling(window).std() * np.sqrt(252)

        # Rolling Sharpe
        daily_rf = self.risk_free_rate / 252
        excess_returns = returns - daily_rf
        rolling_metrics['sharpe'] = (
            excess_returns.rolling(window).mean() * 252 /
            (returns.rolling(window).std() * np.sqrt(252))
        )

        # Rolling max drawdown
        rolling_metrics['max_drawdown'] = equity_curve.rolling(window).apply(
            lambda x: ((x - x.expanding().max()) / x.expanding().max()).min(),
            raw=False
        )

        return rolling_metrics

    def calculate_monthly_returns(self, equity_curve: pd.Series) -> pd.DataFrame:
        """
        Calculate monthly returns.

        Args:
            equity_curve: Portfolio value time series

        Returns:
            DataFrame with monthly returns
        """
        monthly = equity_curve.resample('M').last()
        monthly_returns = monthly.pct_change().dropna()

        # Create pivot table for heatmap
        monthly_df = pd.DataFrame({
            'return': monthly_returns,
            'year': monthly_returns.index.year,
            'month': monthly_returns.index.month,
        })

        pivot = monthly_df.pivot(index='year', columns='month', values='return')

        # Add year totals
        pivot['Year'] = pivot.apply(lambda x: (1 + x).prod() - 1, axis=1)

        return pivot
