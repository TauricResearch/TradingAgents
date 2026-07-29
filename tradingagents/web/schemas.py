"""HTTP-only schemas for the localhost TradingAgents service boundary."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tradingagents.execution.models import ANALYST_WIRE_KEYS


SUPPORTED_OUTPUT_LANGUAGES = (
    "English",
    "Chinese",
)
RESEARCH_DEPTHS = (1, 3, 5)
TICKER_PATTERN = re.compile(r"^[A-Za-z0-9._\-^=]{1,32}$")


class RunCreateRequest(BaseModel):
    """Validated browser input before any background worker is created."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ticker: str = Field(min_length=1, max_length=32)
    analysis_date: str
    selected_analysts: tuple[str, ...] = ANALYST_WIRE_KEYS
    research_depth: Literal[1, 3, 5] = 1
    llm_provider: str = Field(min_length=1, max_length=64)
    quick_think_llm: str = Field(min_length=1, max_length=256)
    deep_think_llm: str = Field(min_length=1, max_length=256)
    output_language: str = "English"
    checkpoint_enabled: bool = False
    asset_type: Literal["stock", "crypto"] | None = None

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        if not TICKER_PATTERN.fullmatch(value) or not any(
            character.isalnum() for character in value
        ):
            raise ValueError("ticker contains unsupported characters")
        return value

    @field_validator("analysis_date")
    @classmethod
    def validate_analysis_date(cls, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("analysis_date must use YYYY-MM-DD") from exc
        if parsed > date.today():
            raise ValueError("analysis_date cannot be in the future")
        return value

    @field_validator("selected_analysts")
    @classmethod
    def validate_analysts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("at least one analyst is required")
        unknown = sorted(set(value) - set(ANALYST_WIRE_KEYS))
        if unknown:
            raise ValueError(f"unknown analyst keys: {', '.join(unknown)}")
        if len(value) != len(set(value)):
            raise ValueError("selected_analysts must not contain duplicates")
        selected = set(value)
        return tuple(key for key in ANALYST_WIRE_KEYS if key in selected)

    @field_validator("output_language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        if value not in SUPPORTED_OUTPUT_LANGUAGES:
            raise ValueError("unsupported output language")
        return value

    @model_validator(mode="after")
    def validate_asset_analysts(self) -> RunCreateRequest:
        if self.asset_type == "crypto" and "fundamentals" in self.selected_analysts:
            raise ValueError("fundamentals analyst is unavailable for crypto")
        return self


class ArtifactMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    kind: str
    media_type: str
    content_sha256: str
    byte_size: int = Field(ge=0)
    locator: str


class ApiErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    fields: tuple[str, ...] = ()
    active_run_id: str | None = None


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: ApiErrorDetail
