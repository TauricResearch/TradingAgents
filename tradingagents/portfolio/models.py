"""Data models for portfolio position tracking."""

from typing import List
from pydantic import BaseModel, Field


class PositionRecord(BaseModel):
    """A single position (holding) in the portfolio."""
    ticker: str = Field(..., description="Stock ticker symbol (e.g., NVDA, 000404.SH)")
    entry_date: str = Field(..., description="Entry date in YYYY-MM-DD format")
    entry_price: float = Field(..., gt=0, description="Average entry price")
    quantity: float = Field(..., gt=0, description="Number of shares held")
    side: str = Field(default="long", description="Position side: long or short")
    note: str = Field(default="", description="Optional note about the position")


class Transaction(BaseModel):
    """A single buy/sell transaction record."""
    ticker: str = Field(..., description="Stock ticker symbol")
    action: str = Field(..., description="Transaction action: buy or sell")
    date: str = Field(..., description="Transaction date in YYYY-MM-DD format")
    price: float = Field(..., gt=0, description="Execution price")
    quantity: float = Field(..., gt=0, description="Number of shares")
    note: str = Field(default="", description="Optional note about the transaction")


class Portfolio(BaseModel):
    """Complete portfolio state with positions and transaction history."""
    positions: List[PositionRecord] = Field(default_factory=list)
    transactions: List[Transaction] = Field(default_factory=list)
    updated_at: str = Field(default="", description="Last update timestamp")
