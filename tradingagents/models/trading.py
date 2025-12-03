from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class Order(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    ticker: str = Field(min_length=1, max_length=10)
    side: OrderSide
    order_type: OrderType = Field(default=OrderType.MARKET)
    quantity: int = Field(gt=0)
    limit_price: Optional[Decimal] = Field(default=None, gt=0)
    stop_price: Optional[Decimal] = Field(default=None, gt=0)
    status: OrderStatus = Field(default=OrderStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.now)
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    filled_quantity: int = Field(default=0, ge=0)
    filled_avg_price: Optional[Decimal] = None
    commission: Decimal = Field(default=Decimal("0"))
    notes: Optional[str] = None

    @computed_field
    @property
    def remaining_quantity(self) -> int:
        return self.quantity - self.filled_quantity

    @computed_field
    @property
    def is_complete(self) -> bool:
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )


class Fill(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    ticker: str
    side: OrderSide
    quantity: int = Field(gt=0)
    price: Decimal = Field(gt=0)
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    timestamp: datetime = Field(default_factory=datetime.now)

    @computed_field
    @property
    def total_value(self) -> Decimal:
        return self.price * self.quantity

    @computed_field
    @property
    def total_cost(self) -> Decimal:
        if self.side == OrderSide.BUY:
            return self.total_value + self.commission
        return self.total_value - self.commission


class Position(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    quantity: int = Field(default=0)
    avg_cost: Decimal = Field(default=Decimal("0"), ge=0)
    realized_pnl: Decimal = Field(default=Decimal("0"))
    opened_at: Optional[datetime] = None
    last_updated: datetime = Field(default_factory=datetime.now)

    @computed_field
    @property
    def side(self) -> PositionSide:
        if self.quantity > 0:
            return PositionSide.LONG
        elif self.quantity < 0:
            return PositionSide.SHORT
        return PositionSide.FLAT

    @computed_field
    @property
    def cost_basis(self) -> Decimal:
        return abs(self.quantity) * self.avg_cost

    def unrealized_pnl(self, current_price: Decimal) -> Decimal:
        if self.quantity == 0:
            return Decimal("0")
        market_value = self.quantity * current_price
        return market_value - (self.quantity * self.avg_cost)

    def market_value(self, current_price: Decimal) -> Decimal:
        return abs(self.quantity) * current_price

    def update_from_fill(self, fill: Fill) -> None:
        if fill.side == OrderSide.BUY:
            if self.quantity >= 0:
                total_cost = (self.quantity * self.avg_cost) + fill.total_value
                self.quantity += fill.quantity
                self.avg_cost = total_cost / self.quantity if self.quantity else Decimal("0")
            else:
                close_qty = min(fill.quantity, abs(self.quantity))
                pnl = close_qty * (self.avg_cost - fill.price)
                self.realized_pnl += pnl
                self.quantity += fill.quantity
                if self.quantity > 0:
                    self.avg_cost = fill.price
        else:
            if self.quantity <= 0:
                total_cost = (abs(self.quantity) * self.avg_cost) + fill.total_value
                self.quantity -= fill.quantity
                self.avg_cost = total_cost / abs(self.quantity) if self.quantity else Decimal("0")
            else:
                close_qty = min(fill.quantity, self.quantity)
                pnl = close_qty * (fill.price - self.avg_cost)
                self.realized_pnl += pnl
                self.quantity -= fill.quantity
                if self.quantity < 0:
                    self.avg_cost = fill.price

        if self.quantity != 0 and self.opened_at is None:
            self.opened_at = fill.timestamp
        elif self.quantity == 0:
            self.opened_at = None

        self.last_updated = fill.timestamp


class Trade(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    ticker: str
    side: OrderSide
    entry_price: Decimal = Field(gt=0)
    entry_quantity: int = Field(gt=0)
    entry_time: datetime
    exit_price: Optional[Decimal] = Field(default=None, gt=0)
    exit_quantity: Optional[int] = Field(default=None, gt=0)
    exit_time: Optional[datetime] = None
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    entry_order_id: Optional[UUID] = None
    exit_order_id: Optional[UUID] = None
    notes: Optional[str] = None
    tags: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def is_closed(self) -> bool:
        return self.exit_price is not None and self.exit_quantity is not None

    @computed_field
    @property
    def pnl(self) -> Optional[Decimal]:
        if not self.is_closed:
            return None
        if self.side == OrderSide.BUY:
            return (self.exit_price - self.entry_price) * self.exit_quantity - self.commission
        return (self.entry_price - self.exit_price) * self.exit_quantity - self.commission

    @computed_field
    @property
    def pnl_percent(self) -> Optional[Decimal]:
        if not self.is_closed or self.entry_price == 0:
            return None
        return (self.pnl / (self.entry_price * self.entry_quantity)) * 100

    @computed_field
    @property
    def holding_period(self) -> Optional[int]:
        if not self.exit_time:
            return None
        return (self.exit_time - self.entry_time).days
