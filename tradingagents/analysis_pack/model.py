from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnalysisPackContent(BaseModel):
    version: int = 1
    ticker: str
    trade_date: str
    event_id: str | None = None
    event_context: str = ""
    reports: dict[str, str] = Field(default_factory=dict)
    debates: dict[str, Any] = Field(default_factory=dict)
    final_trade_decisions: list[dict[str, str]] = Field(default_factory=list)
