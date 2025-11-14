"""
Execution simulation for backtesting.

This module simulates realistic order execution including slippage,
commissions, market impact, and partial fills.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any
import random

import pandas as pd
import numpy as np

from .config import BacktestConfig, OrderType, SlippageModel, CommissionModel
from .exceptions import (
    ExecutionError,
    InsufficientCapitalError,
    InvalidOrderError,
)


logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """Order side (buy or sell)."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order execution status."""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass
class Order:
    """
    Represents a trading order.

    Attributes:
        ticker: Security ticker
        side: Buy or sell
        quantity: Number of shares
        order_type: Type of order
        timestamp: Order timestamp
        limit_price: Limit price (for limit orders)
        stop_price: Stop price (for stop orders)
        filled_quantity: Quantity filled
        filled_price: Average fill price
        commission: Commission paid
        slippage: Slippage cost
        status: Order status
    """
    ticker: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    timestamp: datetime
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    filled_quantity: Decimal = Decimal("0")
    filled_price: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.PENDING

    def __post_init__(self):
        """Validate order."""
        if self.quantity <= 0:
            raise InvalidOrderError("Order quantity must be positive")

        if isinstance(self.side, str):
            self.side = OrderSide(self.side)

        if isinstance(self.order_type, str):
            self.order_type = OrderType(self.order_type)

        if isinstance(self.status, str):
            self.status = OrderStatus(self.status)

    @property
    def is_filled(self) -> bool:
        """Check if order is fully filled."""
        return self.status == OrderStatus.FILLED

    @property
    def is_partially_filled(self) -> bool:
        """Check if order is partially filled."""
        return self.status == OrderStatus.PARTIALLY_FILLED

    @property
    def remaining_quantity(self) -> Decimal:
        """Get remaining quantity to fill."""
        return self.quantity - self.filled_quantity

    def to_dict(self) -> Dict[str, Any]:
        """Convert order to dictionary."""
        return {
            'ticker': self.ticker,
            'side': self.side.value,
            'quantity': float(self.quantity),
            'order_type': self.order_type.value,
            'timestamp': self.timestamp,
            'limit_price': float(self.limit_price) if self.limit_price else None,
            'stop_price': float(self.stop_price) if self.stop_price else None,
            'filled_quantity': float(self.filled_quantity),
            'filled_price': float(self.filled_price),
            'commission': float(self.commission),
            'slippage': float(self.slippage),
            'status': self.status.value,
        }


@dataclass
class Fill:
    """
    Represents an order fill.

    Attributes:
        order_id: Associated order ID
        ticker: Security ticker
        side: Buy or sell
        quantity: Filled quantity
        price: Fill price
        timestamp: Fill timestamp
        commission: Commission paid
        slippage: Slippage cost
    """
    order_id: int
    ticker: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    timestamp: datetime
    commission: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")

    def to_dict(self) -> Dict[str, Any]:
        """Convert fill to dictionary."""
        return {
            'order_id': self.order_id,
            'ticker': self.ticker,
            'side': self.side.value if isinstance(self.side, OrderSide) else self.side,
            'quantity': float(self.quantity),
            'price': float(self.price),
            'timestamp': self.timestamp,
            'commission': float(self.commission),
            'slippage': float(self.slippage),
        }


class ExecutionSimulator:
    """
    Simulates realistic order execution.

    This class models slippage, commissions, market impact, and other
    execution costs to create realistic backtesting.

    Attributes:
        config: Backtest configuration
        fills: List of all fills
        order_count: Counter for order IDs
    """

    def __init__(self, config: BacktestConfig):
        """
        Initialize execution simulator.

        Args:
            config: Backtest configuration
        """
        self.config = config
        self.fills: list[Fill] = []
        self.order_count = 0

        # Set random seed for reproducibility
        if config.random_seed is not None:
            random.seed(config.random_seed)
            np.random.seed(config.random_seed)

        logger.info("ExecutionSimulator initialized")

    def execute_order(
        self,
        order: Order,
        current_price: Decimal,
        current_volume: Decimal,
        available_capital: Decimal,
    ) -> Order:
        """
        Execute an order.

        Args:
            order: Order to execute
            current_price: Current market price
            current_volume: Current trading volume
            available_capital: Available capital

        Returns:
            Updated order with fill information

        Raises:
            InsufficientCapitalError: If insufficient capital
            ExecutionError: If execution fails
        """
        self.order_count += 1

        # Check trading hours
        if self.config.trading_hours and not self._is_market_open(order.timestamp):
            order.status = OrderStatus.REJECTED
            logger.warning(f"Order rejected - market closed at {order.timestamp}")
            return order

        # Determine if order can be filled
        if not self._can_fill_order(order, current_price):
            order.status = OrderStatus.REJECTED
            logger.debug(f"Order rejected - price conditions not met")
            return order

        # Calculate fill price with slippage
        fill_price = self._calculate_fill_price(
            order,
            current_price,
            current_volume
        )

        # Calculate quantity to fill
        fill_quantity = order.quantity

        # Handle partial fills
        if self.config.partial_fills:
            fill_quantity = self._calculate_partial_fill(
                order.quantity,
                current_volume
            )

        # Check capital requirements
        if order.side == OrderSide.BUY:
            required_capital = fill_quantity * fill_price
            commission = self._calculate_commission(fill_quantity, fill_price)
            total_required = required_capital + commission

            if total_required > available_capital:
                if self.config.partial_fills:
                    # Fill what we can afford
                    affordable_quantity = available_capital / (fill_price * (Decimal("1") + self.config.commission))
                    fill_quantity = min(fill_quantity, affordable_quantity.quantize(Decimal("1")))

                    if fill_quantity <= 0:
                        order.status = OrderStatus.REJECTED
                        raise InsufficientCapitalError(
                            f"Insufficient capital: need {total_required}, have {available_capital}"
                        )
                else:
                    order.status = OrderStatus.REJECTED
                    raise InsufficientCapitalError(
                        f"Insufficient capital: need {total_required}, have {available_capital}"
                    )

        # Calculate final costs
        commission = self._calculate_commission(fill_quantity, fill_price)
        slippage_cost = abs(fill_price - current_price) * fill_quantity

        # Update order
        order.filled_quantity = fill_quantity
        order.filled_price = fill_price
        order.commission = commission
        order.slippage = slippage_cost

        if fill_quantity >= order.quantity:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED

        # Record fill
        fill = Fill(
            order_id=self.order_count,
            ticker=order.ticker,
            side=order.side,
            quantity=fill_quantity,
            price=fill_price,
            timestamp=order.timestamp,
            commission=commission,
            slippage=slippage_cost,
        )
        self.fills.append(fill)

        logger.debug(
            f"Order executed: {order.ticker} {order.side.value} "
            f"{fill_quantity} @ {fill_price} (comm: {commission}, slip: {slippage_cost})"
        )

        return order

    def _can_fill_order(self, order: Order, current_price: Decimal) -> bool:
        """
        Check if order can be filled at current price.

        Args:
            order: Order to check
            current_price: Current market price

        Returns:
            True if order can be filled
        """
        if order.order_type == OrderType.MARKET:
            return True

        elif order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY:
                return current_price <= order.limit_price
            else:
                return current_price >= order.limit_price

        elif order.order_type == OrderType.STOP:
            if order.side == OrderSide.BUY:
                return current_price >= order.stop_price
            else:
                return current_price <= order.stop_price

        return False

    def _calculate_fill_price(
        self,
        order: Order,
        current_price: Decimal,
        current_volume: Decimal
    ) -> Decimal:
        """
        Calculate fill price including slippage.

        Args:
            order: Order being filled
            current_price: Current market price
            current_volume: Current trading volume

        Returns:
            Fill price including slippage
        """
        base_price = current_price

        # Calculate slippage
        if self.config.slippage_model == SlippageModel.FIXED:
            slippage = self._calculate_fixed_slippage(order, base_price)

        elif self.config.slippage_model == SlippageModel.VOLUME_BASED:
            slippage = self._calculate_volume_slippage(
                order, base_price, current_volume
            )

        elif self.config.slippage_model == SlippageModel.SPREAD_BASED:
            slippage = self._calculate_spread_slippage(order, base_price)

        else:
            slippage = Decimal("0")

        # Apply slippage
        if order.side == OrderSide.BUY:
            fill_price = base_price * (Decimal("1") + slippage)
        else:
            fill_price = base_price * (Decimal("1") - slippage)

        return fill_price

    def _calculate_fixed_slippage(
        self,
        order: Order,
        base_price: Decimal
    ) -> Decimal:
        """Calculate fixed percentage slippage."""
        return self.config.slippage

    def _calculate_volume_slippage(
        self,
        order: Order,
        base_price: Decimal,
        current_volume: Decimal
    ) -> Decimal:
        """Calculate volume-based slippage."""
        if current_volume == 0:
            return self.config.slippage * Decimal("2")  # Penalty for low volume

        # Slippage increases with order size relative to volume
        volume_ratio = order.quantity / current_volume
        volume_impact = volume_ratio * Decimal("0.1")  # 10% impact per 1% of volume

        return self.config.slippage + volume_impact

    def _calculate_spread_slippage(
        self,
        order: Order,
        base_price: Decimal
    ) -> Decimal:
        """Calculate spread-based slippage."""
        # Assume bid-ask spread is 2x the configured slippage
        spread = self.config.slippage * Decimal("2")
        return spread / Decimal("2")  # Half spread

    def _calculate_commission(
        self,
        quantity: Decimal,
        price: Decimal
    ) -> Decimal:
        """
        Calculate commission for a trade.

        Args:
            quantity: Trade quantity
            price: Trade price

        Returns:
            Commission amount
        """
        if self.config.commission_model == CommissionModel.PERCENTAGE:
            return quantity * price * self.config.commission

        elif self.config.commission_model == CommissionModel.PER_SHARE:
            return quantity * self.config.commission

        elif self.config.commission_model == CommissionModel.FIXED_PER_TRADE:
            return self.config.commission

        else:
            return Decimal("0")

    def _calculate_partial_fill(
        self,
        order_quantity: Decimal,
        current_volume: Decimal
    ) -> Decimal:
        """
        Calculate partial fill quantity.

        Args:
            order_quantity: Requested quantity
            current_volume: Current market volume

        Returns:
            Quantity that can be filled
        """
        if current_volume == 0:
            return Decimal("0")

        # Can fill up to 10% of daily volume
        max_fillable = current_volume * Decimal("0.1")

        # Add randomness
        fill_ratio = Decimal(str(random.uniform(0.5, 1.0)))
        fillable = min(order_quantity, max_fillable) * fill_ratio

        return fillable.quantize(Decimal("1"))

    def _is_market_open(self, timestamp: datetime) -> bool:
        """
        Check if market is open at timestamp.

        Args:
            timestamp: Time to check

        Returns:
            True if market is open
        """
        if not self.config.trading_hours:
            return True

        # Get day of week (0 = Monday, 6 = Sunday)
        day_of_week = timestamp.weekday()

        # Check if weekend
        if day_of_week >= 5:  # Saturday or Sunday
            return False

        # Check trading hours (default: 9:30 AM - 4:00 PM ET)
        market_open = self.config.trading_hours.get('open', time(9, 30))
        market_close = self.config.trading_hours.get('close', time(16, 0))

        current_time = timestamp.time()

        return market_open <= current_time <= market_close

    def get_fills_df(self) -> pd.DataFrame:
        """
        Get fills as DataFrame.

        Returns:
            DataFrame with all fills
        """
        if not self.fills:
            return pd.DataFrame()

        return pd.DataFrame([fill.to_dict() for fill in self.fills])

    def get_total_commission(self) -> Decimal:
        """
        Get total commission paid.

        Returns:
            Total commission
        """
        return sum(fill.commission for fill in self.fills)

    def get_total_slippage(self) -> Decimal:
        """
        Get total slippage cost.

        Returns:
            Total slippage
        """
        return sum(fill.slippage for fill in self.fills)

    def reset(self) -> None:
        """Reset the execution simulator."""
        self.fills = []
        self.order_count = 0
        logger.info("ExecutionSimulator reset")


def create_market_order(
    ticker: str,
    side: OrderSide,
    quantity: Decimal,
    timestamp: datetime
) -> Order:
    """
    Create a market order.

    Args:
        ticker: Security ticker
        side: Buy or sell
        quantity: Quantity
        timestamp: Order timestamp

    Returns:
        Market order
    """
    return Order(
        ticker=ticker,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
        timestamp=timestamp,
    )


def create_limit_order(
    ticker: str,
    side: OrderSide,
    quantity: Decimal,
    limit_price: Decimal,
    timestamp: datetime
) -> Order:
    """
    Create a limit order.

    Args:
        ticker: Security ticker
        side: Buy or sell
        quantity: Quantity
        limit_price: Limit price
        timestamp: Order timestamp

    Returns:
        Limit order
    """
    return Order(
        ticker=ticker,
        side=side,
        quantity=quantity,
        order_type=OrderType.LIMIT,
        limit_price=limit_price,
        timestamp=timestamp,
    )
