"""
Walk-forward analysis for backtesting.

This module implements walk-forward optimization to test strategy robustness
and detect overfitting by splitting data into in-sample and out-of-sample periods.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from decimal import Decimal

import pandas as pd
import numpy as np
from tqdm import tqdm

from .config import BacktestConfig, WalkForwardConfig
from .performance import PerformanceMetrics
from .exceptions import OptimizationError


logger = logging.getLogger(__name__)


@dataclass
class WalkForwardWindow:
    """
    Represents a single walk-forward window.

    Attributes:
        window_id: Window identifier
        in_sample_start: In-sample start date
        in_sample_end: In-sample end date
        out_sample_start: Out-of-sample start date
        out_sample_end: Out-of-sample end date
        best_params: Best parameters from in-sample optimization
        in_sample_metrics: In-sample performance metrics
        out_sample_metrics: Out-of-sample performance metrics
    """
    window_id: int
    in_sample_start: datetime
    in_sample_end: datetime
    out_sample_start: datetime
    out_sample_end: datetime
    best_params: Optional[Dict[str, Any]] = None
    in_sample_metrics: Optional[PerformanceMetrics] = None
    out_sample_metrics: Optional[PerformanceMetrics] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'window_id': self.window_id,
            'in_sample_start': self.in_sample_start.strftime('%Y-%m-%d'),
            'in_sample_end': self.in_sample_end.strftime('%Y-%m-%d'),
            'out_sample_start': self.out_sample_start.strftime('%Y-%m-%d'),
            'out_sample_end': self.out_sample_end.strftime('%Y-%m-%d'),
            'best_params': self.best_params,
            'in_sample_sharpe': self.in_sample_metrics.sharpe_ratio if self.in_sample_metrics else None,
            'out_sample_sharpe': self.out_sample_metrics.sharpe_ratio if self.out_sample_metrics else None,
        }


@dataclass
class WalkForwardResults:
    """
    Results from walk-forward analysis.

    Attributes:
        windows: List of walk-forward windows
        combined_metrics: Combined out-of-sample metrics
        efficiency_ratio: Walk-forward efficiency ratio
        overfitting_score: Overfitting score (0-1, lower is better)
    """
    windows: List[WalkForwardWindow]
    combined_metrics: PerformanceMetrics
    efficiency_ratio: float
    overfitting_score: float

    def summary(self) -> pd.DataFrame:
        """Get summary DataFrame of all windows."""
        return pd.DataFrame([w.to_dict() for w in self.windows])

    def __str__(self) -> str:
        """String representation."""
        lines = [
            "Walk-Forward Analysis Results",
            "=" * 60,
            f"Number of Windows: {len(self.windows)}",
            f"WF Efficiency Ratio: {self.efficiency_ratio:.2f}",
            f"Overfitting Score: {self.overfitting_score:.2f}",
            "",
            "Combined Out-of-Sample Metrics:",
            "-" * 60,
            f"Sharpe Ratio: {self.combined_metrics.sharpe_ratio:.2f}",
            f"Total Return: {self.combined_metrics.total_return:.2%}",
            f"Max Drawdown: {self.combined_metrics.max_drawdown:.2%}",
        ]
        return "\n".join(lines)


class WalkForwardAnalyzer:
    """
    Performs walk-forward analysis.

    This class splits the backtest period into multiple windows, optimizes
    parameters on in-sample data, and tests on out-of-sample data.
    """

    def __init__(self, wf_config: WalkForwardConfig):
        """
        Initialize walk-forward analyzer.

        Args:
            wf_config: Walk-forward configuration
        """
        self.config = wf_config
        logger.info("WalkForwardAnalyzer initialized")

    def analyze(
        self,
        backtest_func: Callable,
        param_grid: Dict[str, List[Any]],
        tickers: List[str],
        start_date: str,
        end_date: str,
        initial_capital: Decimal = Decimal("100000"),
    ) -> WalkForwardResults:
        """
        Perform walk-forward analysis.

        Args:
            backtest_func: Function that runs backtest with given parameters
                          Should have signature: (params, tickers, start, end, capital) -> (metrics, equity, trades)
            param_grid: Dictionary of parameter names to lists of values
            tickers: List of tickers to test
            start_date: Overall start date
            end_date: Overall end date
            initial_capital: Initial capital

        Returns:
            WalkForwardResults

        Raises:
            OptimizationError: If optimization fails
        """
        logger.info("Starting walk-forward analysis")

        # Generate windows
        windows = self._generate_windows(start_date, end_date)

        logger.info(f"Generated {len(windows)} walk-forward windows")

        # Process each window
        for window in tqdm(windows, desc="Walk-forward windows"):
            try:
                # Optimize on in-sample data
                best_params, is_metrics = self._optimize_window(
                    backtest_func,
                    param_grid,
                    tickers,
                    window.in_sample_start,
                    window.in_sample_end,
                    initial_capital,
                )

                window.best_params = best_params
                window.in_sample_metrics = is_metrics

                # Test on out-of-sample data
                oos_metrics, _, _ = backtest_func(
                    best_params,
                    tickers,
                    window.out_sample_start.strftime('%Y-%m-%d'),
                    window.out_sample_end.strftime('%Y-%m-%d'),
                    initial_capital,
                )

                window.out_sample_metrics = oos_metrics

                logger.info(
                    f"Window {window.window_id}: "
                    f"IS Sharpe={is_metrics.sharpe_ratio:.2f}, "
                    f"OOS Sharpe={oos_metrics.sharpe_ratio:.2f}"
                )

            except Exception as e:
                logger.error(f"Failed to process window {window.window_id}: {e}")
                raise OptimizationError(f"Walk-forward analysis failed: {e}")

        # Calculate combined metrics
        combined_metrics = self._combine_oos_metrics(windows)

        # Calculate efficiency ratio
        efficiency_ratio = self._calculate_efficiency_ratio(windows)

        # Calculate overfitting score
        overfitting_score = self._calculate_overfitting_score(windows)

        results = WalkForwardResults(
            windows=windows,
            combined_metrics=combined_metrics,
            efficiency_ratio=efficiency_ratio,
            overfitting_score=overfitting_score,
        )

        logger.info("Walk-forward analysis complete")
        return results

    def _generate_windows(
        self,
        start_date: str,
        end_date: str,
    ) -> List[WalkForwardWindow]:
        """Generate walk-forward windows."""
        windows = []
        window_id = 0

        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        current_start = start

        while True:
            # Calculate in-sample period
            is_start = current_start
            is_end = is_start + timedelta(days=self.config.in_sample_months * 30)

            # Calculate out-of-sample period
            oos_start = is_end + timedelta(days=1)
            oos_end = oos_start + timedelta(days=self.config.out_sample_months * 30)

            # Check if we're past the end date
            if oos_end > end:
                break

            # Create window
            window = WalkForwardWindow(
                window_id=window_id,
                in_sample_start=is_start,
                in_sample_end=is_end,
                out_sample_start=oos_start,
                out_sample_end=oos_end,
            )

            windows.append(window)
            window_id += 1

            # Move to next window
            if self.config.anchored:
                # Anchored: keep same start, extend end
                current_start = start
            else:
                # Rolling: move forward by step_months
                current_start = current_start + timedelta(days=self.config.step_months * 30)

        return windows

    def _optimize_window(
        self,
        backtest_func: Callable,
        param_grid: Dict[str, List[Any]],
        tickers: List[str],
        start_date: datetime,
        end_date: datetime,
        initial_capital: Decimal,
    ) -> Tuple[Dict[str, Any], PerformanceMetrics]:
        """
        Optimize parameters for a single window.

        Args:
            backtest_func: Backtest function
            param_grid: Parameter grid
            tickers: Tickers to test
            start_date: Start date
            end_date: End date
            initial_capital: Initial capital

        Returns:
            (best_params, best_metrics) tuple
        """
        # Generate parameter combinations
        param_combinations = self._generate_param_combinations(param_grid)

        best_params = None
        best_score = float('-inf')
        best_metrics = None

        # Test each parameter combination
        for params in param_combinations:
            try:
                metrics, _, _ = backtest_func(
                    params,
                    tickers,
                    start_date.strftime('%Y-%m-%d'),
                    end_date.strftime('%Y-%m-%d'),
                    initial_capital,
                )

                # Get optimization score
                score = self._get_optimization_score(metrics)

                if score > best_score:
                    best_score = score
                    best_params = params
                    best_metrics = metrics

            except Exception as e:
                logger.warning(f"Failed to test params {params}: {e}")
                continue

        if best_params is None:
            raise OptimizationError("No valid parameter combinations found")

        return best_params, best_metrics

    def _generate_param_combinations(
        self,
        param_grid: Dict[str, List[Any]]
    ) -> List[Dict[str, Any]]:
        """Generate all combinations of parameters."""
        if not param_grid:
            return [{}]

        import itertools

        keys = list(param_grid.keys())
        values = list(param_grid.values())

        combinations = []
        for combo in itertools.product(*values):
            combinations.append(dict(zip(keys, combo)))

        return combinations

    def _get_optimization_score(self, metrics: PerformanceMetrics) -> float:
        """Get optimization score based on configured metric."""
        metric_map = {
            'sharpe': metrics.sharpe_ratio,
            'sortino': metrics.sortino_ratio,
            'calmar': metrics.calmar_ratio,
            'return': metrics.annualized_return,
            'max_drawdown': -metrics.max_drawdown,  # Negative because we want to minimize
        }

        return metric_map.get(self.config.optimization_metric, metrics.sharpe_ratio)

    def _combine_oos_metrics(self, windows: List[WalkForwardWindow]) -> PerformanceMetrics:
        """Combine out-of-sample metrics from all windows."""
        # This is a simplified combination - in practice, you'd want to
        # concatenate the actual equity curves and recalculate

        oos_metrics = [w.out_sample_metrics for w in windows if w.out_sample_metrics]

        if not oos_metrics:
            raise OptimizationError("No out-of-sample metrics available")

        # Average the metrics (simplified approach)
        combined = PerformanceMetrics(
            total_return=np.mean([m.total_return for m in oos_metrics]),
            annualized_return=np.mean([m.annualized_return for m in oos_metrics]),
            cumulative_return=np.mean([m.cumulative_return for m in oos_metrics]),
            sharpe_ratio=np.mean([m.sharpe_ratio for m in oos_metrics]),
            sortino_ratio=np.mean([m.sortino_ratio for m in oos_metrics]),
            calmar_ratio=np.mean([m.calmar_ratio for m in oos_metrics]),
            omega_ratio=np.mean([m.omega_ratio for m in oos_metrics]),
            volatility=np.mean([m.volatility for m in oos_metrics]),
            downside_deviation=np.mean([m.downside_deviation for m in oos_metrics]),
            max_drawdown=np.mean([m.max_drawdown for m in oos_metrics]),
            avg_drawdown=np.mean([m.avg_drawdown for m in oos_metrics]),
            max_drawdown_duration=int(np.mean([m.max_drawdown_duration for m in oos_metrics])),
            total_trades=sum([m.total_trades for m in oos_metrics]),
            winning_trades=sum([m.winning_trades for m in oos_metrics]),
            losing_trades=sum([m.losing_trades for m in oos_metrics]),
            win_rate=np.mean([m.win_rate for m in oos_metrics]),
            profit_factor=np.mean([m.profit_factor for m in oos_metrics]),
            avg_win=np.mean([m.avg_win for m in oos_metrics]),
            avg_loss=np.mean([m.avg_loss for m in oos_metrics]),
            avg_trade=np.mean([m.avg_trade for m in oos_metrics]),
            best_trade=max([m.best_trade for m in oos_metrics]),
            worst_trade=min([m.worst_trade for m in oos_metrics]),
        )

        return combined

    def _calculate_efficiency_ratio(self, windows: List[WalkForwardWindow]) -> float:
        """
        Calculate walk-forward efficiency ratio.

        This is the ratio of out-of-sample performance to in-sample performance.
        A ratio close to 1.0 indicates the strategy performs similarly in-sample
        and out-of-sample (good). A ratio much lower than 1.0 indicates overfitting.
        """
        is_scores = []
        oos_scores = []

        for window in windows:
            if window.in_sample_metrics and window.out_sample_metrics:
                is_score = self._get_optimization_score(window.in_sample_metrics)
                oos_score = self._get_optimization_score(window.out_sample_metrics)

                is_scores.append(is_score)
                oos_scores.append(oos_score)

        if not is_scores or not oos_scores:
            return 0.0

        avg_is_score = np.mean(is_scores)
        avg_oos_score = np.mean(oos_scores)

        if avg_is_score == 0:
            return 0.0

        return avg_oos_score / avg_is_score

    def _calculate_overfitting_score(self, windows: List[WalkForwardWindow]) -> float:
        """
        Calculate overfitting score.

        This measures how much the performance degrades from in-sample to
        out-of-sample. Lower scores indicate less overfitting.

        Returns value between 0 and 1 (0 = no overfitting, 1 = severe overfitting)
        """
        degradations = []

        for window in windows:
            if window.in_sample_metrics and window.out_sample_metrics:
                is_score = self._get_optimization_score(window.in_sample_metrics)
                oos_score = self._get_optimization_score(window.out_sample_metrics)

                if is_score > 0:
                    degradation = (is_score - oos_score) / is_score
                    degradations.append(max(0, degradation))  # Clip at 0

        if not degradations:
            return 0.0

        # Average degradation
        return min(1.0, np.mean(degradations))


def create_walk_forward_config(
    in_sample_months: int = 12,
    out_sample_months: int = 3,
    optimization_metric: str = "sharpe",
    anchored: bool = False,
) -> WalkForwardConfig:
    """
    Create a walk-forward configuration with sensible defaults.

    Args:
        in_sample_months: Months for training
        out_sample_months: Months for testing
        optimization_metric: Metric to optimize
        anchored: Whether to use anchored windows

    Returns:
        WalkForwardConfig
    """
    return WalkForwardConfig(
        in_sample_months=in_sample_months,
        out_sample_months=out_sample_months,
        optimization_metric=optimization_metric,
        anchored=anchored,
    )
