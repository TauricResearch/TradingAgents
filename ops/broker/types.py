from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class Order:
    client_order_id: str
    symbol: str
    side: Side
    notional_dollars: Decimal
    order_type: OrderType
    limit_price: Decimal | None = None
    stop_loss_price: Decimal | None = None

    def __post_init__(self) -> None:
        if self.notional_dollars < 0:
            raise ValueError("notional_dollars cannot be negative")
        if self.side == Side.BUY and self.notional_dollars <= 0:
            raise ValueError("BUY order requires positive notional_dollars")
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT order requires limit_price")


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    stop_loss_price: Decimal | None = None

    def market_value(self, current_price: Decimal) -> Decimal:
        return self.quantity * current_price

    def unrealized_pct(self, current_price: Decimal) -> Decimal:
        return (current_price - self.avg_entry_price) / self.avg_entry_price


@dataclass(frozen=True)
class Fill:
    order_id: str
    client_order_id: str
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    filled_at: datetime
