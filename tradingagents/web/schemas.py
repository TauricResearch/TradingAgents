from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SYMBOL_RE = re.compile(r"^[A-Za-z0-9._^=\-]{1,32}$")


class ResolveRequest(BaseModel):
    symbol: str
    asset_type: Literal["auto", "stock", "fund", "crypto"] = "auto"

    @field_validator("symbol")
    @classmethod
    def valid_symbol(cls, value: str) -> str:
        value = value.strip()
        if not SYMBOL_RE.fullmatch(value):
            raise ValueError("Invalid symbol")
        return value


class AnalysisCreate(ResolveRequest):
    analysis_date: date
    benchmark_symbol: str = "SPY"
    analysts: list[Literal["market", "social", "news", "fundamentals"]] = Field(min_length=1)
    research_depth: int = Field(default=1, ge=1, le=5)
    llm_provider: str = "openai"
    quick_model: str = "gpt-5.4-mini"
    deep_model: str = "gpt-5.5"
    output_language: str = "English"

    @field_validator("analysis_date")
    @classmethod
    def not_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Analysis date cannot be in the future")
        return value

    @field_validator("benchmark_symbol")
    @classmethod
    def valid_benchmark(cls, value: str) -> str:
        if not SYMBOL_RE.fullmatch(value.strip()):
            raise ValueError("Invalid benchmark symbol")
        return value.strip().upper()


class ConversationMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    refresh_data: bool = False
    candidate_adjustment: bool = False


class ReevaluateCreate(BaseModel):
    trigger_message_ids: list[str] = Field(min_length=1, max_length=100)


class RestoreRequest(BaseModel):
    backup_id: str = Field(pattern=r"^[0-9a-f-]{36}$")


class ChinaFundResolveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=120)


class ChinaFundEvaluateRequest(BaseModel):
    intended_action: Literal["subscribe", "hold", "redeem_partial", "redeem_all", "convert"] = (
        "hold"
    )
    analysis_date: date | None = None
    amount: str | None = Field(default=None, max_length=40)
    unit_fraction: str | None = Field(default=None, max_length=40)
    confirmed_units: str | None = Field(default=None, max_length=40)
    holding_days: int | None = Field(default=None, ge=0, le=100_000)
    minimum_holding_known: bool = False
    sales_platform: str | None = Field(default=None, max_length=120)
    conversion_supported: bool = False
    target_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class ChinaFundConversionRequest(BaseModel):
    target_code: str = Field(pattern=r"^\d{6}$")
    sales_platform: str = Field(min_length=1, max_length=120)
    conversion_supported: bool = False
    confirmed_units: str | None = Field(default=None, max_length=40)
    holding_days: int | None = Field(default=None, ge=0, le=100_000)
    minimum_holding_known: bool = False
