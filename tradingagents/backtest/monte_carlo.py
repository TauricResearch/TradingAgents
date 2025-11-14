"""
Monte Carlo simulation for backtesting.

This module implements Monte Carlo methods to assess the distribution of
potential outcomes and confidence intervals for backtest results.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal

import pandas as pd
import numpy as np
from tqdm import tqdm

from .config import MonteCarloConfig
from .exceptions import MonteCarloError


logger = logging.getLogger(__name__)


@dataclass
class MonteCarloResults:
    """
    Results from Monte Carlo simulation.

    Attributes:
        n_simulations: Number of simulations run
        mean_final_value: Mean final portfolio value
        median_final_value: Median final portfolio value
        std_final_value: Standard deviation of final values
        confidence_intervals: Confidence intervals for final value
        worst_case: Worst case final value
        best_case: Best case final value
        probability_of_profit: Probability of positive return
        simulated_paths: Sample of simulated equity curves
        percentiles: Percentiles of final values
    """
    n_simulations: int
    mean_final_value: float
    median_final_value: float
    std_final_value: float
    confidence_intervals: Dict[float, Tuple[float, float]]
    worst_case: float
    best_case: float
    probability_of_profit: float
    simulated_paths: Optional[pd.DataFrame] = None
    percentiles: Dict[int, float] = field(default_factory=dict)

    def __str__(self) -> str:
        """String representation."""
        lines = [
            "Monte Carlo Simulation Results",
            "=" * 60,
            f"Simulations: {self.n_simulations:,}",
            f"Mean Final Value: ${self.mean_final_value:,.2f}",
            f"Median Final Value: ${self.median_final_value:,.2f}",
            f"Std Dev: ${self.std_final_value:,.2f}",
            f"Probability of Profit: {self.probability_of_profit:.2%}",
            "",
            "Confidence Intervals:",
            "-" * 60,
        ]

        for level, (lower, upper) in sorted(self.confidence_intervals.items()):
            lines.append(f"{level:.0%}: ${lower:,.2f} - ${upper:,.2f}")

        lines.extend([
            "",
            "Extreme Cases:",
            "-" * 60,
            f"Best Case: ${self.best_case:,.2f}",
            f"Worst Case: ${self.worst_case:,.2f}",
        ])

        return "\n".join(lines)


class MonteCarloSimulator:
    """
    Performs Monte Carlo simulations on backtest results.

    This class uses various resampling methods to generate distributions
    of potential outcomes and assess risk.
    """

    def __init__(self, config: MonteCarloConfig):
        """
        Initialize Monte Carlo simulator.

        Args:
            config: Monte Carlo configuration
        """
        self.config = config

        # Set random seed for reproducibility
        if config.random_seed is not None:
            np.random.seed(config.random_seed)

        logger.info(f"MonteCarloSimulator initialized with {config.n_simulations} simulations")

    def simulate(
        self,
        equity_curve: pd.Series,
        trades: Optional[pd.DataFrame] = None,
        initial_value: Optional[float] = None,
    ) -> MonteCarloResults:
        """
        Run Monte Carlo simulation.

        Args:
            equity_curve: Historical equity curve
            trades: DataFrame with trade information (required for trade resampling)
            initial_value: Initial portfolio value (default: first value in equity_curve)

        Returns:
            MonteCarloResults

        Raises:
            MonteCarloError: If simulation fails
        """
        logger.info(f"Running Monte Carlo simulation: {self.config.method}")

        if initial_value is None:
            initial_value = float(equity_curve.iloc[0])

        try:
            if self.config.method == 'resample_returns':
                simulated_values = self._resample_returns(equity_curve, initial_value)

            elif self.config.method == 'resample_trades':
                if trades is None or trades.empty:
                    raise MonteCarloError("Trades data required for trade resampling")
                simulated_values = self._resample_trades(trades, initial_value)

            elif self.config.method == 'parametric':
                simulated_values = self._parametric_simulation(equity_curve, initial_value)

            else:
                raise MonteCarloError(f"Unknown simulation method: {self.config.method}")

            # Calculate statistics
            results = self._calculate_statistics(simulated_values, initial_value)

            logger.info("Monte Carlo simulation complete")
            return results

        except Exception as e:
            raise MonteCarloError(f"Monte Carlo simulation failed: {e}")

    def _resample_returns(
        self,
        equity_curve: pd.Series,
        initial_value: float,
    ) -> np.ndarray:
        """
        Simulate by resampling historical returns.

        Args:
            equity_curve: Historical equity curve
            initial_value: Initial portfolio value

        Returns:
            Array of final values from simulations
        """
        # Calculate returns
        returns = equity_curve.pct_change().dropna().values

        if len(returns) == 0:
            raise MonteCarloError("No returns available for resampling")

        n_periods = len(returns)
        final_values = np.zeros(self.config.n_simulations)

        for i in tqdm(range(self.config.n_simulations), desc="Monte Carlo simulation"):
            # Resample returns with replacement
            if self.config.preserve_order:
                # Block resampling to preserve some order
                block_size = min(20, n_periods // 10)
                resampled_returns = self._block_resample(returns, n_periods, block_size)
            else:
                # Random resampling
                resampled_returns = np.random.choice(returns, size=n_periods, replace=True)

            # Calculate final value
            final_value = initial_value * np.prod(1 + resampled_returns)
            final_values[i] = final_value

        return final_values

    def _resample_trades(
        self,
        trades: pd.DataFrame,
        initial_value: float,
    ) -> np.ndarray:
        """
        Simulate by resampling trades.

        Args:
            trades: DataFrame with trade information
            initial_value: Initial portfolio value

        Returns:
            Array of final values from simulations
        """
        if 'pnl' not in trades.columns:
            raise MonteCarloError("Trades must have 'pnl' column")

        trade_returns = (trades['pnl'] / initial_value).values
        n_trades = len(trade_returns)

        if n_trades == 0:
            raise MonteCarloError("No trades available for resampling")

        final_values = np.zeros(self.config.n_simulations)

        for i in tqdm(range(self.config.n_simulations), desc="Monte Carlo simulation"):
            # Resample trades
            if self.config.preserve_order:
                # Sequential resampling with some randomness
                resampled_returns = self._sequential_resample(trade_returns)
            else:
                # Random resampling
                resampled_returns = np.random.choice(trade_returns, size=n_trades, replace=True)

            # Calculate final value
            cumulative_return = np.sum(resampled_returns)
            final_value = initial_value * (1 + cumulative_return)
            final_values[i] = final_value

        return final_values

    def _parametric_simulation(
        self,
        equity_curve: pd.Series,
        initial_value: float,
    ) -> np.ndarray:
        """
        Simulate using parametric distribution.

        Assumes returns follow a normal distribution with estimated parameters.

        Args:
            equity_curve: Historical equity curve
            initial_value: Initial portfolio value

        Returns:
            Array of final values from simulations
        """
        # Calculate returns
        returns = equity_curve.pct_change().dropna().values

        if len(returns) == 0:
            raise MonteCarloError("No returns available for parametric simulation")

        # Estimate parameters
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        n_periods = len(returns)

        final_values = np.zeros(self.config.n_simulations)

        for i in tqdm(range(self.config.n_simulations), desc="Monte Carlo simulation"):
            # Generate random returns from normal distribution
            simulated_returns = np.random.normal(mean_return, std_return, n_periods)

            # Calculate final value
            final_value = initial_value * np.prod(1 + simulated_returns)
            final_values[i] = final_value

        return final_values

    def _block_resample(
        self,
        data: np.ndarray,
        target_length: int,
        block_size: int,
    ) -> np.ndarray:
        """
        Resample data in blocks to preserve some temporal structure.

        Args:
            data: Data to resample
            target_length: Target length of resampled data
            block_size: Size of blocks to resample

        Returns:
            Resampled data
        """
        n_data = len(data)
        n_blocks = (target_length + block_size - 1) // block_size

        resampled = []
        for _ in range(n_blocks):
            # Random starting point
            start_idx = np.random.randint(0, max(1, n_data - block_size + 1))
            end_idx = min(start_idx + block_size, n_data)
            block = data[start_idx:end_idx]
            resampled.extend(block)

        return np.array(resampled[:target_length])

    def _sequential_resample(self, data: np.ndarray) -> np.ndarray:
        """
        Resample while maintaining some sequential structure.

        Args:
            data: Data to resample

        Returns:
            Resampled data
        """
        n_data = len(data)
        resampled = np.zeros(n_data)

        # Start with a random position
        current_idx = np.random.randint(0, n_data)

        for i in range(n_data):
            resampled[i] = data[current_idx]

            # Move to next position with some randomness
            if np.random.random() < 0.8:  # 80% chance to move sequentially
                current_idx = (current_idx + 1) % n_data
            else:  # 20% chance to jump randomly
                current_idx = np.random.randint(0, n_data)

        return resampled

    def _calculate_statistics(
        self,
        simulated_values: np.ndarray,
        initial_value: float,
    ) -> MonteCarloResults:
        """
        Calculate statistics from simulated values.

        Args:
            simulated_values: Array of final values
            initial_value: Initial portfolio value

        Returns:
            MonteCarloResults
        """
        # Basic statistics
        mean_final = np.mean(simulated_values)
        median_final = np.median(simulated_values)
        std_final = np.std(simulated_values)
        min_final = np.min(simulated_values)
        max_final = np.max(simulated_values)

        # Probability of profit
        prob_profit = np.sum(simulated_values > initial_value) / len(simulated_values)

        # Confidence intervals
        confidence_intervals = {}
        for level in self.config.confidence_levels:
            alpha = 1 - level
            lower_percentile = (alpha / 2) * 100
            upper_percentile = (1 - alpha / 2) * 100

            lower_bound = np.percentile(simulated_values, lower_percentile)
            upper_bound = np.percentile(simulated_values, upper_percentile)

            confidence_intervals[level] = (float(lower_bound), float(upper_bound))

        # Percentiles
        percentiles = {
            p: float(np.percentile(simulated_values, p))
            for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]
        }

        # Store sample of simulated paths (for visualization)
        # Note: This would require storing the full paths, not just final values
        # For now, we'll skip this to save memory

        results = MonteCarloResults(
            n_simulations=self.config.n_simulations,
            mean_final_value=float(mean_final),
            median_final_value=float(median_final),
            std_final_value=float(std_final),
            confidence_intervals=confidence_intervals,
            worst_case=float(min_final),
            best_case=float(max_final),
            probability_of_profit=float(prob_profit),
            percentiles=percentiles,
        )

        return results

    def simulate_paths(
        self,
        equity_curve: pd.Series,
        n_paths: int = 100,
    ) -> pd.DataFrame:
        """
        Simulate multiple equity curve paths.

        Args:
            equity_curve: Historical equity curve
            n_paths: Number of paths to simulate

        Returns:
            DataFrame with simulated paths
        """
        returns = equity_curve.pct_change().dropna()
        n_periods = len(returns)
        initial_value = equity_curve.iloc[0]

        paths = np.zeros((n_periods, n_paths))

        for i in range(n_paths):
            # Resample returns
            resampled_returns = np.random.choice(returns.values, size=n_periods, replace=True)

            # Calculate path
            path_values = initial_value * np.cumprod(1 + resampled_returns)
            paths[:, i] = path_values

        # Create DataFrame
        paths_df = pd.DataFrame(
            paths,
            index=returns.index,
            columns=[f'path_{i}' for i in range(n_paths)]
        )

        return paths_df

    def value_at_risk(
        self,
        simulated_values: np.ndarray,
        confidence_level: float = 0.95,
    ) -> float:
        """
        Calculate Value at Risk (VaR).

        Args:
            simulated_values: Array of simulated final values
            confidence_level: Confidence level (e.g., 0.95 for 95%)

        Returns:
            Value at Risk
        """
        alpha = 1 - confidence_level
        var = np.percentile(simulated_values, alpha * 100)
        return float(var)

    def conditional_value_at_risk(
        self,
        simulated_values: np.ndarray,
        confidence_level: float = 0.95,
    ) -> float:
        """
        Calculate Conditional Value at Risk (CVaR / Expected Shortfall).

        Args:
            simulated_values: Array of simulated final values
            confidence_level: Confidence level (e.g., 0.95 for 95%)

        Returns:
            Conditional Value at Risk
        """
        var = self.value_at_risk(simulated_values, confidence_level)
        cvar = np.mean(simulated_values[simulated_values <= var])
        return float(cvar)


def create_monte_carlo_config(
    n_simulations: int = 10000,
    method: str = "resample_returns",
    confidence_levels: Optional[List[float]] = None,
    random_seed: Optional[int] = None,
) -> MonteCarloConfig:
    """
    Create a Monte Carlo configuration with sensible defaults.

    Args:
        n_simulations: Number of simulations
        method: Simulation method
        confidence_levels: Confidence levels for intervals
        random_seed: Random seed for reproducibility

    Returns:
        MonteCarloConfig
    """
    if confidence_levels is None:
        confidence_levels = [0.90, 0.95, 0.99]

    return MonteCarloConfig(
        n_simulations=n_simulations,
        method=method,
        confidence_levels=confidence_levels,
        random_seed=random_seed,
    )
