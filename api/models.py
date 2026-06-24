import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EntitlementBlock(BaseModel):
    tier: str
    remaining_views: int
    reset_at: Optional[datetime.datetime] = None
    locked: bool
    cooldown_ends_at: Optional[datetime.datetime] = None


class SignalPayload(BaseModel):
    id: str
    ticker: str
    asset_type: str
    name: Optional[str] = None
    signal_type: str
    confidence: float
    time_horizon: Optional[str] = None
    price_target: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    position_sizing: Optional[str] = None
    reasoning_summary: str
    generated_at: datetime.datetime
    source_run_id: Optional[str] = None
    grade: Optional[str] = None
    rr: Optional[float] = None
    agent_votes: Optional[Dict[str, Any]] = None
    sentiment_score: Optional[float] = None
    sentiment_band: Optional[str] = None
    # Raw agent reports (Pro only — masked for free tier)
    market_report: Optional[str] = None
    news_report: Optional[str] = None
    fundamentals_report: Optional[str] = None
    sentiment_report: Optional[str] = None
    pm_report: Optional[str] = None
    trader_report: Optional[str] = None
    investment_debate: Optional[str] = None
    risk_debate: Optional[str] = None


class SignalsResponse(BaseModel):
    signals: List[SignalPayload]
    entitlement: EntitlementBlock


class StatsResponse(BaseModel):
    signals_today: int
    buy_signals: int
    sell_signals: int
    hold_signals: int
    avg_confidence: float
    active_watchlist: int
    win_rate_30d: Optional[float] = None


class TickerStats(BaseModel):
    ticker: str
    asset_type: str
    added_at: datetime.datetime
    signals_count: int
    last_signal_at: Optional[datetime.datetime] = None


class TickersResponse(BaseModel):
    tickers: List[TickerStats]
    entitlement: EntitlementBlock


class WatchlistAddPayload(BaseModel):
    ticker: str = Field(..., description="Ticker symbol (e.g. MSFT, BTC)")
    asset_type: str = Field("stocks", description="'stocks' or 'crypto'")


class UserWatchlistPayload(BaseModel):
    ticker: str
    asset_type: str = "stocks"
