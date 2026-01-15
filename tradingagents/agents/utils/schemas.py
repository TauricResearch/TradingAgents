from pydantic import BaseModel, Field
from typing import Literal

class ConfidenceOutput(BaseModel):
    """Calibrated confidence emission from researchers."""
    rationale: str = Field(description="Mathematical or qualitative reasoning for the score.")
    confidence: float = Field(
        description="Confidence score between 0.0 and 1.0.",
        ge=0.0,
        le=1.0
    )

class TraderOutput(BaseModel):
    """Structured trade proposal from the Trader."""
    action: Literal["BUY", "SELL", "HOLD"] = Field(description="Proposed market action.")
    confidence: float = Field(
        description="Confidence in the proposal between 0.0 and 1.0.",
        ge=0.0,
        le=1.0
    )
    rationale: str = Field(description="Direct justification for the action.")
