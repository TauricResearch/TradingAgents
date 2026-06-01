from datetime import datetime
from pydantic import BaseModel, Field


class SettingsRead(BaseModel):
    trading_mode: str
    active_broker: str
    active_data_vendor: str
    cron_enabled: bool
    cron_schedule: str
    price_tolerance_pct: float
    watchlist: list[str]
    selected_analysts: list[str]
    llm_provider: str
    deep_think_llm: str
    quick_think_llm: str
    backend_url: str | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    google_thinking_level: str | None = None
    output_language: str = "English"
    analyst_concurrency_limit: int = 1
    max_debate_rounds: int
    max_risk_rounds: int
    max_position_size_pct: float
    max_risk_per_trade_pct: float
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    trading_mode: str | None = None
    active_broker: str | None = None
    active_data_vendor: str | None = None
    cron_enabled: bool | None = None
    cron_schedule: str | None = None
    price_tolerance_pct: float | None = Field(default=None, ge=0, le=50)
    watchlist: list[str] | None = None
    selected_analysts: list[str] | None = None
    llm_provider: str | None = None
    deep_think_llm: str | None = None
    quick_think_llm: str | None = None
    backend_url: str | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    google_thinking_level: str | None = None
    output_language: str | None = None
    analyst_concurrency_limit: int | None = Field(default=None, ge=1, le=16)
    max_debate_rounds: int | None = Field(default=None, ge=1, le=10)
    max_risk_rounds: int | None = Field(default=None, ge=1, le=10)
    max_position_size_pct: float | None = Field(default=None, ge=1, le=100)
    max_risk_per_trade_pct: float | None = Field(default=None, ge=0.1, le=50)
