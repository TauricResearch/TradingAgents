"""
Core portfolio management for the TradingAgents framework.

This module provides the main Portfolio class for managing positions,
executing orders, tracking P&L, and calculating risk metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
import threading
import logging

from tradingagents.security import validate_ticker
from .position import Position
from .orders import (
    Order, MarketOrder, LimitOrder, StopLossOrder, TakeProfitOrder,
    OrderStatus, create_order_from_dict
)
from .risk import RiskManager, RiskLimits
from .analytics import PerformanceAnalytics, TradeRecord, PerformanceMetrics
from .persistence import PortfolioPersistence
from .exceptions import (
    InsufficientFundsError,
    InsufficientSharesError,
    InvalidOrderError,
    PositionNotFoundError,
    RiskLimitExceededError,
    ValidationError,
    PersistenceError,
)

logger = logging.getLogger(__name__)


class Portfolio:
    """
    Main portfolio management class.

    This class manages a portfolio of positions, handles order execution,
    tracks cash and P&L, enforces risk limits, and provides performance
    analytics.

    Thread-safe for concurrent operations.

    Attributes:
        initial_capital: Initial portfolio capital
        cash: Current cash balance
        positions: Dictionary of current positions (ticker -> Position)
        commission_rate: Commission rate as a fraction (e.g., 0.001 for 0.1%)
        risk_manager: Risk management component
        analytics: Performance analytics component
        persistence: Persistence component
    """

    def __init__(
        self,
        initial_capital: Decimal,
        commission_rate: Decimal = Decimal('0.001'),
        risk_limits: Optional[RiskLimits] = None,
        persist_dir: Optional[str] = None
    ):
        """
        Initialize a new portfolio.

        Args:
            initial_capital: Starting capital
            commission_rate: Commission rate as a fraction (default 0.1%)
            risk_limits: Risk limits configuration (uses defaults if None)
            persist_dir: Directory for persistence (default ./portfolio_data)

        Raises:
            ValidationError: If inputs are invalid
        """
        # Validate inputs
        if not isinstance(initial_capital, Decimal):
            try:
                initial_capital = Decimal(str(initial_capital))
            except (ValueError, TypeError) as e:
                raise ValidationError(f"Invalid initial capital: {e}")

        if initial_capital <= 0:
            raise ValidationError("Initial capital must be positive")

        if not isinstance(commission_rate, Decimal):
            try:
                commission_rate = Decimal(str(commission_rate))
            except (ValueError, TypeError) as e:
                raise ValidationError(f"Invalid commission rate: {e}")

        if commission_rate < 0 or commission_rate > 1:
            raise ValidationError("Commission rate must be between 0 and 1")

        # Initialize core attributes
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.commission_rate = commission_rate
        self.positions: Dict[str, Position] = {}

        # Trade tracking
        self.trade_history: List[TradeRecord] = []
        self.closed_positions: Dict[str, List[Position]] = {}
        self.pending_orders: List[Order] = []

        # Equity curve tracking
        self.equity_curve: List[Tuple[datetime, Decimal]] = [
            (datetime.now(), initial_capital)
        ]

        # Peak tracking for drawdown
        self.peak_value = initial_capital

        # Components
        self.risk_manager = RiskManager(risk_limits)
        self.analytics = PerformanceAnalytics()
        self.persistence = PortfolioPersistence(persist_dir)

        # Thread safety
        self._lock = threading.RLock()

        logger.info(
            f"Initialized portfolio with capital={initial_capital}, "
            f"commission={commission_rate}"
        )

    def execute_order(
        self,
        order: Order,
        current_price: Decimal,
        check_risk: bool = True
    ) -> None:
        """
        Execute an order at the current price.

        Args:
            order: Order to execute
            current_price: Current market price
            check_risk: Whether to check risk limits (default True)

        Raises:
            InvalidOrderError: If order cannot be executed
            InsufficientFundsError: If insufficient cash for buy order
            InsufficientSharesError: If insufficient shares for sell order
            RiskLimitExceededError: If trade would exceed risk limits
            ValidationError: If inputs are invalid
        """
        with self._lock:
            # Validate price
            if not isinstance(current_price, Decimal):
                try:
                    current_price = Decimal(str(current_price))
                except (ValueError, TypeError) as e:
                    raise ValidationError(f"Invalid current price: {e}")

            if current_price <= 0:
                raise ValidationError("Current price must be positive")

            # Check if order can execute at current price
            if not order.can_execute(current_price):
                raise InvalidOrderError(
                    f"Order cannot execute at current price {current_price}"
                )

            # Calculate order value and commission
            order_value = abs(order.quantity) * current_price
            commission = order_value * self.commission_rate

            # Execute based on order side
            if order.is_buy:
                self._execute_buy_order(
                    order, current_price, order_value, commission, check_risk
                )
            else:
                self._execute_sell_order(
                    order, current_price, order_value, commission, check_risk
                )

            # Mark order as executed
            order.mark_executed(abs(order.quantity), current_price)

            # Update equity curve
            self._update_equity_curve(current_price)

            logger.info(
                f"Executed {order.side.value} order: {order.ticker} "
                f"qty={abs(order.quantity)} price={current_price} "
                f"commission={commission}"
            )

    def _execute_buy_order(
        self,
        order: Order,
        current_price: Decimal,
        order_value: Decimal,
        commission: Decimal,
        check_risk: bool
    ) -> None:
        """Execute a buy order."""
        total_cost = order_value + commission

        # Check sufficient funds
        if total_cost > self.cash:
            raise InsufficientFundsError(
                f"Insufficient funds: need {total_cost}, have {self.cash}"
            )

        # Risk checks
        if check_risk:
            # Check position size limit
            portfolio_value = self.total_value()
            new_position_value = order_value

            if order.ticker in self.positions:
                current_position_value = self.positions[order.ticker].market_value(current_price)
                new_position_value += current_position_value

            self.risk_manager.check_position_size_limit(
                new_position_value, portfolio_value, order.ticker
            )

            # Check cash reserve
            new_cash = self.cash - total_cost
            self.risk_manager.check_cash_reserve(new_cash, portfolio_value)

        # Update or create position
        if order.ticker in self.positions:
            # Add to existing position
            position = self.positions[order.ticker]
            position.update_cost_basis(order.quantity, current_price)
            position.update_quantity(order.quantity)
        else:
            # Create new position
            self.positions[order.ticker] = Position(
                ticker=order.ticker,
                quantity=order.quantity,
                cost_basis=current_price,
                metadata=order.metadata
            )

        # Deduct cash
        self.cash -= total_cost

    def _execute_sell_order(
        self,
        order: Order,
        current_price: Decimal,
        order_value: Decimal,
        commission: Decimal,
        check_risk: bool
    ) -> None:
        """Execute a sell order."""
        # Check if position exists
        if order.ticker not in self.positions:
            raise PositionNotFoundError(
                f"No position in {order.ticker} to sell"
            )

        position = self.positions[order.ticker]
        sell_quantity = abs(order.quantity)

        # Check sufficient shares
        if sell_quantity > abs(position.quantity):
            raise InsufficientSharesError(
                f"Insufficient shares: trying to sell {sell_quantity}, "
                f"have {abs(position.quantity)}"
            )

        # Calculate P&L for this sale
        cost_basis_value = sell_quantity * position.cost_basis
        sale_proceeds = order_value - commission
        pnl = sale_proceeds - cost_basis_value
        pnl_percent = pnl / cost_basis_value if cost_basis_value > 0 else Decimal('0')

        # Check if closing entire position
        if sell_quantity == abs(position.quantity):
            # Record completed trade
            trade_record = TradeRecord(
                ticker=order.ticker,
                entry_date=position.opened_at,
                exit_date=datetime.now(),
                entry_price=position.cost_basis,
                exit_price=current_price,
                quantity=position.quantity,
                pnl=pnl,
                pnl_percent=pnl_percent,
                commission=commission,
                holding_period=(datetime.now() - position.opened_at).days,
                is_win=pnl > 0
            )
            self.trade_history.append(trade_record)

            # Move to closed positions
            if order.ticker not in self.closed_positions:
                self.closed_positions[order.ticker] = []
            self.closed_positions[order.ticker].append(position)

            # Remove from active positions
            del self.positions[order.ticker]

        else:
            # Partially close position
            position.update_quantity(-sell_quantity)

        # Add proceeds to cash
        self.cash += sale_proceeds

    def get_position(self, ticker: str) -> Optional[Position]:
        """
        Get a position by ticker.

        Args:
            ticker: Ticker symbol

        Returns:
            Position object or None if not found

        Raises:
            ValidationError: If ticker is invalid
        """
        with self._lock:
            try:
                ticker = validate_ticker(ticker)
            except ValueError as e:
                raise ValidationError(f"Invalid ticker: {e}")

            return self.positions.get(ticker)

    def get_all_positions(self) -> Dict[str, Position]:
        """
        Get all current positions.

        Returns:
            Dictionary mapping ticker to Position
        """
        with self._lock:
            return self.positions.copy()

    def total_value(self, prices: Optional[Dict[str, Decimal]] = None) -> Decimal:
        """
        Calculate total portfolio value.

        Args:
            prices: Optional dict of current prices (ticker -> price)
                   If None, uses cost basis for positions

        Returns:
            Total portfolio value (cash + positions)

        Raises:
            ValidationError: If prices are invalid
        """
        with self._lock:
            total = self.cash

            for ticker, position in self.positions.items():
                if prices and ticker in prices:
                    price = prices[ticker]
                    if not isinstance(price, Decimal):
                        price = Decimal(str(price))
                    if price <= 0:
                        raise ValidationError(f"Invalid price for {ticker}: {price}")
                    total += position.market_value(price)
                else:
                    # Use cost basis if no price provided
                    total += position.total_cost()

            return total

    def unrealized_pnl(self, prices: Dict[str, Decimal]) -> Decimal:
        """
        Calculate total unrealized P&L.

        Args:
            prices: Dictionary of current prices (ticker -> price)

        Returns:
            Total unrealized P&L

        Raises:
            ValidationError: If prices are invalid
        """
        with self._lock:
            total_pnl = Decimal('0')

            for ticker, position in self.positions.items():
                if ticker in prices:
                    price = prices[ticker]
                    if not isinstance(price, Decimal):
                        price = Decimal(str(price))
                    total_pnl += position.unrealized_pnl(price)

            return total_pnl

    def realized_pnl(self) -> Decimal:
        """
        Calculate total realized P&L from closed trades.

        Returns:
            Total realized P&L
        """
        with self._lock:
            return sum(trade.pnl for trade in self.trade_history)

    def get_performance_metrics(
        self,
        risk_free_rate: Decimal = Decimal('0.02')
    ) -> PerformanceMetrics:
        """
        Get comprehensive performance metrics.

        Args:
            risk_free_rate: Annual risk-free rate (default 2%)

        Returns:
            PerformanceMetrics object

        Raises:
            ValidationError: If risk_free_rate is invalid
        """
        with self._lock:
            return self.analytics.generate_performance_metrics(
                self.equity_curve,
                self.trade_history,
                self.initial_capital,
                risk_free_rate
            )

    def get_equity_curve(self) -> List[Tuple[datetime, Decimal]]:
        """
        Get the equity curve.

        Returns:
            List of (datetime, value) tuples
        """
        with self._lock:
            return self.equity_curve.copy()

    def _update_equity_curve(
        self,
        current_price: Optional[Decimal] = None,
        prices: Optional[Dict[str, Decimal]] = None
    ) -> None:
        """
        Update the equity curve with current portfolio value.

        Args:
            current_price: Single price to use for all positions
            prices: Dictionary of prices per ticker
        """
        if prices is None and current_price is None:
            # Use cost basis
            value = self.total_value()
        elif prices is not None:
            value = self.total_value(prices)
        else:
            # Use single price for all positions
            price_dict = {ticker: current_price for ticker in self.positions.keys()}
            value = self.total_value(price_dict)

        self.equity_curve.append((datetime.now(), value))

        # Update peak value
        if value > self.peak_value:
            self.peak_value = value

    def check_stop_loss_triggers(
        self,
        prices: Dict[str, Decimal]
    ) -> List[Order]:
        """
        Check if any positions should trigger stop-loss orders.

        Args:
            prices: Dictionary of current prices

        Returns:
            List of stop-loss orders that should be executed
        """
        with self._lock:
            stop_loss_orders = []

            for ticker, position in self.positions.items():
                if ticker not in prices:
                    continue

                price = prices[ticker]
                if not isinstance(price, Decimal):
                    price = Decimal(str(price))

                if position.should_trigger_stop_loss(price):
                    # Create stop-loss order to close position
                    order = StopLossOrder(
                        ticker=ticker,
                        quantity=-position.quantity,  # Opposite sign to close
                        stop_price=position.stop_loss
                    )
                    stop_loss_orders.append(order)

                    logger.warning(
                        f"Stop-loss triggered for {ticker} at {price} "
                        f"(stop={position.stop_loss})"
                    )

            return stop_loss_orders

    def check_take_profit_triggers(
        self,
        prices: Dict[str, Decimal]
    ) -> List[Order]:
        """
        Check if any positions should trigger take-profit orders.

        Args:
            prices: Dictionary of current prices

        Returns:
            List of take-profit orders that should be executed
        """
        with self._lock:
            take_profit_orders = []

            for ticker, position in self.positions.items():
                if ticker not in prices:
                    continue

                price = prices[ticker]
                if not isinstance(price, Decimal):
                    price = Decimal(str(price))

                if position.should_trigger_take_profit(price):
                    # Create take-profit order to close position
                    order = TakeProfitOrder(
                        ticker=ticker,
                        quantity=-position.quantity,  # Opposite sign to close
                        target_price=position.take_profit
                    )
                    take_profit_orders.append(order)

                    logger.info(
                        f"Take-profit triggered for {ticker} at {price} "
                        f"(target={position.take_profit})"
                    )

            return take_profit_orders

    def save(self, filename: str = 'portfolio_state.json') -> None:
        """
        Save portfolio state to a file.

        Args:
            filename: Name of the file to save to

        Raises:
            PersistenceError: If save fails
        """
        with self._lock:
            portfolio_data = self.to_dict()
            self.persistence.save_to_json(portfolio_data, filename)
            logger.info(f"Saved portfolio to {filename}")

    @classmethod
    def load(cls, filename: str = 'portfolio_state.json', persist_dir: Optional[str] = None) -> 'Portfolio':
        """
        Load portfolio state from a file.

        Args:
            filename: Name of the file to load from
            persist_dir: Directory containing the file

        Returns:
            Portfolio instance

        Raises:
            PersistenceError: If load fails
        """
        persistence = PortfolioPersistence(persist_dir)
        portfolio_data = persistence.load_from_json(filename)

        # Create portfolio with loaded data
        portfolio = cls(
            initial_capital=portfolio_data['initial_capital'],
            commission_rate=portfolio_data['commission_rate'],
            persist_dir=persist_dir
        )

        # Restore state
        portfolio.cash = portfolio_data['cash']

        # Restore positions
        for ticker, pos_data in portfolio_data.get('positions', {}).items():
            portfolio.positions[ticker] = Position.from_dict(pos_data)

        # Restore trade history
        for trade_data in portfolio_data.get('trade_history', []):
            trade = TradeRecord(
                ticker=trade_data['ticker'],
                entry_date=datetime.fromisoformat(trade_data['entry_date']),
                exit_date=datetime.fromisoformat(trade_data['exit_date']),
                entry_price=Decimal(trade_data['entry_price']),
                exit_price=Decimal(trade_data['exit_price']),
                quantity=Decimal(trade_data['quantity']),
                pnl=Decimal(trade_data['pnl']),
                pnl_percent=Decimal(trade_data['pnl_percent']),
                commission=Decimal(trade_data['commission']),
                holding_period=trade_data['holding_period'],
                is_win=trade_data['is_win']
            )
            portfolio.trade_history.append(trade)

        # Restore equity curve
        for point in portfolio_data.get('equity_curve', []):
            portfolio.equity_curve.append((
                datetime.fromisoformat(point[0]),
                Decimal(point[1])
            ))

        # Restore peak value
        portfolio.peak_value = portfolio_data.get('peak_value', portfolio.initial_capital)

        logger.info(f"Loaded portfolio from {filename}")

        return portfolio

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert portfolio to dictionary for serialization.

        Returns:
            Dictionary representation of the portfolio
        """
        with self._lock:
            return {
                'initial_capital': str(self.initial_capital),
                'cash': str(self.cash),
                'commission_rate': str(self.commission_rate),
                'positions': {
                    ticker: position.to_dict()
                    for ticker, position in self.positions.items()
                },
                'trade_history': [
                    trade.to_dict() for trade in self.trade_history
                ],
                'equity_curve': [
                    (dt.isoformat(), str(value))
                    for dt, value in self.equity_curve
                ],
                'peak_value': str(self.peak_value),
                'timestamp': datetime.now().isoformat(),
            }

    def summary(self) -> Dict[str, Any]:
        """
        Get a summary of the portfolio.

        Returns:
            Dictionary with portfolio summary
        """
        with self._lock:
            total_val = self.total_value()
            realized = self.realized_pnl()

            return {
                'total_value': str(total_val),
                'cash': str(self.cash),
                'invested': str(total_val - self.cash),
                'num_positions': len(self.positions),
                'realized_pnl': str(realized),
                'total_return': str((total_val - self.initial_capital) / self.initial_capital),
                'num_trades': len(self.trade_history),
                'positions': list(self.positions.keys()),
            }

    def __repr__(self) -> str:
        """String representation of the portfolio."""
        with self._lock:
            total_val = self.total_value()
            return (
                f"Portfolio(value={total_val}, cash={self.cash}, "
                f"positions={len(self.positions)})"
            )
