"""
Pydantic schemas for structured LLM outputs.

These schemas ensure type-safe, validated responses from LLM calls,
eliminating the need for manual parsing and reducing errors.
"""

from pydantic import BaseModel, Field
from typing import Literal, List, Optional


class TradeDecision(BaseModel):
    """Structured output for trading decisions."""
    
    decision: Literal["BUY", "SELL", "HOLD"] = Field(
        description="The final trading decision"
    )
    rationale: str = Field(
        description="Detailed explanation of the decision"
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence level in the decision"
    )
    key_factors: List[str] = Field(
        description="List of key factors influencing the decision"
    )



class TickerList(BaseModel):
    """Structured output for ticker symbol lists."""
    
    tickers: List[str] = Field(
        description="List of valid stock ticker symbols (1-5 uppercase letters)"
    )


class ThemeList(BaseModel):
    """Structured output for market themes."""
    
    themes: List[str] = Field(
        description="List of trending market themes or sectors"
    )


class MarketMover(BaseModel):
    """Individual market mover entry."""
    
    ticker: str = Field(
        description="Stock ticker symbol"
    )
    type: Literal["gainer", "loser"] = Field(
        description="Whether this is a top gainer or loser"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Brief reason for the movement"
    )


class MarketMovers(BaseModel):
    """Structured output for market movers."""
    
    movers: List[MarketMover] = Field(
        description="List of market movers (gainers and losers)"
    )


class InvestmentOpportunity(BaseModel):
    """Individual investment opportunity."""
    
    ticker: str = Field(
        description="Stock ticker symbol"
    )
    score: int = Field(
        ge=1,
        le=10,
        description="Investment score from 1-10"
    )
    rationale: str = Field(
        description="Why this is a good opportunity"
    )
    risk_level: Literal["low", "medium", "high"] = Field(
        description="Risk level assessment"
    )


class RankedOpportunities(BaseModel):
    """Structured output for ranked investment opportunities."""
    
    opportunities: List[InvestmentOpportunity] = Field(
        description="List of investment opportunities ranked by score"
    )
    market_context: str = Field(
        description="Brief overview of current market conditions"
    )


class DebateDecision(BaseModel):
    """Structured output for debate/research manager decisions."""
    
    decision: Literal["BUY", "SELL", "HOLD"] = Field(
        description="Investment recommendation"
    )
    summary: str = Field(
        description="Summary of the debate and key arguments"
    )
    bull_points: List[str] = Field(
        description="Key bullish arguments"
    )
    bear_points: List[str] = Field(
        description="Key bearish arguments"
    )
    investment_plan: str = Field(
        description="Detailed investment plan for the trader"
    )


class RiskAssessment(BaseModel):
    """Structured output for risk management decisions."""
    
    final_decision: Literal["BUY", "SELL", "HOLD"] = Field(
        description="Final trading decision after risk assessment"
    )
    risk_level: Literal["low", "medium", "high", "very_high"] = Field(
        description="Overall risk level"
    )
    adjusted_plan: str = Field(
        description="Risk-adjusted investment plan"
    )
    risk_factors: List[str] = Field(
        description="Key risk factors identified"
    )
    mitigation_strategies: List[str] = Field(
        description="Strategies to mitigate identified risks"
    )
