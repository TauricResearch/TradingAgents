"""Request/response schemas for the assistant API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AddTickerRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32, description="Yahoo Finance symbol, e.g. NVDA, RELIANCE.NS, BTC-USD")


class UpdateTickerRequest(BaseModel):
    tier: Literal["daily", "weekly", "paused"] = Field(
        description=(
            "Coverage cadence: daily (every slot), weekly (Monday check-in + "
            "event trigger on big moves), paused (never analyzed)"
        )
    )


class WatchlistItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    market: str
    asset_type: str
    tier: str
    added_by: str
    category: str
    consecutive_holds: int
    last_rating: str | None
    last_run_at: datetime | None
    next_review_at: datetime | None
    note: str | None


class SignalItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    market: str
    trade_date: str
    rating: str | None
    prev_rating: str | None
    changed: bool
    status: str
    error: str | None
    report_path: str | None
    duration_seconds: float | None
    created_at: datetime


class RunTriggeredResponse(BaseModel):
    market: str
    status: str = "started"


class ScheduleSlotItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    run_time: str
    timezone: str
    market: str | None
    enabled: bool
    max_tickers: int


class ScheduleSlotCreate(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    run_time: str = Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
    timezone: str = "America/Chicago"
    market: str | None = Field(default=None, description="us / india / crypto, or null for any")
    enabled: bool = True
    max_tickers: int = Field(default=1, ge=1, le=20)


class ScheduleSlotUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=64)
    run_time: str | None = Field(default=None, pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
    timezone: str | None = None
    market: str | None = Field(
        default=None, description="us / india / crypto, or 'any' to clear the filter"
    )
    enabled: bool | None = None
    max_tickers: int | None = Field(default=None, ge=1, le=20)


class PriceHistory(BaseModel):
    symbol: str
    dates: list[str]
    close: list[float]


class TickerContextResponse(BaseModel):
    symbol: str
    next_earnings_date: str | None
    days_to_earnings: int | None
    eps_estimate_avg: float | None
    revenue_estimate_avg: float | None
    target_mean: float | None
    target_median: float | None
    target_high: float | None
    target_low: float | None
    current_price: float | None
    analyst_upside_pct: float | None


class ReportVersionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trade_date: str
    rating: str | None
    created_at: datetime


class ReportResponse(BaseModel):
    signal_id: int
    symbol: str
    trade_date: str
    rating: str | None
    created_at: datetime
    markdown: str


class PositionItem(BaseModel):
    id: int
    account_type: str
    symbol: str
    market: str
    currency: str
    quantity: float
    avg_price: float
    stop_loss: float | None
    price_target: float | None
    opened_at: datetime
    note: str | None
    # Live valuation (None when a quote is unavailable)
    last_price: float | None
    value_usd: float | None
    pnl_usd: float | None
    pnl_pct: float | None


class BookSummary(BaseModel):
    label: str                      # strategic | tactical
    starting_cash_usd: float
    cash_usd: float
    equity_usd: float | None
    return_pct: float | None
    positions: list[PositionItem]
    enabled: bool = True            # tactical shows False until a rule is set
    # Deployment is the metric that actually explained the Jul-Aug 2026
    # underperformance: both books held decent positions and still trailed SPY
    # because most of the capital sat in cash earning nothing.
    invested_pct: float | None = None
    core_value_usd: float | None = None
    realised_pnl_usd: float = 0.0   # closed trades — hidden by a positions-only view
    closed_trades: int = 0
    winning_trades: int = 0


class EquityPoint(BaseModel):
    date: str
    equity_usd: float


class PortfolioResponse(BaseModel):
    books: list[BookSummary]
    real_positions: list[PositionItem]
    benchmark_return_pct: float | None  # SPY since the books opened
    tactical_rule: str                  # "" = disabled (backtest gate not passed)
    core_etf: str = "SPY"
    core_enabled: bool = True
    core_trend_filter: bool = False     # crash insurance; costs ~3-5pp/yr when on
    core_defensive: bool = False        # True when the filter has moved to cash
    # Backward-compat mirrors of the strategic book (dashboard v1 fields)
    cash_usd: float
    starting_cash_usd: float
    equity_usd: float | None
    return_pct: float | None
    paper_positions: list[PositionItem]


class AddHoldingRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    quantity: float = Field(gt=0)
    price: float = Field(gt=0, description="Average buy price in the instrument's own currency")
    bought_at: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD"
    )
    stop_loss: float | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=200)


class TradeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_type: str
    symbol: str
    side: str
    quantity: float
    price: float
    currency: str
    reason: str
    realized_pnl_usd: float | None
    executed_at: datetime


class ScreenerResultItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_date: str
    symbol: str
    market: str
    score: float
    summary: str
    added: bool
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    scheduler_running: bool
    jobs: list[dict]
    telegram_configured: bool
    email_configured: bool
    llm_provider: str
    deep_model: str
    quick_model: str
    runs_today: int
    daily_run_budget: int
    runs_this_week: int
    weekly_run_budget: int
    analyzing: dict | None = None  # {symbol, label, started_at} while a deep run is live
