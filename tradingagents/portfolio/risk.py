"""
Risk management for the portfolio system.

This module provides risk controls including position size limits,
sector concentration limits, drawdown monitoring, VaR calculation,
and risk-adjusted returns.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import logging
import math

from .exceptions import RiskLimitExceededError, CalculationError, ValidationError

logger = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """
    Configuration for portfolio risk limits.

    Attributes:
        max_position_size: Maximum size of any single position (as fraction of portfolio)
        max_sector_concentration: Maximum exposure to any single sector (as fraction)
        max_drawdown: Maximum allowed drawdown (as fraction, e.g., 0.20 for 20%)
        max_portfolio_leverage: Maximum portfolio leverage ratio
        max_correlation: Maximum correlation between positions
        min_cash_reserve: Minimum cash reserve (as fraction of portfolio)
    """

    max_position_size: Decimal = Decimal('0.20')  # 20% max
    max_sector_concentration: Decimal = Decimal('0.30')  # 30% max
    max_drawdown: Decimal = Decimal('0.25')  # 25% max
    max_portfolio_leverage: Decimal = Decimal('2.0')  # 2x max
    max_correlation: Decimal = Decimal('0.80')  # 0.80 max
    min_cash_reserve: Decimal = Decimal('0.05')  # 5% min

    def __post_init__(self):
        """Validate risk limits."""
        limits = {
            'max_position_size': self.max_position_size,
            'max_sector_concentration': self.max_sector_concentration,
            'max_drawdown': self.max_drawdown,
            'min_cash_reserve': self.min_cash_reserve,
        }

        for name, value in limits.items():
            if not isinstance(value, Decimal):
                setattr(self, name, Decimal(str(value)))
                value = getattr(self, name)

            if value < 0 or value > 1:
                raise ValidationError(
                    f"{name} must be between 0 and 1, got {value}"
                )

        if not isinstance(self.max_portfolio_leverage, Decimal):
            self.max_portfolio_leverage = Decimal(str(self.max_portfolio_leverage))

        if self.max_portfolio_leverage < 1:
            raise ValidationError("max_portfolio_leverage must be >= 1")

        if not isinstance(self.max_correlation, Decimal):
            self.max_correlation = Decimal(str(self.max_correlation))

        if self.max_correlation < 0 or self.max_correlation > 1:
            raise ValidationError("max_correlation must be between 0 and 1")


class RiskManager:
    """
    Manages risk controls and calculations for a portfolio.

    This class provides methods to check risk limits, calculate risk metrics,
    and ensure trades comply with risk management rules.
    """

    def __init__(self, limits: Optional[RiskLimits] = None):
        """
        Initialize the risk manager.

        Args:
            limits: Risk limits configuration (uses defaults if not provided)
        """
        self.limits = limits or RiskLimits()
        logger.info(
            f"Initialized RiskManager with limits: "
            f"max_position={self.limits.max_position_size}, "
            f"max_sector={self.limits.max_sector_concentration}, "
            f"max_drawdown={self.limits.max_drawdown}"
        )

    def check_position_size_limit(
        self,
        position_value: Decimal,
        portfolio_value: Decimal,
        ticker: str
    ) -> None:
        """
        Check if a position size exceeds the limit.

        Args:
            position_value: Value of the position
            portfolio_value: Total portfolio value
            ticker: Ticker symbol (for error messages)

        Raises:
            RiskLimitExceededError: If position size exceeds limit
            ValidationError: If inputs are invalid
        """
        if portfolio_value <= 0:
            raise ValidationError("Portfolio value must be positive")

        position_pct = abs(position_value) / portfolio_value

        if position_pct > self.limits.max_position_size:
            raise RiskLimitExceededError(
                f"Position size for {ticker} ({position_pct:.2%}) exceeds "
                f"limit ({self.limits.max_position_size:.2%})"
            )

        logger.debug(
            f"Position size check passed for {ticker}: "
            f"{position_pct:.2%} <= {self.limits.max_position_size:.2%}"
        )

    def check_sector_concentration(
        self,
        sector_exposure: Dict[str, Decimal],
        portfolio_value: Decimal
    ) -> None:
        """
        Check if sector concentration exceeds limits.

        Args:
            sector_exposure: Dictionary mapping sector to total exposure
            portfolio_value: Total portfolio value

        Raises:
            RiskLimitExceededError: If sector concentration exceeds limit
            ValidationError: If inputs are invalid
        """
        if portfolio_value <= 0:
            raise ValidationError("Portfolio value must be positive")

        for sector, exposure in sector_exposure.items():
            sector_pct = abs(exposure) / portfolio_value

            if sector_pct > self.limits.max_sector_concentration:
                raise RiskLimitExceededError(
                    f"Sector concentration for {sector} ({sector_pct:.2%}) "
                    f"exceeds limit ({self.limits.max_sector_concentration:.2%})"
                )

        logger.debug("Sector concentration check passed")

    def check_drawdown_limit(
        self,
        current_value: Decimal,
        peak_value: Decimal
    ) -> None:
        """
        Check if drawdown exceeds the limit.

        Args:
            current_value: Current portfolio value
            peak_value: Peak portfolio value

        Raises:
            RiskLimitExceededError: If drawdown exceeds limit
            ValidationError: If inputs are invalid
        """
        if peak_value <= 0:
            raise ValidationError("Peak value must be positive")

        if current_value < 0:
            raise ValidationError("Current value cannot be negative")

        if current_value > peak_value:
            # Not in drawdown, all good
            return

        drawdown = (peak_value - current_value) / peak_value

        if drawdown > self.limits.max_drawdown:
            raise RiskLimitExceededError(
                f"Drawdown ({drawdown:.2%}) exceeds limit "
                f"({self.limits.max_drawdown:.2%})"
            )

        logger.debug(
            f"Drawdown check passed: {drawdown:.2%} <= {self.limits.max_drawdown:.2%}"
        )

    def check_cash_reserve(
        self,
        cash: Decimal,
        portfolio_value: Decimal
    ) -> None:
        """
        Check if cash reserve meets minimum requirement.

        Args:
            cash: Current cash balance
            portfolio_value: Total portfolio value

        Raises:
            RiskLimitExceededError: If cash reserve is below minimum
            ValidationError: If inputs are invalid
        """
        if portfolio_value <= 0:
            raise ValidationError("Portfolio value must be positive")

        cash_pct = cash / portfolio_value

        if cash_pct < self.limits.min_cash_reserve:
            raise RiskLimitExceededError(
                f"Cash reserve ({cash_pct:.2%}) below minimum "
                f"({self.limits.min_cash_reserve:.2%})"
            )

        logger.debug(
            f"Cash reserve check passed: {cash_pct:.2%} >= "
            f"{self.limits.min_cash_reserve:.2%}"
        )

    def calculate_position_size(
        self,
        portfolio_value: Decimal,
        risk_per_trade: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal
    ) -> Decimal:
        """
        Calculate optimal position size based on risk per trade.

        Uses the formula: Position Size = (Portfolio Value * Risk %) / Risk Per Share
        where Risk Per Share = |Entry Price - Stop Loss Price|

        Args:
            portfolio_value: Total portfolio value
            risk_per_trade: Maximum risk per trade (as fraction, e.g., 0.02 for 2%)
            entry_price: Entry price for the position
            stop_loss_price: Stop-loss price

        Returns:
            Recommended position size (number of shares)

        Raises:
            ValidationError: If inputs are invalid
            CalculationError: If calculation fails
        """
        if portfolio_value <= 0:
            raise ValidationError("Portfolio value must be positive")

        if risk_per_trade <= 0 or risk_per_trade > 1:
            raise ValidationError("risk_per_trade must be between 0 and 1")

        if entry_price <= 0:
            raise ValidationError("Entry price must be positive")

        if stop_loss_price <= 0:
            raise ValidationError("Stop-loss price must be positive")

        if entry_price == stop_loss_price:
            raise ValidationError("Entry price and stop-loss price cannot be equal")

        # Calculate risk per share
        risk_per_share = abs(entry_price - stop_loss_price)

        # Calculate maximum dollar risk
        max_risk_amount = portfolio_value * risk_per_trade

        # Calculate position size
        position_size = max_risk_amount / risk_per_share

        # Also check against position size limit
        position_value = position_size * entry_price
        if position_value > portfolio_value * self.limits.max_position_size:
            # Adjust to meet position size limit
            position_size = (portfolio_value * self.limits.max_position_size) / entry_price

        logger.info(
            f"Calculated position size: {position_size} shares "
            f"(risk_per_trade={risk_per_trade:.2%}, "
            f"risk_per_share={risk_per_share})"
        )

        return position_size.quantize(Decimal('1'))  # Round to whole shares

    def calculate_var(
        self,
        returns: List[Decimal],
        confidence_level: Decimal = Decimal('0.95'),
        time_horizon: int = 1
    ) -> Decimal:
        """
        Calculate Value at Risk (VaR) using historical simulation.

        VaR estimates the maximum loss over a time horizon at a given
        confidence level.

        Args:
            returns: List of historical returns
            confidence_level: Confidence level (e.g., 0.95 for 95%)
            time_horizon: Time horizon in days

        Returns:
            VaR as a positive number (e.g., 0.05 means 5% potential loss)

        Raises:
            ValidationError: If inputs are invalid
            CalculationError: If calculation fails
        """
        if not returns:
            raise ValidationError("Returns list cannot be empty")

        if confidence_level <= 0 or confidence_level >= 1:
            raise ValidationError("Confidence level must be between 0 and 1")

        if time_horizon < 1:
            raise ValidationError("Time horizon must be at least 1")

        try:
            # Sort returns
            sorted_returns = sorted(returns)

            # Calculate the percentile index
            percentile = 1 - confidence_level
            index = int(len(sorted_returns) * percentile)

            # Get VaR (as a positive number representing potential loss)
            var = abs(sorted_returns[index])

            # Scale by time horizon (assuming IID returns)
            if time_horizon > 1:
                var = var * Decimal(math.sqrt(time_horizon))

            logger.info(
                f"Calculated VaR: {var:.4f} "
                f"(confidence={confidence_level}, horizon={time_horizon})"
            )

            return var

        except (IndexError, ValueError, TypeError) as e:
            raise CalculationError(f"VaR calculation failed: {e}")

    def calculate_sharpe_ratio(
        self,
        returns: List[Decimal],
        risk_free_rate: Decimal = Decimal('0.02')
    ) -> Decimal:
        """
        Calculate the Sharpe ratio.

        Sharpe Ratio = (Mean Return - Risk Free Rate) / Std Dev of Returns

        Args:
            returns: List of periodic returns
            risk_free_rate: Risk-free rate (annualized)

        Returns:
            Sharpe ratio

        Raises:
            ValidationError: If inputs are invalid
            CalculationError: If calculation fails
        """
        if not returns:
            raise ValidationError("Returns list cannot be empty")

        try:
            # Calculate mean return
            mean_return = sum(returns) / len(returns)

            # Calculate standard deviation
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            std_dev = Decimal(math.sqrt(float(variance)))

            if std_dev == 0:
                return Decimal('0')

            # Annualize (assuming daily returns)
            annual_return = mean_return * 252
            annual_std = std_dev * Decimal(math.sqrt(252))

            # Calculate Sharpe ratio
            sharpe = (annual_return - risk_free_rate) / annual_std

            logger.info(f"Calculated Sharpe ratio: {sharpe:.4f}")

            return sharpe

        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise CalculationError(f"Sharpe ratio calculation failed: {e}")

    def calculate_sortino_ratio(
        self,
        returns: List[Decimal],
        risk_free_rate: Decimal = Decimal('0.02')
    ) -> Decimal:
        """
        Calculate the Sortino ratio.

        Similar to Sharpe ratio but only considers downside volatility.

        Args:
            returns: List of periodic returns
            risk_free_rate: Risk-free rate (annualized)

        Returns:
            Sortino ratio

        Raises:
            ValidationError: If inputs are invalid
            CalculationError: If calculation fails
        """
        if not returns:
            raise ValidationError("Returns list cannot be empty")

        try:
            # Calculate mean return
            mean_return = sum(returns) / len(returns)

            # Calculate downside deviation (only negative returns)
            downside_returns = [min(r, Decimal('0')) for r in returns]
            downside_variance = sum(r ** 2 for r in downside_returns) / len(returns)
            downside_dev = Decimal(math.sqrt(float(downside_variance)))

            if downside_dev == 0:
                return Decimal('0') if mean_return <= 0 else Decimal('inf')

            # Annualize
            annual_return = mean_return * 252
            annual_downside_dev = downside_dev * Decimal(math.sqrt(252))

            # Calculate Sortino ratio
            sortino = (annual_return - risk_free_rate) / annual_downside_dev

            logger.info(f"Calculated Sortino ratio: {sortino:.4f}")

            return sortino

        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise CalculationError(f"Sortino ratio calculation failed: {e}")

    def calculate_max_drawdown(self, equity_curve: List[Decimal]) -> Tuple[Decimal, int, int]:
        """
        Calculate maximum drawdown from an equity curve.

        Args:
            equity_curve: List of portfolio values over time

        Returns:
            Tuple of (max_drawdown, peak_index, trough_index)
            where max_drawdown is the maximum drawdown as a fraction

        Raises:
            ValidationError: If inputs are invalid
            CalculationError: If calculation fails
        """
        if not equity_curve:
            raise ValidationError("Equity curve cannot be empty")

        try:
            max_drawdown = Decimal('0')
            peak_value = equity_curve[0]
            peak_index = 0
            trough_index = 0

            for i, value in enumerate(equity_curve):
                if value > peak_value:
                    peak_value = value
                    peak_index = i
                elif peak_value > 0:
                    drawdown = (peak_value - value) / peak_value
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown
                        trough_index = i

            logger.info(
                f"Calculated max drawdown: {max_drawdown:.4f} "
                f"(peak_idx={peak_index}, trough_idx={trough_index})"
            )

            return max_drawdown, peak_index, trough_index

        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise CalculationError(f"Max drawdown calculation failed: {e}")

    def calculate_beta(
        self,
        portfolio_returns: List[Decimal],
        benchmark_returns: List[Decimal]
    ) -> Decimal:
        """
        Calculate portfolio beta relative to a benchmark.

        Beta = Covariance(Portfolio, Benchmark) / Variance(Benchmark)

        Args:
            portfolio_returns: List of portfolio returns
            benchmark_returns: List of benchmark returns

        Returns:
            Beta coefficient

        Raises:
            ValidationError: If inputs are invalid
            CalculationError: If calculation fails
        """
        if not portfolio_returns or not benchmark_returns:
            raise ValidationError("Returns lists cannot be empty")

        if len(portfolio_returns) != len(benchmark_returns):
            raise ValidationError("Returns lists must have equal length")

        try:
            n = len(portfolio_returns)

            # Calculate means
            port_mean = sum(portfolio_returns) / n
            bench_mean = sum(benchmark_returns) / n

            # Calculate covariance
            covariance = sum(
                (portfolio_returns[i] - port_mean) * (benchmark_returns[i] - bench_mean)
                for i in range(n)
            ) / n

            # Calculate benchmark variance
            bench_variance = sum(
                (r - bench_mean) ** 2 for r in benchmark_returns
            ) / n

            if bench_variance == 0:
                raise CalculationError("Benchmark variance is zero")

            beta = covariance / bench_variance

            logger.info(f"Calculated beta: {beta:.4f}")

            return beta

        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise CalculationError(f"Beta calculation failed: {e}")

    def calculate_correlation(
        self,
        returns1: List[Decimal],
        returns2: List[Decimal]
    ) -> Decimal:
        """
        Calculate correlation coefficient between two return series.

        Args:
            returns1: First return series
            returns2: Second return series

        Returns:
            Correlation coefficient (-1 to 1)

        Raises:
            ValidationError: If inputs are invalid
            CalculationError: If calculation fails
        """
        if not returns1 or not returns2:
            raise ValidationError("Returns lists cannot be empty")

        if len(returns1) != len(returns2):
            raise ValidationError("Returns lists must have equal length")

        try:
            n = len(returns1)

            # Calculate means
            mean1 = sum(returns1) / n
            mean2 = sum(returns2) / n

            # Calculate covariance
            covariance = sum(
                (returns1[i] - mean1) * (returns2[i] - mean2)
                for i in range(n)
            ) / n

            # Calculate standard deviations
            std1_sq = sum((r - mean1) ** 2 for r in returns1) / n
            std2_sq = sum((r - mean2) ** 2 for r in returns2) / n

            std1 = Decimal(math.sqrt(float(std1_sq)))
            std2 = Decimal(math.sqrt(float(std2_sq)))

            if std1 == 0 or std2 == 0:
                return Decimal('0')

            correlation = covariance / (std1 * std2)

            logger.info(f"Calculated correlation: {correlation:.4f}")

            return correlation

        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise CalculationError(f"Correlation calculation failed: {e}")
