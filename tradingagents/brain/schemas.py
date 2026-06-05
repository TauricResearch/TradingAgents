"""Structured LLM outputs for the brain's agents.

Each agent returns a small Pydantic object (JSON-strict). The brain assembles
these into the project's ResearchState; the schemas mirror the "what you
produce" block of the system prompts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..domain.enums import Direction, RiskVerdict


class DeskOpinion(BaseModel):
    """Output of a desk agent (Market / Sentiment / Technical / Fundamentals)."""

    view: str = Field(description="Concise analysis from this desk's angle.")
    suggested_direction: Direction = Field(
        description="This desk's directional proposal (5-level enum)."
    )
    suggested_conviction: Direction = Field(
        description="This desk's conviction level (same 5-level vocabulary)."
    )
    rationale: str = Field(description="One or two sentences justifying the call.")


class PMDecision(BaseModel):
    """Output of the Portfolio Manager: the aggregated final call + ATR coefficients."""

    direction: Direction = Field(description="Final aggregated direction.")
    conviction: Direction = Field(description="Final conviction level.")
    k_entry: float = Field(description="Entry distance in ATR units (smaller = chase less).")
    k_stop: float = Field(description="Stop distance in ATR units (> 0).")
    k_tp: float = Field(description="Take-profit distance in ATR units (> 0).")
    pro: list[str] = Field(default_factory=list, description="Bull points.")
    contro: list[str] = Field(default_factory=list, description="Bear points.")
    need_more_info: bool = Field(
        default=False,
        description="True if a material doubt remains and the desks should be re-queried.",
    )
    rationale: str = Field(default="", description="Why this decision.")


class RiskDecision(BaseModel):
    """Output of the Risk Analyst gate (bearish antithesis)."""

    verdict: RiskVerdict = Field(description="approved / declined / send_back.")
    rationale: str = Field(description="The bear case and the reason for the verdict.")
