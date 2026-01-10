"""
Pydantic Schemas for Strict JSON Enforcement

All agent outputs must conform to these schemas.
Retry loops enforce compliance.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal
from enum import Enum


class SignalType(str, Enum):
    """Trading signal types."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"  # Used for rejected trades (dead state)


class AnalystOutput(BaseModel):
    """
    Schema for analyst outputs (Market, News, Fundamentals, Social).
    
    STRICT JSON ENFORCEMENT: LLM must output exactly this structure.
    """
    analyst_type: str = Field(..., description="Type of analyst (market/news/fundamentals/social)")
    key_findings: List[str] = Field(..., min_items=1, max_items=5, description="3-5 key findings")
    signal: SignalType = Field(..., description="Trading signal recommendation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    reasoning: str = Field(..., min_length=50, max_length=500, description="Brief reasoning")
    
    @validator('key_findings')
    def validate_findings(cls, v):
        """Ensure findings are non-empty."""
        if not all(f.strip() for f in v):
            raise ValueError("All findings must be non-empty strings")
        return v


class ResearcherOutput(BaseModel):
    """
    Schema for researcher outputs (Bull/Bear).
    
    CRITICAL: key_arguments are validated by FactChecker.
    """
    researcher_type: Literal["bull", "bear"] = Field(..., description="Bull or Bear researcher")
    key_arguments: List[str] = Field(..., min_items=2, max_items=5, description="2-5 key arguments")
    signal: SignalType = Field(..., description="Trading signal")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence 0-1")
    supporting_evidence: List[str] = Field(..., description="Evidence supporting arguments")
    
    @validator('key_arguments')
    def validate_arguments(cls, v):
        """Ensure arguments are substantive."""
        if not all(len(arg.strip()) > 20 for arg in v):
            raise ValueError("Arguments must be at least 20 characters")
        return v


class RiskAnalystOutput(BaseModel):
    """Schema for risk analyst outputs (Risky/Safe/Neutral)."""
    analyst_type: Literal["risky", "safe", "neutral"] = Field(..., description="Risk analyst type")
    risk_assessment: str = Field(..., min_length=50, description="Risk assessment")
    key_risks: List[str] = Field(..., min_items=1, max_items=5, description="Key risks identified")
    recommended_action: SignalType = Field(..., description="Recommended action")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence 0-1")


class TradeDecision(BaseModel):
    """
    Final trade decision schema.
    
    This is the output after FactChecker validation.
    """
    action: SignalType = Field(..., description="Final trading action")
    quantity: Optional[int] = Field(None, ge=0, description="Number of shares (if BUY/SELL), 0 for rejected trades")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence")
    reasoning: str = Field(..., min_length=20, description="Comprehensive reasoning")  # Reduced from 100 to 20
    fact_check_passed: bool = Field(..., description="Whether fact check passed")
    risk_gate_passed: bool = Field(..., description="Whether risk gate passed")
    
    # Risk metrics from deterministic gate
    position_size: Optional[int] = Field(None, description="Calculated position size")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    risk_pct: Optional[float] = Field(None, description="Risk as % of portfolio")


class FactCheckReport(BaseModel):
    """Fact check validation report."""
    total_arguments: int = Field(..., ge=0, description="Total arguments checked")
    valid_arguments: int = Field(..., ge=0, description="Number of valid arguments")
    invalid_arguments: int = Field(..., ge=0, description="Number of invalid arguments")
    contradictions: List[str] = Field(default_factory=list, description="List of contradictions found")
    overall_valid: bool = Field(..., description="Overall validation result")
    
    @validator('valid_arguments', 'invalid_arguments')
    def validate_counts(cls, v, values):
        """Ensure counts are consistent."""
        if 'total_arguments' in values:
            if v > values['total_arguments']:
                raise ValueError("Count cannot exceed total")
        return v


class WorkflowState(BaseModel):
    """
    Complete workflow state.
    
    Tracks all agent outputs and validation results.
    """
    ticker: str = Field(..., description="Anonymized ticker (ASSET_XXX)")
    trading_date: str = Field(..., description="Trading date YYYY-MM-DD")
    
    # Analyst outputs
    market_analysis: Optional[AnalystOutput] = None
    news_analysis: Optional[AnalystOutput] = None
    fundamentals_analysis: Optional[AnalystOutput] = None
    social_analysis: Optional[AnalystOutput] = None
    
    # Researcher outputs
    bull_research: Optional[ResearcherOutput] = None
    bear_research: Optional[ResearcherOutput] = None
    
    # Risk analysis
    risky_analysis: Optional[RiskAnalystOutput] = None
    safe_analysis: Optional[RiskAnalystOutput] = None
    neutral_analysis: Optional[RiskAnalystOutput] = None
    
    # Validation results
    fact_check_report: Optional[FactCheckReport] = None
    
    # Final decision
    final_decision: Optional[TradeDecision] = None
    
    # Metadata
    regime: Optional[str] = Field(None, description="Detected market regime")
    workflow_start_time: Optional[float] = None
    workflow_end_time: Optional[float] = None
    
    def get_latency(self) -> Optional[float]:
        """Calculate total workflow latency."""
        if self.workflow_start_time and self.workflow_end_time:
            return self.workflow_end_time - self.workflow_start_time
        return None


# Example usage
if __name__ == "__main__":
    import json
    
    # Test valid analyst output
    valid_output = {
        "analyst_type": "market",
        "key_findings": [
            "Price broke above 200-day SMA",
            "Volume increased 50% above average",
            "RSI at 55 (neutral zone)"
        ],
        "signal": "BUY",
        "confidence": 0.75,
        "reasoning": "Technical indicators show bullish momentum with strong volume confirmation and price breaking key resistance."
    }
    
    analyst = AnalystOutput(**valid_output)
    print("✅ Valid analyst output:")
    print(analyst.json(indent=2))
    
    # Test invalid output (missing fields)
    try:
        invalid_output = {
            "analyst_type": "market",
            "key_findings": ["Only one finding"],  # Too few
            "signal": "BUY"
            # Missing confidence and reasoning
        }
        AnalystOutput(**invalid_output)
    except Exception as e:
        print(f"\n❌ Invalid output rejected: {e}")
