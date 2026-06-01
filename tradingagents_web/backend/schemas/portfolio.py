from datetime import datetime
from pydantic import BaseModel


class HoldingRead(BaseModel):
    id: int
    ticker: str
    quantity: float
    avg_buy_price: float
    current_price: float
    unrealized_pnl: float
    updated_at: datetime

    class Config:
        from_attributes = True


class PortfolioRead(BaseModel):
    id: int
    mode: str
    broker: str
    initial_capital: float
    current_balance: float
    cash_available: float
    status: str
    holdings: list[HoldingRead]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrderRead(BaseModel):
    id: int
    portfolio_id: int
    mode: str
    broker: str
    ticker: str
    action: str
    quantity_requested: float
    quantity_filled: float
    status: str
    price_per_share: float | None
    total_value: float | None
    commission: float
    analysis_id: int | None
    ai_signal: str
    created_at: datetime
    executed_at: datetime | None

    class Config:
        from_attributes = True
