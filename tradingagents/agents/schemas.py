"""Pydantic models for structured agent outputs."""

from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field


class ActionSignal(str, Enum):
    BUY = "Buy"
    SELL = "Sell"
    HOLD = "Hold"


class PortfolioRating(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class AnalystReport(BaseModel):
    """Structured output from any analyst (market, news, fundamentals, social media)."""

    summary: str = Field(description="Concise summary of key findings")
    detailed_analysis: str = Field(description="Full analysis with supporting evidence")
    key_points: list[str] = Field(description="Bullet list of actionable insights")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence level 0-1")


class TraderDecision(BaseModel):
    """Structured output from the trader agent."""

    action: ActionSignal = Field(description="Trading action: Buy, Sell, or Hold")
    reasoning: str = Field(description="Rationale for the decision")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence level 0-1")
    price_target: Optional[float] = Field(default=None, description="Target price if applicable")
    stop_loss: Optional[float] = Field(default=None, description="Stop-loss price if applicable")


class RiskAssessment(BaseModel):
    """Structured output from a risk debater (aggressive, conservative, neutral)."""

    stance: str = Field(description="The analyst's stance on the trade")
    argument: str = Field(description="Core argument with supporting evidence")
    risk_factors: list[str] = Field(description="Key risk factors identified")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence level 0-1")


class PortfolioDecision(BaseModel):
    """Structured output from the portfolio manager."""

    rating: PortfolioRating = Field(description="Buy / Overweight / Hold / Underweight / Sell")
    executive_summary: str = Field(description="Concise action plan")
    investment_thesis: str = Field(description="Detailed reasoning for the decision")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence level 0-1")
    price_target: Optional[float] = Field(default=None, description="Target price if applicable")
    time_horizon: Optional[str] = Field(default=None, description="Recommended holding period")


# Key fields to extract from each model type (only non-text, structured data)
_EXTRACT_KEYS: dict[type[BaseModel], list[str]] = {
    AnalystReport: ["confidence", "key_points"],
    TraderDecision: ["action", "confidence", "price_target", "stop_loss"],
    RiskAssessment: ["stance", "confidence", "risk_factors"],
    PortfolioDecision: ["rating", "confidence", "price_target", "time_horizon"],
}


def extract_fields(
    model: Union[AnalystReport, TraderDecision, RiskAssessment, PortfolioDecision],
) -> dict:
    """Extract key structured fields from a validated Pydantic model.

    Returns a flat dict containing only the actionable structured fields
    (rating, action, price targets, confidence, etc.) with None values omitted.
    Enum values are converted to their string representation.
    """
    keys = _EXTRACT_KEYS.get(type(model), list(model.model_fields.keys()))
    result: dict = {}
    for key in keys:
        val = getattr(model, key)
        if val is None:
            continue
        # Convert enums to their string value
        if isinstance(val, Enum):
            val = val.value
        result[key] = val
    return result
