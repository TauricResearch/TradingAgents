"""
Pydantic schemas for request / response bodies.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol, e.g. NVDA")
    date: Optional[str] = Field(
        None,
        description="Analysis date YYYY-MM-DD. Defaults to today if omitted.",
    )
    llm_provider: Optional[str] = Field(
        None,
        description="LLM provider to use for this request. Defaults to ollama. Supported: ollama, google, openrouter.",
    )


class SubmitResponse(BaseModel):
    request_id: str
    ticker: str
    analysis_date: str
    llm_provider: str
    status: str
    submitted_at: str


class RequestStatus(BaseModel):
    request_id: str
    ticker: str
    analysis_date: str
    llm_provider: Optional[str] = None
    deep_model: Optional[str] = None
    quick_model: Optional[str] = None
    status: str
    submitted_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    recommendation: Optional[str] = None
    llm_calls: Optional[int] = None
    tool_calls: Optional[int] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    agent_recommendations: Optional[dict] = None
    analysis_url: Optional[str] = None
    debug_log_url: Optional[str] = None
    error_message: Optional[str] = None


class RequestListResponse(BaseModel):
    total: int
    requests: list[RequestStatus]


class CancelResponse(BaseModel):
    request_id: str
    status: str
    canceled_at: str


class CancelAllResponse(BaseModel):
    canceled_count: int
    canceled_at: str


class BatchScheduleCreateRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol, e.g. NVDA")
    llm_provider: str = Field(..., description="Provider for scheduled runs: ollama, google, or openrouter")
    frequency: str = Field(..., description="Run frequency: daily, weekly, or monthly")


class BatchScheduleRerunRequest(BaseModel):
    llm_provider: str = Field(..., description="Provider to use for this rerun: ollama, google, or openrouter")


class BatchScheduleUpdateRequest(BaseModel):
    llm_provider: str = Field(..., description="Updated provider for future scheduled runs")
    frequency: str = Field(..., description="Updated frequency for future scheduled runs: daily, weekly, or monthly")


class BatchScheduleItem(BaseModel):
    id: str
    ticker: str
    llm_provider: str
    frequency: str
    next_run_at: Optional[str] = None
    last_schedule_run_at: Optional[str] = None
    latest_recommendation: Optional[str] = None
    last_run_at: Optional[str] = None
    latest_logs_url: Optional[str] = None
    latest_analysis_url: Optional[str] = None


class BatchScheduleListResponse(BaseModel):
    total: int
    schedules: list[BatchScheduleItem]


class EnvVarUpdateRequest(BaseModel):
    value: str = Field(..., description="New env variable value")


class EnvVarValueResponse(BaseModel):
    name: str
    value: Optional[str] = None
    exists: bool


class VaultRefreshResponse(BaseModel):
    enabled: bool
    updated: int
    keys: list[str]
    skipped: list[str]
    message: str


class LatestRecommendationResponse(BaseModel):
    ticker: str
    provider: Optional[str] = None
    available: bool
    latest: Optional[dict] = None
