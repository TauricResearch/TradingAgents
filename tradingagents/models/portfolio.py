from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field

from .trading import Fill, OrderSide, Position


class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    FEE = "fee"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"


class CashTransaction(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    transaction_type: TransactionType
    amount: Decimal
    timestamp: datetime = Field(default_factory=datetime.now)
    description: str | None = None
    reference_id: UUID | None = None


class PortfolioConfig(BaseModel):
    initial_cash: Decimal = Field(default=Decimal("100000"), gt=0)
    commission_per_share: Decimal = Field(default=Decimal("0"), ge=0)
    commission_per_trade: Decimal = Field(default=Decimal("0"), ge=0)
    commission_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    min_commission: Decimal = Field(default=Decimal("0"), ge=0)
    max_commission: Decimal | None = Field(default=None, ge=0)
    slippage_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    margin_enabled: bool = Field(default=False)
    margin_rate: Decimal = Field(default=Decimal("0.05"), ge=0)
    max_position_size_percent: Decimal = Field(default=Decimal("100"), gt=0, le=100)
    allow_fractional_shares: bool = Field(default=False)

    def calculate_commission(self, quantity: int, price: Decimal) -> Decimal:
        trade_value = quantity * price
        commission = Decimal("0")

        commission += self.commission_per_trade
        commission += self.commission_per_share * quantity
        commission += trade_value * (self.commission_percent / 100)

        if commission < self.min_commission:
            commission = self.min_commission
        if self.max_commission and commission > self.max_commission:
            commission = self.max_commission

        return commission

    def calculate_slippage(self, price: Decimal, side: OrderSide) -> Decimal:
        slippage = price * (self.slippage_percent / 100)
        if side == OrderSide.BUY:
            return price + slippage
        return price - slippage


class PortfolioSnapshot(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    cash: Decimal = Field(default=Decimal("0"))
    positions: dict[str, Position] = Field(default_factory=dict)
    pending_orders: int = Field(default=0, ge=0)
    total_commission_paid: Decimal = Field(default=Decimal("0"), ge=0)
    total_realized_pnl: Decimal = Field(default=Decimal("0"))
    cash_transactions: list[CashTransaction] = Field(default_factory=list)

    @computed_field
    @property
    def position_count(self) -> int:
        return len([p for p in self.positions.values() if p.quantity != 0])

    def positions_value(self, prices: dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        for ticker, position in self.positions.items():
            if ticker in prices and position.quantity != 0:
                total += position.market_value(prices[ticker])
        return total

    def total_equity(self, prices: dict[str, Decimal]) -> Decimal:
        return self.cash + self.positions_value(prices)

    def total_unrealized_pnl(self, prices: dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        for ticker, position in self.positions.items():
            if ticker in prices:
                total += position.unrealized_pnl(prices[ticker])
        return total

    def get_position(self, ticker: str) -> Position:
        if ticker not in self.positions:
            self.positions[ticker] = Position(ticker=ticker)
        return self.positions[ticker]

    def apply_fill(self, fill: Fill) -> None:
        position = self.get_position(fill.ticker)
        old_realized = position.realized_pnl

        position.update_from_fill(fill)

        pnl_change = position.realized_pnl - old_realized
        self.total_realized_pnl += pnl_change
        self.total_commission_paid += fill.commission

        if fill.side == OrderSide.BUY:
            self.cash -= fill.total_cost
        else:
            self.cash += fill.total_value - fill.commission

    def add_cash_transaction(self, transaction: CashTransaction) -> None:
        self.cash_transactions.append(transaction)
        if transaction.transaction_type in (
            TransactionType.DEPOSIT,
            TransactionType.DIVIDEND,
            TransactionType.INTEREST,
            TransactionType.TRANSFER_IN,
        ):
            self.cash += transaction.amount
        else:
            self.cash -= abs(transaction.amount)

    def can_afford(
        self, ticker: str, quantity: int, price: Decimal, config: PortfolioConfig
    ) -> bool:
        execution_price = config.calculate_slippage(price, OrderSide.BUY)
        commission = config.calculate_commission(quantity, execution_price)
        total_cost = (quantity * execution_price) + commission
        return self.cash >= total_cost

    def max_shares_affordable(
        self, ticker: str, price: Decimal, config: PortfolioConfig
    ) -> int:
        if price <= 0:
            return 0

        execution_price = config.calculate_slippage(price, OrderSide.BUY)
        available = self.cash

        low, high = 0, int(available / execution_price) + 1
        result = 0

        while low <= high:
            mid = (low + high) // 2
            commission = config.calculate_commission(mid, execution_price)
            total_cost = (mid * execution_price) + commission

            if total_cost <= available:
                result = mid
                low = mid + 1
            else:
                high = mid - 1

        return result

    def to_dict(self, prices: dict[str, Decimal]) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "cash": float(self.cash),
            "positions_value": float(self.positions_value(prices)),
            "total_equity": float(self.total_equity(prices)),
            "position_count": self.position_count,
            "total_realized_pnl": float(self.total_realized_pnl),
            "total_unrealized_pnl": float(self.total_unrealized_pnl(prices)),
            "total_commission_paid": float(self.total_commission_paid),
        }
