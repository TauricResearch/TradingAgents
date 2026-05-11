"""Standardized input/output schemas for the generic agent interface."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    """Standardized input contract for any trading agent."""

    ticker: str
    date: str
    context: dict[str, str] = Field(
        default_factory=dict,
        description="Optional context keyed by: market_data, news, fundamentals, sentiment, technical_indicators",
    )


class PriceTargets(BaseModel):
    """Entry, target, and stop-loss price levels."""

    entry: float
    target: float
    stop_loss: float


class AgentOutput(BaseModel):
    """Standardized output contract for any trading agent."""

    rating: Literal["BUY", "OVERWEIGHT", "HOLD", "UNDERWEIGHT", "SELL"]
    confidence: float = Field(ge=0.0, le=1.0)
    price_targets: PriceTargets | None = None
    thesis: str
    risk_factors: list[str] = Field(default_factory=list)
