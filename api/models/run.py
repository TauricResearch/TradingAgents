from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


class RunConfig(BaseModel):
    ticker: str
    date: str  # "YYYY-MM-DD"
    llm_provider: str = "openai"
    deep_think_llm: str = "gpt-5.2"
    quick_think_llm: str = "gpt-5-mini"
    max_debate_rounds: int = Field(default=1, ge=1, le=5)
    max_risk_discuss_rounds: int = Field(default=1, ge=1, le=5)
    enabled_analysts: list[str] = Field(
        default=["market", "news", "fundamentals", "social"]
    )


class RunSummary(BaseModel):
    id: str
    ticker: str
    date: str
    status: RunStatus
    decision: Optional[Literal["BUY", "SELL", "HOLD"]] = None
    created_at: str


class RunResult(RunSummary):
    config: Optional[RunConfig] = None
    reports: dict[str, str] = {}
    error: Optional[str] = None
