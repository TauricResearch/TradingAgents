"""Data models for portfolio state persistence."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TradeRecord:
    """
    A single executed trade, persisted to the database.

    Captures both the agent's reasoning and the broker's execution
    so every trade is fully auditable.
    """
    ticker: str
    side: str                      # "buy" or "sell"
    qty: float
    price: float
    total_value: float             # qty * price
    signal: str                    # "BUY" / "OVERWEIGHT" / etc.
    agent_reasoning: str           # full final_trade_decision text
    order_id: str
    trade_date: str                # ISO date string (YYYY-MM-DD)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    id: Optional[int] = None       # set by DB after insert

    @property
    def is_buy(self) -> bool:
        return self.side.lower() == "buy"

    @property
    def is_sell(self) -> bool:
        return self.side.lower() == "sell"


@dataclass
class PortfolioSnapshot:
    """
    End-of-day portfolio value snapshot.
    Used to plot the equity curve and calculate drawdowns.
    """
    snapshot_date: str             # ISO date string
    cash: float
    invested_value: float
    total_value: float
    daily_pnl: float               # absolute change from previous snapshot
    daily_pnl_pct: float           # percentage change
    open_positions: int            # number of tickers held
    timestamp: datetime = field(default_factory=datetime.utcnow)
    id: Optional[int] = None


@dataclass
class PerformanceMetrics:
    """Computed performance statistics over the portfolio history."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float                # fraction 0–1
    total_realized_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float           # gross_profit / gross_loss
    sharpe_ratio: float            # annualised, assumes 252 trading days
    max_drawdown: float            # peak-to-trough as a positive fraction
    current_equity: float
    starting_equity: float
    total_return_pct: float        # (current - starting) / starting
