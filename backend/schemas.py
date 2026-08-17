from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ResearchDepth = Literal["shallow", "medium", "deep"]
AnalysisStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str

    model_config = {"from_attributes": True}


class AnalysisCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    analysis_date: str | None = None
    research_depth: ResearchDepth = "medium"
    llm_provider: str | None = None
    model: str | None = None
    quick_model: str | None = None
    selected_analysts: list[str] = Field(
        default_factory=lambda: ["market", "social", "news", "fundamentals"]
    )
    temperature: float | None = None
    debate_rounds: int | None = Field(default=None, ge=1, le=5)


class AnalysisOut(BaseModel):
    analysis_id: str
    status: str
    symbol: str
    exchange: str
    analysis_date: str
    provider: str
    model: str
    research_depth: str
    selected_analysts: list[str]
    final_decision: str | None = None
    confidence: float | None = None
    risk_level: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    agents: list["AgentResultOut"] = Field(default_factory=list)
    decision: "DecisionOut | None" = None
    payload: dict[str, Any] | None = None


class AnalysisQueued(BaseModel):
    analysis_id: str
    status: str = "queued"


class AgentResultOut(BaseModel):
    agent_name: str
    status: str
    summary: str | None = None
    structured_output: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class DecisionOut(BaseModel):
    action: str
    confidence: float | None = None
    risk_level: str | None = None
    reason: str | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    price_target: float | None = None
    time_horizon: str | None = None
    in_plain_language: str | None = None

    model_config = {"from_attributes": True}


class StockQuote(BaseModel):
    symbol: str
    name: str
    exchange: str
    currency: str = "INR"
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    previous_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    market_cap: float | None = None
    sector: str | None = None


class Candle(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class WatchlistCreate(BaseModel):
    symbol: str


class WatchlistOut(BaseModel):
    id: str
    symbol: str
    quote: StockQuote | None = None
    last_analysis: AnalysisOut | None = None


class SettingsIn(BaseModel):
    llm_provider: str | None = None
    model: str | None = None
    quick_model: str | None = None
    temperature: float | None = None
    research_depth: ResearchDepth | None = None
    debate_rounds: int | None = None
    enable_sentiment: bool = True
    enable_news: bool = True
    enable_fundamentals: bool = True
    enable_technical: bool = True
    market_data_provider: str = "yahoo"
    refresh_interval_seconds: int = 60
    output_language: str = "English"


class BacktestCreate(BaseModel):
    universe: str = "NIFTY50"
    start_date: str
    end_date: str
    research_depth: ResearchDepth = "medium"
    holding_days: int = 5


class EventMessage(BaseModel):
    type: str
    analysis_id: str
    agent_name: str | None = None
    status: str | None = None
    summary: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: datetime


TokenResponse.model_rebuild()
AnalysisOut.model_rebuild()
