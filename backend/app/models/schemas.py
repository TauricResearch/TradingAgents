from typing import Any

from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    ticker: str = Field(..., description="Ticker symbol, e.g. AAPL, NVDA, BTC-USD")
    trade_date: str | None = Field(None, description="Analysis date (YYYY-MM-DD). Defaults to today.")
    asset_type: str | None = Field("stock", description="Asset type: stock or crypto")
    analysts: list[str] | None = Field(
        default=["market", "social", "news", "fundamentals"],
        description="List of selected analysts: market, social, news, fundamentals"
    )
    llm_provider: str | None = Field(None, description="LLM provider name")
    deep_think_llm: str | None = Field(None, description="Model for deep reasoning")
    quick_think_llm: str | None = Field(None, description="Model for fast steps")
    max_debate_rounds: int | None = Field(None, ge=1, le=5, description="Number of bull/bear debate rounds")
    max_risk_discuss_rounds: int | None = Field(None, ge=1, le=5, description="Number of risk debate rounds")
    max_tool_rounds: int | None = Field(None, ge=1, le=50, description="Max tool call rounds per analyst")
    holding_period_days: int | None = Field(None, ge=1, le=60, description="Holding period days for reflection")
    output_language: str | None = Field(None, description="Target language for the reports")

class JobResponse(BaseModel):
    id: str
    ticker: str
    trade_date: str
    asset_type: str
    analysts: list[str]
    llm_provider: str
    deep_think_llm: str
    quick_think_llm: str
    max_debate_rounds: int
    max_risk_discuss_rounds: int
    output_language: str
    status: str
    progress: int
    current_stage: str
    decision_signal: str | None = None
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None

class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int

class JobEventItem(BaseModel):
    id: int
    job_id: str
    timestamp: str
    event_type: str
    data: dict[str, Any]

class JobReportResponse(BaseModel):
    job_id: str
    ticker: str
    trade_date: str
    recommendation: str | None = None
    executive_summary: str | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    target_price: float | None = None
    complete_report_md: str | None = None
    market_report_md: str | None = None
    sentiment_report_md: str | None = None
    news_report_md: str | None = None
    fundamentals_report_md: str | None = None
    investment_debate: dict[str, Any] | None = None
    risk_debate: dict[str, Any] | None = None
    trader_investment_plan: str | None = None

class ConfigOptionsResponse(BaseModel):
    providers: list[dict[str, Any]]
    models: dict[str, Any]
    analysts: list[dict[str, str]]
    languages: list[str]
    default_config: dict[str, Any]

class APIKeyInfo(BaseModel):
    provider: str
    env_var: str
    category: str = "llm"  # "llm" or "data"
    configured: bool
    preview: str

class APIKeysStatusResponse(BaseModel):
    keys: list[APIKeyInfo]

class APIKeysUpdateRequest(BaseModel):
    keys: dict[str, str] = Field(..., description="Mapping of provider/feed key to new secret string")

class BatchDeleteRequest(BaseModel):
    job_ids: list[str] = Field(..., description="List of job IDs to delete")
    force: bool = Field(False, description="Whether to force cancel and delete active jobs")

class BatchDeleteResponse(BaseModel):
    message: str
    deleted_count: int
    job_ids: list[str]

class DeleteJobResponse(BaseModel):
    message: str
    job_id: str

class ClearJobsResponse(BaseModel):
    message: str
    deleted_count: int


# Concurrency & Worker Management Schemas
class ConcurrencyConfigResponse(BaseModel):
    max_concurrent_jobs: int = Field(..., description="Maximum concurrent worker jobs permitted")
    active_running_jobs: int = Field(..., description="Currently active running worker jobs")
    recommended_min: int = Field(1, description="Minimum recommended concurrent jobs")
    recommended_max: int = Field(16, description="Maximum recommended concurrent jobs for single VPS")


class ConcurrencyUpdateRequest(BaseModel):
    max_concurrent_jobs: int = Field(
        ...,
        ge=1,
        le=32,
        description="Updated maximum concurrent worker jobs (bounded 1 to 32)",
    )


# Authentication & Security Schemas
class UserProfile(BaseModel):
    id: str
    username: str
    must_change_password: bool
    created_at: str
    last_login_at: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class LoginResponse(BaseModel):
    success: bool
    user: UserProfile
    must_change_password: bool
    session_token: str | None = None
    message: str = "Login successful"


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=6, description="New password (minimum 6 characters)")


class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: UserProfile | None = None
    must_change_password: bool = False

