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
    llm_provider: str | None = Field("openai", description="LLM provider name")
    deep_think_llm: str | None = Field("gpt-5.6", description="Model for deep reasoning")
    quick_think_llm: str | None = Field("gpt-5.6-luna", description="Model for fast steps")
    max_debate_rounds: int | None = Field(1, ge=1, le=5, description="Number of bull/bear debate rounds")
    max_risk_discuss_rounds: int | None = Field(1, ge=1, le=5, description="Number of risk debate rounds")
    output_language: str | None = Field("English", description="Target language for the reports")

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

