"""
Pydantic validation models for TradingAgents.

Provides strict schema validation at agent boundaries to catch
validation errors early and provide clear error messages.

Issue #434: https://github.com/TauricResearch/TradingAgents/issues/434
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from datetime import date as DateType


class AnalystReport(BaseModel):
    """Validated analyst report output."""
    
    report: str = Field(
        ...,
        min_length=10,
        description="Detailed analyst report with market insights"
    )
    indicators_used: List[str] = Field(
        default_factory=list,
        description="List of technical indicators used in the analysis"
    )
    has_trade_proposal: bool = Field(
        default=False,
        description="Whether the report contains a FINAL TRANSACTION PROPOSAL"
    )
    
    @field_validator('report')
    @classmethod
    def validate_report_quality(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("Report must be at least 10 characters")
        return v.strip()


class InvestDebateStateValidated(BaseModel):
    """Validated research debate state."""
    
    bull_history: str = Field(default="", description="Bullish conversation history")
    bear_history: str = Field(default="", description="Bearish conversation history")
    history: str = Field(default="", description="Full conversation history")
    current_response: str = Field(default="", description="Latest response")
    judge_decision: str = Field(default="", description="Final judge decision")
    count: int = Field(default=0, ge=0, description="Conversation length")
    
    @field_validator('judge_decision')
    @classmethod
    def validate_judge_decision(cls, v: str) -> str:
        if v and v.strip().upper() not in ['', 'BUY', 'SELL', 'HOLD']:
            # Allow any text but warn about non-standard decisions
            pass
        return v


class RiskDebateStateValidated(BaseModel):
    """Validated risk management debate state."""
    
    aggressive_history: str = Field(default="", description="Aggressive agent history")
    conservative_history: str = Field(default="", description="Conservative agent history")
    neutral_history: str = Field(default="", description="Neutral agent history")
    history: str = Field(default="", description="Full conversation history")
    latest_speaker: str = Field(default="", description="Last speaker")
    current_aggressive_response: str = Field(default="")
    current_conservative_response: str = Field(default="")
    current_neutral_response: str = Field(default="")
    judge_decision: str = Field(default="", description="Judge's decision")
    count: int = Field(default=0, ge=0, description="Conversation length")


class TradeDecision(BaseModel):
    """Validated final trade decision."""
    
    decision: str = Field(
        ...,
        description="Trade decision: BUY, SELL, or HOLD"
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence level (0-1)"
    )
    reasoning: str = Field(
        default="",
        description="Brief reasoning for the decision"
    )
    
    @field_validator('decision')
    @classmethod
    def validate_decision(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ['BUY', 'SELL', 'HOLD']:
            raise ValueError(f"Decision must be BUY, SELL, or HOLD, got: {v}")
        return v


class AgentInput(BaseModel):
    """Validated agent input state."""
    
    company_of_interest: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Stock ticker symbol"
    )
    trade_date: str = Field(
        ...,
        description="Trading date in YYYY-MM-DD format"
    )
    
    @field_validator('company_of_interest')
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not v.isalpha():
            raise ValueError(f"Ticker must be alphabetic, got: {v}")
        return v
    
    @field_validator('trade_date')
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            DateType.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Expected YYYY-MM-DD")
        return v


def validate_agent_output(
    output: Dict[str, Any],
    model_class: type[BaseModel]
) -> Dict[str, Any]:
    """
    Validate agent output against a Pydantic model.
    
    Args:
        output: Raw agent output dictionary
        model_class: Pydantic model class to validate against
        
    Returns:
        Validated dictionary
        
    Raises:
        ValueError: If validation fails
    """
    try:
        validated = model_class(**output)
        return validated.model_dump()
    except Exception as e:
        raise ValueError(
            f"Agent output validation failed for {model_class.__name__}: {e}"
        )


def safe_validate_agent_output(
    output: Dict[str, Any],
    model_class: type[BaseModel]
) -> Dict[str, Any]:
    """
    Safely validate agent output with fallback.
    
    If validation fails, returns the original output with an error field.
    Does not raise exceptions.
    """
    try:
        validated = model_class(**output)
        result = validated.model_dump()
        result['_validation_status'] = 'valid'
        return result
    except Exception as e:
        result = dict(output) if isinstance(output, dict) else {'raw': str(output)}
        result['_validation_status'] = 'invalid'
        result['_validation_error'] = str(e)
        return result
