"""
Position management for the portfolio system.

This module provides the Position class for tracking individual security
positions including quantity, cost basis, market value, and P&L.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
import logging

from tradingagents.security import validate_ticker
from .exceptions import (
    InvalidPositionError,
    InvalidPriceError,
    InvalidQuantityError,
    ValidationError,
)

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """
    Represents a position in a single security.

    A position tracks ownership of a specific security, including quantity,
    cost basis, and provides calculations for market value and P&L.

    Attributes:
        ticker: The security ticker symbol
        quantity: Number of shares/units owned (can be negative for short positions)
        cost_basis: Average cost per share/unit
        sector: Optional sector classification
        opened_at: Timestamp when position was first opened
        last_updated: Timestamp of last position update
        stop_loss: Optional stop-loss price
        take_profit: Optional take-profit price
        metadata: Optional additional metadata
    """

    ticker: str
    quantity: Decimal
    cost_basis: Decimal
    sector: Optional[str] = None
    opened_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate position data after initialization."""
        # Validate ticker
        try:
            self.ticker = validate_ticker(self.ticker)
        except ValueError as e:
            raise InvalidPositionError(f"Invalid ticker: {e}")

        # Convert to Decimal if needed
        if not isinstance(self.quantity, Decimal):
            try:
                self.quantity = Decimal(str(self.quantity))
            except (ValueError, TypeError) as e:
                raise InvalidQuantityError(f"Invalid quantity: {e}")

        if not isinstance(self.cost_basis, Decimal):
            try:
                self.cost_basis = Decimal(str(self.cost_basis))
            except (ValueError, TypeError) as e:
                raise InvalidPriceError(f"Invalid cost basis: {e}")

        # Validate quantity is not zero
        if self.quantity == 0:
            raise InvalidQuantityError("Position quantity cannot be zero")

        # Validate cost basis is positive
        if self.cost_basis <= 0:
            raise InvalidPriceError("Cost basis must be positive")

        # Convert optional Decimal fields
        if self.stop_loss is not None and not isinstance(self.stop_loss, Decimal):
            self.stop_loss = Decimal(str(self.stop_loss))

        if self.take_profit is not None and not isinstance(self.take_profit, Decimal):
            self.take_profit = Decimal(str(self.take_profit))

        # Validate stop loss and take profit
        if self.stop_loss is not None and self.stop_loss <= 0:
            raise InvalidPriceError("Stop loss must be positive")

        if self.take_profit is not None and self.take_profit <= 0:
            raise InvalidPriceError("Take profit must be positive")

        logger.info(
            f"Created position: {self.ticker} "
            f"quantity={self.quantity} cost_basis={self.cost_basis}"
        )

    @property
    def is_long(self) -> bool:
        """Check if this is a long position."""
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        """Check if this is a short position."""
        return self.quantity < 0

    def market_value(self, current_price: Decimal) -> Decimal:
        """
        Calculate the current market value of the position.

        Args:
            current_price: Current market price of the security

        Returns:
            Market value of the position

        Raises:
            InvalidPriceError: If current_price is invalid
        """
        if not isinstance(current_price, Decimal):
            try:
                current_price = Decimal(str(current_price))
            except (ValueError, TypeError) as e:
                raise InvalidPriceError(f"Invalid current price: {e}")

        if current_price <= 0:
            raise InvalidPriceError("Current price must be positive")

        return self.quantity * current_price

    def total_cost(self) -> Decimal:
        """
        Calculate the total cost of the position.

        Returns:
            Total cost (quantity * cost_basis)
        """
        return abs(self.quantity) * self.cost_basis

    def unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """
        Calculate unrealized profit/loss.

        For long positions: (current_price - cost_basis) * quantity
        For short positions: (cost_basis - current_price) * abs(quantity)

        Args:
            current_price: Current market price of the security

        Returns:
            Unrealized profit (positive) or loss (negative)

        Raises:
            InvalidPriceError: If current_price is invalid
        """
        if not isinstance(current_price, Decimal):
            try:
                current_price = Decimal(str(current_price))
            except (ValueError, TypeError) as e:
                raise InvalidPriceError(f"Invalid current price: {e}")

        if current_price <= 0:
            raise InvalidPriceError("Current price must be positive")

        if self.is_long:
            return (current_price - self.cost_basis) * self.quantity
        else:
            # For short positions
            return (self.cost_basis - current_price) * abs(self.quantity)

    def unrealized_pnl_percent(self, current_price: Decimal) -> Decimal:
        """
        Calculate unrealized P&L as a percentage of cost basis.

        Args:
            current_price: Current market price of the security

        Returns:
            Unrealized P&L as a percentage (e.g., 0.15 for 15% gain)

        Raises:
            InvalidPriceError: If current_price is invalid
        """
        if not isinstance(current_price, Decimal):
            try:
                current_price = Decimal(str(current_price))
            except (ValueError, TypeError) as e:
                raise InvalidPriceError(f"Invalid current price: {e}")

        if current_price <= 0:
            raise InvalidPriceError("Current price must be positive")

        total_cost = self.total_cost()
        if total_cost == 0:
            return Decimal('0')

        pnl = self.unrealized_pnl(current_price)
        return pnl / total_cost

    def update_quantity(self, quantity_delta: Decimal) -> None:
        """
        Update the position quantity and cost basis.

        This method handles adding to or reducing a position, including
        proper cost basis calculation.

        Args:
            quantity_delta: Change in quantity (positive to add, negative to reduce)

        Raises:
            InvalidQuantityError: If the resulting quantity would be zero
        """
        if not isinstance(quantity_delta, Decimal):
            try:
                quantity_delta = Decimal(str(quantity_delta))
            except (ValueError, TypeError) as e:
                raise InvalidQuantityError(f"Invalid quantity delta: {e}")

        new_quantity = self.quantity + quantity_delta

        if new_quantity == 0:
            raise InvalidQuantityError(
                "Quantity delta would result in zero position. "
                "Use close_position instead."
            )

        # Check if we're reversing the position (going from long to short or vice versa)
        if (self.is_long and new_quantity < 0) or (self.is_short and new_quantity > 0):
            raise InvalidQuantityError(
                "Cannot reverse position direction. Close position first."
            )

        self.quantity = new_quantity
        self.last_updated = datetime.now()

        logger.info(
            f"Updated position {self.ticker}: "
            f"delta={quantity_delta} new_quantity={self.quantity}"
        )

    def update_cost_basis(
        self,
        quantity_delta: Decimal,
        price: Decimal
    ) -> None:
        """
        Update cost basis when adding to a position.

        Uses weighted average cost basis calculation.

        Args:
            quantity_delta: Additional quantity being added
            price: Price of the additional shares

        Raises:
            InvalidQuantityError: If quantity_delta is invalid
            InvalidPriceError: If price is invalid
        """
        if not isinstance(quantity_delta, Decimal):
            try:
                quantity_delta = Decimal(str(quantity_delta))
            except (ValueError, TypeError) as e:
                raise InvalidQuantityError(f"Invalid quantity delta: {e}")

        if not isinstance(price, Decimal):
            try:
                price = Decimal(str(price))
            except (ValueError, TypeError) as e:
                raise InvalidPriceError(f"Invalid price: {e}")

        if price <= 0:
            raise InvalidPriceError("Price must be positive")

        # Only update cost basis when adding to the position
        if (self.is_long and quantity_delta > 0) or (self.is_short and quantity_delta < 0):
            current_value = abs(self.quantity) * self.cost_basis
            new_value = abs(quantity_delta) * price
            new_total_quantity = abs(self.quantity) + abs(quantity_delta)

            self.cost_basis = (current_value + new_value) / new_total_quantity

            logger.debug(
                f"Updated cost basis for {self.ticker}: "
                f"new_cost_basis={self.cost_basis}"
            )

    def should_trigger_stop_loss(self, current_price: Decimal) -> bool:
        """
        Check if stop loss should be triggered.

        Args:
            current_price: Current market price

        Returns:
            True if stop loss should be triggered, False otherwise
        """
        if self.stop_loss is None:
            return False

        if not isinstance(current_price, Decimal):
            try:
                current_price = Decimal(str(current_price))
            except (ValueError, TypeError):
                return False

        if self.is_long:
            return current_price <= self.stop_loss
        else:
            # For short positions, stop loss is triggered when price goes up
            return current_price >= self.stop_loss

    def should_trigger_take_profit(self, current_price: Decimal) -> bool:
        """
        Check if take profit should be triggered.

        Args:
            current_price: Current market price

        Returns:
            True if take profit should be triggered, False otherwise
        """
        if self.take_profit is None:
            return False

        if not isinstance(current_price, Decimal):
            try:
                current_price = Decimal(str(current_price))
            except (ValueError, TypeError):
                return False

        if self.is_long:
            return current_price >= self.take_profit
        else:
            # For short positions, take profit is triggered when price goes down
            return current_price <= self.take_profit

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert position to dictionary for serialization.

        Returns:
            Dictionary representation of the position
        """
        return {
            'ticker': self.ticker,
            'quantity': str(self.quantity),
            'cost_basis': str(self.cost_basis),
            'sector': self.sector,
            'opened_at': self.opened_at.isoformat(),
            'last_updated': self.last_updated.isoformat(),
            'stop_loss': str(self.stop_loss) if self.stop_loss else None,
            'take_profit': str(self.take_profit) if self.take_profit else None,
            'metadata': self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """
        Create a Position from a dictionary.

        Args:
            data: Dictionary containing position data

        Returns:
            Position instance

        Raises:
            ValidationError: If data is invalid
        """
        try:
            return cls(
                ticker=data['ticker'],
                quantity=Decimal(data['quantity']),
                cost_basis=Decimal(data['cost_basis']),
                sector=data.get('sector'),
                opened_at=datetime.fromisoformat(data['opened_at']),
                last_updated=datetime.fromisoformat(data['last_updated']),
                stop_loss=Decimal(data['stop_loss']) if data.get('stop_loss') else None,
                take_profit=Decimal(data['take_profit']) if data.get('take_profit') else None,
                metadata=data.get('metadata', {}),
            )
        except (KeyError, ValueError, TypeError) as e:
            raise ValidationError(f"Invalid position data: {e}")

    def __repr__(self) -> str:
        """String representation of the position."""
        position_type = "LONG" if self.is_long else "SHORT"
        return (
            f"Position({self.ticker}, {position_type}, "
            f"qty={self.quantity}, cost={self.cost_basis})"
        )
