from __future__ import annotations

from datetime import date
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


AnalystKey = Literal["market", "social", "news", "fundamentals"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AuthStatus(BaseModel):
    auth_enabled: bool = True
    logged_in: bool = False
    username: Optional[str] = None


class ApiKeyPayload(BaseModel):
    provider: str
    value: str = ""

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.strip().lower()


class SettingsPayload(BaseModel):
    llm_provider: str = "openai"
    deep_think_llm: str = "gpt-5.4"
    quick_think_llm: str = "gpt-5.4-mini"
    backend_url: Optional[str] = None
    google_thinking_level: Optional[str] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None
    output_language: str = "Chinese"
    max_debate_rounds: int = Field(default=1, ge=1, le=5)
    max_risk_discuss_rounds: int = Field(default=1, ge=1, le=5)
    checkpoint_enabled: bool = False
    data_vendors: Dict[str, str] = Field(
        default_factory=lambda: {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
            "fundamental_data": "yfinance",
            "news_data": "yfinance",
        }
    )

    @field_validator("llm_provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("backend_url")
    @classmethod
    def normalize_backend_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class AnalysisRequest(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    analysis_date: str = Field(default_factory=lambda: date.today().isoformat())
    analysts: List[AnalystKey] = Field(default_factory=lambda: ["market", "news", "fundamentals"])
    research_depth: int = Field(default=1, ge=1, le=5)
    output_language: str = "Chinese"
    checkpoint_enabled: bool = False
    use_mock_stream: bool = False

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        raw = value.strip().upper()
        for suffix in (".SS", ".SZ", ".SH", ".HK"):
            if raw.endswith(suffix):
                raw = raw[: -len(suffix)]
                break
        cleaned = "".join(character for character in raw if character.isalnum())
        if not cleaned:
            raise ValueError("ticker is required")
        return cleaned


class RunSummary(BaseModel):
    id: str
    ticker: str
    company_name: Optional[str] = None
    analysis_date: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    created_at: str
    updated_at: str
    decision: Optional[str] = None
    title: str
