from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from cli.models import AnalystType


class AnalysisRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    analysis_date: str
    output_language: str = "English"
    analysts: list[AnalystType] = Field(min_length=1)
    research_depth: int = Field(ge=1, le=5)
    llm_provider: str
    backend_url: str | None = None
    quick_think_llm: str
    deep_think_llm: str
    google_thinking_level: str | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    checkpoint_enabled: bool = False

    @field_validator("analysis_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        import datetime
        import re

        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("analysis_date must use YYYY-MM-DD format")
        datetime.datetime.strptime(value, "%Y-%m-%d")
        return value

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be empty")
        return normalized


class StreamEvent(BaseModel):
    type: Literal[
        "run_started",
        "agent_status",
        "message",
        "tool_call",
        "report_section",
        "stats",
        "run_completed",
        "run_failed",
    ]
    payload: dict[str, Any]
