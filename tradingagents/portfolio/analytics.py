"""
Performance analytics for the portfolio system.

This module provides comprehensive performance analytics including
returns calculation, risk metrics, trade statistics, and equity curve generation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
import logging
import math

from .exceptions import CalculationError, ValidationError

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """
    Record of a completed trade.

    Attributes:
        ticker: Security ticker symbol
        entry_date: Date position was opened
        exit_date: Date position was closed
        entry_price: Entry price
        exit_price: Exit price
        quantity: Quantity traded
        pnl: Profit/loss from the trade
        pnl_percent: Profit/loss as percentage
        commission: Total commission paid
        holding_period: Number of days held
        is_win: Whether the trade was profitable
    """

    ticker: str
    entry_date: datetime
    exit_date: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    pnl: Decimal
    pnl_percent: Decimal
    commission: Decimal
    holding_period: int
    is_win: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert trade record to dictionary."""
        return {
            'ticker': self.ticker,
            'entry_date': self.entry_date.isoformat(),
            'exit_date': self.exit_date.isoformat(),
            'entry_price': str(self.entry_price),
            'exit_price': str(self.exit_price),
            'quantity': str(self.quantity),
            'pnl': str(self.pnl),
            'pnl_percent': str(self.pnl_percent),
            'commission': str(self.commission),
            'holding_period': self.holding_period,
            'is_win': self.is_win,
        }


@dataclass
class PerformanceMetrics:
    """
    Comprehensive performance metrics for a portfolio.

    Attributes:
        total_return: Total return (as fraction)
        annualized_return: Annualized return
        total_trades: Total number of trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        win_rate: Percentage of winning trades
        profit_factor: Ratio of gross profits to gross losses
        average_win: Average profit from winning trades
        average_loss: Average loss from losing trades
        largest_win: Largest single winning trade
        largest_loss: Largest single losing trade
        sharpe_ratio: Risk-adjusted return metric
        sortino_ratio: Downside risk-adjusted return metric
        max_drawdown: Maximum peak-to-trough decline
        max_drawdown_duration: Duration of max drawdown in days
        calmar_ratio: Return / Max Drawdown
        volatility: Annualized volatility
        total_commission: Total commission paid
    """

    total_return: Decimal
    annualized_return: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    profit_factor: Decimal
    average_win: Decimal
    average_loss: Decimal
    largest_win: Decimal
    largest_loss: Decimal
    sharpe_ratio: Decimal
    sortino_ratio: Decimal
    max_drawdown: Decimal
    max_drawdown_duration: int
    calmar_ratio: Decimal
    volatility: Decimal
    total_commission: Decimal

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'total_return': str(self.total_return),
            'annualized_return': str(self.annualized_return),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': str(self.win_rate),
            'profit_factor': str(self.profit_factor),
            'average_win': str(self.average_win),
            'average_loss': str(self.average_loss),
            'largest_win': str(self.largest_win),
            'largest_loss': str(self.largest_loss),
            'sharpe_ratio': str(self.sharpe_ratio),
            'sortino_ratio': str(self.sortino_ratio),
            'max_drawdown': str(self.max_drawdown),
            'max_drawdown_duration': self.max_drawdown_duration,
            'calmar_ratio': str(self.calmar_ratio),
            'volatility': str(self.volatility),
            'total_commission': str(self.total_commission),
        }


class PerformanceAnalytics:
    """
    Analyzes portfolio performance and generates metrics.

    This class provides methods to calculate various performance metrics,
    generate equity curves, and analyze trade statistics.
    """

    def __init__(self):
        """Initialize the performance analytics engine."""
        self.equity_curve: List[Tuple[datetime, Decimal]] = []
        self.returns: List[Decimal] = []
        logger.info("Initialized PerformanceAnalytics")

    def calculate_returns(
        self,
        equity_curve: List[Tuple[datetime, Decimal]]
    ) -> List[Decimal]:
        """
        Calculate periodic returns from an equity curve.

        Args:
            equity_curve: List of (datetime, value) tuples

        Returns:
            List of periodic returns

        Raises:
            ValidationError: If equity curve is invalid
        """
        if len(equity_curve) < 2:
            return []

        try:
            returns = []
            for i in range(1, len(equity_curve)):
                prev_value = equity_curve[i - 1][1]
                curr_value = equity_curve[i][1]

                if prev_value == 0:
                    continue

                ret = (curr_value - prev_value) / prev_value
                returns.append(ret)

            return returns

        except (IndexError, ZeroDivisionError, TypeError) as e:
            raise CalculationError(f"Returns calculation failed: {e}")

    def calculate_total_return(
        self,
        initial_value: Decimal,
        final_value: Decimal
    ) -> Decimal:
        """
        Calculate total return.

        Args:
            initial_value: Initial portfolio value
            final_value: Final portfolio value

        Returns:
            Total return as a fraction

        Raises:
            ValidationError: If values are invalid
        """
        if initial_value <= 0:
            raise ValidationError("Initial value must be positive")

        return (final_value - initial_value) / initial_value

    def calculate_annualized_return(
        self,
        total_return: Decimal,
        days: int
    ) -> Decimal:
        """
        Calculate annualized return from total return.

        Args:
            total_return: Total return as a fraction
            days: Number of days in the period

        Returns:
            Annualized return

        Raises:
            ValidationError: If inputs are invalid
        """
        if days <= 0:
            raise ValidationError("Days must be positive")

        years = Decimal(days) / Decimal('365.25')

        if years == 0:
            return Decimal('0')

        # Annualized return = (1 + total_return) ^ (1/years) - 1
        try:
            annualized = Decimal(
                math.pow(float(1 + total_return), float(1 / years))
            ) - 1
            return annualized
        except (ValueError, OverflowError) as e:
            raise CalculationError(f"Annualized return calculation failed: {e}")

    def calculate_volatility(
        self,
        returns: List[Decimal]
    ) -> Decimal:
        """
        Calculate annualized volatility.

        Args:
            returns: List of periodic returns

        Returns:
            Annualized volatility (standard deviation)

        Raises:
            ValidationError: If returns is empty
        """
        if not returns:
            raise ValidationError("Returns list cannot be empty")

        try:
            # Calculate mean
            mean = sum(returns) / len(returns)

            # Calculate variance
            variance = sum((r - mean) ** 2 for r in returns) / len(returns)

            # Calculate standard deviation
            std_dev = Decimal(math.sqrt(float(variance)))

            # Annualize (assuming daily returns)
            annualized_vol = std_dev * Decimal(math.sqrt(252))

            return annualized_vol

        except (ValueError, TypeError) as e:
            raise CalculationError(f"Volatility calculation failed: {e}")

    def calculate_trade_statistics(
        self,
        trades: List[TradeRecord]
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive trade statistics.

        Args:
            trades: List of trade records

        Returns:
            Dictionary of trade statistics

        Raises:
            ValidationError: If trades list is invalid
        """
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': Decimal('0'),
                'profit_factor': Decimal('0'),
                'average_win': Decimal('0'),
                'average_loss': Decimal('0'),
                'largest_win': Decimal('0'),
                'largest_loss': Decimal('0'),
                'average_holding_period': 0,
                'total_commission': Decimal('0'),
            }

        try:
            winning_trades = [t for t in trades if t.is_win]
            losing_trades = [t for t in trades if not t.is_win]

            total_trades = len(trades)
            num_wins = len(winning_trades)
            num_losses = len(losing_trades)

            # Win rate
            win_rate = Decimal(num_wins) / Decimal(total_trades) if total_trades > 0 else Decimal('0')

            # Profit factor
            gross_profit = sum(t.pnl for t in winning_trades)
            gross_loss = abs(sum(t.pnl for t in losing_trades))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else Decimal('0')

            # Average win/loss
            average_win = gross_profit / num_wins if num_wins > 0 else Decimal('0')
            average_loss = gross_loss / num_losses if num_losses > 0 else Decimal('0')

            # Largest win/loss
            largest_win = max((t.pnl for t in winning_trades), default=Decimal('0'))
            largest_loss = abs(min((t.pnl for t in losing_trades), default=Decimal('0')))

            # Average holding period
            avg_holding = sum(t.holding_period for t in trades) / total_trades

            # Total commission
            total_commission = sum(t.commission for t in trades)

            return {
                'total_trades': total_trades,
                'winning_trades': num_wins,
                'losing_trades': num_losses,
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'average_win': average_win,
                'average_loss': average_loss,
                'largest_win': largest_win,
                'largest_loss': largest_loss,
                'average_holding_period': int(avg_holding),
                'total_commission': total_commission,
            }

        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise CalculationError(f"Trade statistics calculation failed: {e}")

    def generate_performance_metrics(
        self,
        equity_curve: List[Tuple[datetime, Decimal]],
        trades: List[TradeRecord],
        initial_capital: Decimal,
        risk_free_rate: Decimal = Decimal('0.02')
    ) -> PerformanceMetrics:
        """
        Generate comprehensive performance metrics.

        Args:
            equity_curve: List of (datetime, value) tuples
            trades: List of completed trades
            initial_capital: Initial portfolio capital
            risk_free_rate: Annual risk-free rate (default 2%)

        Returns:
            PerformanceMetrics object

        Raises:
            ValidationError: If inputs are invalid
            CalculationError: If calculation fails
        """
        if not equity_curve:
            raise ValidationError("Equity curve cannot be empty")

        if initial_capital <= 0:
            raise ValidationError("Initial capital must be positive")

        try:
            # Calculate returns
            returns = self.calculate_returns(equity_curve)

            # Total return
            final_value = equity_curve[-1][1]
            total_return = self.calculate_total_return(initial_capital, final_value)

            # Annualized return
            start_date = equity_curve[0][0]
            end_date = equity_curve[-1][0]
            days = (end_date - start_date).days
            annualized_return = self.calculate_annualized_return(total_return, max(days, 1))

            # Volatility
            volatility = self.calculate_volatility(returns) if returns else Decimal('0')

            # Sharpe ratio
            from .risk import RiskManager
            risk_manager = RiskManager()
            sharpe = risk_manager.calculate_sharpe_ratio(returns, risk_free_rate) if returns else Decimal('0')
            sortino = risk_manager.calculate_sortino_ratio(returns, risk_free_rate) if returns else Decimal('0')

            # Max drawdown
            equity_values = [value for _, value in equity_curve]
            max_dd, _, _ = risk_manager.calculate_max_drawdown(equity_values)

            # Max drawdown duration
            max_dd_duration = self._calculate_max_drawdown_duration(equity_curve)

            # Calmar ratio
            calmar = abs(annualized_return / max_dd) if max_dd > 0 else Decimal('0')

            # Trade statistics
            trade_stats = self.calculate_trade_statistics(trades)

            return PerformanceMetrics(
                total_return=total_return,
                annualized_return=annualized_return,
                total_trades=trade_stats['total_trades'],
                winning_trades=trade_stats['winning_trades'],
                losing_trades=trade_stats['losing_trades'],
                win_rate=trade_stats['win_rate'],
                profit_factor=trade_stats['profit_factor'],
                average_win=trade_stats['average_win'],
                average_loss=trade_stats['average_loss'],
                largest_win=trade_stats['largest_win'],
                largest_loss=trade_stats['largest_loss'],
                sharpe_ratio=sharpe,
                sortino_ratio=sortino,
                max_drawdown=max_dd,
                max_drawdown_duration=max_dd_duration,
                calmar_ratio=calmar,
                volatility=volatility,
                total_commission=trade_stats['total_commission'],
            )

        except Exception as e:
            raise CalculationError(f"Performance metrics generation failed: {e}")

    def _calculate_max_drawdown_duration(
        self,
        equity_curve: List[Tuple[datetime, Decimal]]
    ) -> int:
        """
        Calculate the maximum drawdown duration in days.

        Args:
            equity_curve: List of (datetime, value) tuples

        Returns:
            Maximum drawdown duration in days
        """
        if len(equity_curve) < 2:
            return 0

        max_duration = 0
        peak_value = equity_curve[0][1]
        peak_date = equity_curve[0][0]
        current_duration = 0

        for date, value in equity_curve:
            if value > peak_value:
                peak_value = value
                peak_date = date
                current_duration = 0
            else:
                current_duration = (date - peak_date).days
                max_duration = max(max_duration, current_duration)

        return max_duration

    def calculate_monthly_returns(
        self,
        equity_curve: List[Tuple[datetime, Decimal]]
    ) -> Dict[str, Decimal]:
        """
        Calculate monthly returns from equity curve.

        Args:
            equity_curve: List of (datetime, value) tuples

        Returns:
            Dictionary mapping month (YYYY-MM) to return

        Raises:
            ValidationError: If equity curve is invalid
        """
        if not equity_curve:
            raise ValidationError("Equity curve cannot be empty")

        try:
            monthly_returns = {}
            monthly_values = {}

            # Group values by month
            for date, value in equity_curve:
                month_key = date.strftime('%Y-%m')
                if month_key not in monthly_values:
                    monthly_values[month_key] = []
                monthly_values[month_key].append((date, value))

            # Calculate return for each month
            sorted_months = sorted(monthly_values.keys())
            for i, month in enumerate(sorted_months):
                month_data = monthly_values[month]
                start_value = month_data[0][1]
                end_value = month_data[-1][1]

                if start_value > 0:
                    monthly_return = (end_value - start_value) / start_value
                    monthly_returns[month] = monthly_return

            return monthly_returns

        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise CalculationError(f"Monthly returns calculation failed: {e}")

    def calculate_rolling_sharpe(
        self,
        equity_curve: List[Tuple[datetime, Decimal]],
        window_days: int = 252,
        risk_free_rate: Decimal = Decimal('0.02')
    ) -> List[Tuple[datetime, Decimal]]:
        """
        Calculate rolling Sharpe ratio.

        Args:
            equity_curve: List of (datetime, value) tuples
            window_days: Rolling window size in days
            risk_free_rate: Annual risk-free rate

        Returns:
            List of (date, sharpe_ratio) tuples

        Raises:
            ValidationError: If inputs are invalid
        """
        if not equity_curve:
            raise ValidationError("Equity curve cannot be empty")

        if window_days < 2:
            raise ValidationError("Window days must be at least 2")

        try:
            returns = self.calculate_returns(equity_curve)
            rolling_sharpe = []

            from .risk import RiskManager
            risk_manager = RiskManager()

            for i in range(window_days - 1, len(returns)):
                window_returns = returns[i - window_days + 1:i + 1]
                sharpe = risk_manager.calculate_sharpe_ratio(window_returns, risk_free_rate)
                rolling_sharpe.append((equity_curve[i + 1][0], sharpe))

            return rolling_sharpe

        except Exception as e:
            raise CalculationError(f"Rolling Sharpe calculation failed: {e}")

    def generate_equity_curve_summary(
        self,
        equity_curve: List[Tuple[datetime, Decimal]]
    ) -> Dict[str, Any]:
        """
        Generate a summary of the equity curve.

        Args:
            equity_curve: List of (datetime, value) tuples

        Returns:
            Dictionary with equity curve summary statistics
        """
        if not equity_curve:
            return {
                'start_date': None,
                'end_date': None,
                'start_value': Decimal('0'),
                'end_value': Decimal('0'),
                'peak_value': Decimal('0'),
                'trough_value': Decimal('0'),
                'data_points': 0,
            }

        start_date = equity_curve[0][0]
        end_date = equity_curve[-1][0]
        start_value = equity_curve[0][1]
        end_value = equity_curve[-1][1]

        values = [v for _, v in equity_curve]
        peak_value = max(values)
        trough_value = min(values)

        return {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'start_value': str(start_value),
            'end_value': str(end_value),
            'peak_value': str(peak_value),
            'trough_value': str(trough_value),
            'data_points': len(equity_curve),
        }
