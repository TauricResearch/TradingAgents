"""Order management with execution states and slippage modeling."""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order execution states."""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"


class PriceType(Enum):
    """Price reference for order execution."""
    OPEN = "OPEN"           # Next day open
    CLOSE = "CLOSE"         # Daily close
    VWAP = "VWAP"          # Volume-weighted average price
    LAST = "LAST"          # Last available trade price


class Order:
    """Represents a single trading order."""
    
    def __init__(self, order_id: str, ticker: str, transaction_type: str,
                 quantity_requested: float, price_type: PriceType,
                 reference_price: float, slippage_tolerance_pct: float = 1.0):
        """Initialize an order.
        
        Args:
            order_id: Unique order identifier
            ticker: Stock ticker
            transaction_type: 'BUY' or 'SELL'
            quantity_requested: Quantity to trade
            price_type: Price reference point
            reference_price: Expected execution price
            slippage_tolerance_pct: Maximum acceptable slippage %
        """
        self.order_id = order_id
        self.ticker = ticker
        self.transaction_type = transaction_type
        self.quantity_requested = quantity_requested
        self.price_type = price_type
        self.reference_price = reference_price
        self.slippage_tolerance_pct = slippage_tolerance_pct
        
        self.status = OrderStatus.PENDING
        self.quantity_filled = 0.0
        self.execution_price = None
        self.actual_slippage_pct = 0.0
        self.created_at = datetime.now()
        self.filled_at = None
        self.expires_at = self.created_at + timedelta(hours=1)  # Auto-expire after 1 hour
    
    def execute(self, execution_price: float, quantity_filled: float, 
                available_volume: float) -> bool:
        """Execute order at given price.
        
        Args:
            execution_price: Actual execution price
            quantity_filled: Actual quantity filled
            available_volume: Available market volume
            
        Returns:
            True if order executed (fully or partially), False if rejected
        """
        # Calculate slippage
        self.actual_slippage_pct = abs(execution_price - self.reference_price) / self.reference_price * 100
        
        # Reject if slippage exceeds tolerance
        if self.actual_slippage_pct > self.slippage_tolerance_pct:
            self.status = OrderStatus.REJECTED
            logger.warning(f"Order {self.order_id} rejected: slippage {self.actual_slippage_pct:.2f}% "
                          f"exceeds tolerance {self.slippage_tolerance_pct}%")
            return False
        
        # Check volume availability
        if quantity_filled < self.quantity_requested:
            if quantity_filled == 0:
                self.status = OrderStatus.REJECTED
                logger.warning(f"Order {self.order_id} rejected: insufficient volume")
                return False
            else:
                self.status = OrderStatus.PARTIALLY_FILLED
                logger.info(f"Order {self.order_id} partially filled: {quantity_filled}/{self.quantity_requested}")
        else:
            self.status = OrderStatus.FILLED
        
        self.quantity_filled = quantity_filled
        self.execution_price = execution_price
        self.filled_at = datetime.now()
        return True
    
    def is_expired(self) -> bool:
        """Check if order has expired."""
        return datetime.now() > self.expires_at
    
    def auto_cancel_if_expired(self):
        """Auto-cancel if expiry time reached."""
        if self.is_expired() and self.status == OrderStatus.PENDING:
            self.status = OrderStatus.REJECTED
            logger.info(f"Order {self.order_id} auto-canceled: expired")
    
    def get_total_value(self) -> float:
        """Get total trade value (quantity_filled * execution_price)."""
        if self.execution_price and self.quantity_filled > 0:
            return self.quantity_filled * self.execution_price
        return 0.0
    
    def to_dict(self) -> Dict:
        """Convert order to dictionary for storage."""
        return {
            "order_id": self.order_id,
            "ticker": self.ticker,
            "transaction_type": self.transaction_type,
            "quantity_requested": self.quantity_requested,
            "quantity_filled": self.quantity_filled,
            "price_type": self.price_type.value,
            "reference_price": self.reference_price,
            "execution_price": self.execution_price,
            "status": self.status.value,
            "slippage_pct": self.actual_slippage_pct,
            "created_at": self.created_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
        }


class OrderManager:
    """Manage order lifecycle and execution."""
    
    def __init__(self):
        """Initialize order manager."""
        self.orders = {}  # order_id -> Order
        self.order_counter = 0
    
    def create_order(self, ticker: str, transaction_type: str, quantity: float,
                    price_type: PriceType, reference_price: float,
                    slippage_tolerance_pct: float = 1.0) -> str:
        """Create a new order.
        
        Args:
            ticker: Stock ticker
            transaction_type: 'BUY' or 'SELL'
            quantity: Quantity to trade
            price_type: Price reference point
            reference_price: Expected execution price
            slippage_tolerance_pct: Maximum acceptable slippage %
            
        Returns:
            Order ID
        """
        self.order_counter += 1
        order_id = f"ORD_{self.order_counter:06d}"
        
        order = Order(order_id, ticker, transaction_type, quantity, price_type,
                     reference_price, slippage_tolerance_pct)
        self.orders[order_id] = order
        
        logger.info(f"Created order {order_id}: {transaction_type} {quantity} {ticker} "
                   f"@ {reference_price} ({price_type.value})")
        return order_id
    
    def execute_order(self, order_id: str, execution_price: float, 
                     quantity_filled: float, available_volume: float) -> bool:
        """Execute an order.
        
        Args:
            order_id: Order ID
            execution_price: Actual execution price
            quantity_filled: Actual quantity filled
            available_volume: Available market volume
            
        Returns:
            True if successfully executed, False if rejected
        """
        if order_id not in self.orders:
            logger.error(f"Order {order_id} not found")
            return False
        
        order = self.orders[order_id]
        return order.execute(execution_price, quantity_filled, available_volume)
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID.
        
        Args:
            order_id: Order ID
            
        Returns:
            Order object or None
        """
        return self.orders.get(order_id)
    
    def get_order_status(self, order_id: str) -> Optional[str]:
        """Get order status.
        
        Args:
            order_id: Order ID
            
        Returns:
            Order status string or None
        """
        order = self.orders.get(order_id)
        return order.status.value if order else None
    
    def get_slippage(self, order_id: str) -> float:
        """Get order slippage %.
        
        Args:
            order_id: Order ID
            
        Returns:
            Slippage percentage
        """
        order = self.orders.get(order_id)
        return order.actual_slippage_pct if order else 0.0
    
    def auto_cancel_expired_orders(self):
        """Auto-cancel all expired pending orders."""
        for order in self.orders.values():
            order.auto_cancel_if_expired()
    
    def get_pending_orders(self) -> list:
        """Get all pending orders."""
        return [order for order in self.orders.values() 
                if order.status == OrderStatus.PENDING]
    
    def get_all_orders_summary(self) -> Dict:
        """Get summary of all orders."""
        summary = {
            "total_orders": len(self.orders),
            "pending": 0,
            "filled": 0,
            "partially_filled": 0,
            "rejected": 0,
        }
        
        for order in self.orders.values():
            if order.status == OrderStatus.PENDING:
                summary["pending"] += 1
            elif order.status == OrderStatus.FILLED:
                summary["filled"] += 1
            elif order.status == OrderStatus.PARTIALLY_FILLED:
                summary["partially_filled"] += 1
            elif order.status == OrderStatus.REJECTED:
                summary["rejected"] += 1
        
        return summary
