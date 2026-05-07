"""Pydantic schemas and rating vocabulary for structured agent output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Canonical 5-tier rating vocabulary
CANONICAL_RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")

# Synonym mapping for legacy free-text parsing
RATING_SYNONYMS: dict[str, str] = {
    "Strong Buy": "Buy",
    "Aggressive Buy": "Buy",
    "Accumulate": "Overweight",
    "Outperform": "Overweight",
    "Neutral": "Hold",
    "Market Perform": "Hold",
    "Equal Weight": "Hold",
    "Reduce": "Underweight",
    "Underperform": "Underweight",
    "Strong Sell": "Sell",
    "Avoid": "Sell",
}


def normalize_rating(raw: str) -> str:
    """Map a raw rating string to the canonical 5-tier vocabulary.

    This is a **post-hoc helper for free-text extraction only** — it is NOT wired
    into ResearchPlanSchema as a Pydantic field_validator.  When the LLM returns a
    non-canonical rating (e.g. "Strong Buy"), Pydantic will raise ValidationError
    and the structured output utility will degrade to the free-text fallback path,
    where this function is used to normalize the extracted rating string.

    Checks exact match first (case-insensitive), then synonym lookup.
    Defaults to 'Hold' if unmappable.
    """
    if not raw or not raw.strip():
        return "Hold"
    cleaned = raw.strip()
    # Check canonical values (case-insensitive)
    for canonical in CANONICAL_RATINGS:
        if cleaned.lower() == canonical.lower():
            return canonical
    # Check synonyms (case-insensitive)
    for synonym, canonical in RATING_SYNONYMS.items():
        if cleaned.lower() == synonym.lower():
            return canonical
    return "Hold"


class ResearchPlanSchema(BaseModel):
    """Structured output schema for the Research Manager agent."""

    recommendation: Literal["Buy", "Overweight", "Hold", "Underweight", "Sell"] = Field(
        description="The investment recommendation. Exactly one of Buy / Overweight / Hold / Underweight / Sell."
    )
    confidence: Literal["HIGH", "MED", "LOW"] = Field(
        description="Confidence level in the recommendation based on evidence strength."
    )
    bull_evidence: list[str] = Field(
        description="Top 3 data-backed bull arguments with source attribution."
    )
    bear_evidence: list[str] = Field(
        description="Top 3 data-backed bear arguments with source attribution."
    )
    rationale: str = Field(
        description="2-3 sentence synthesis explaining why the recommendation was chosen."
    )
    strategic_actions: str = Field(
        description="Concrete next steps for the trader to implement the recommendation."
    )
    conflict_resolution: str = Field(
        description="How conflicting bull/bear evidence was weighed to reach the recommendation."
    )


class TraderProposalSchema(BaseModel):
    """Structured output schema for the Trader agent."""

    action: Literal["Buy", "Hold", "Sell"] = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell."
    )
    entry_price: float | None = Field(
        default=None, description="Proposed entry price in the instrument's quote currency."
    )
    stop_loss: float | None = Field(default=None, description="Stop-loss level.")
    take_profit: float | None = Field(default=None, description="Take-profit target.")
    position_sizing: str | None = Field(
        default=None, description="Position sizing rationale, e.g. '5% of portfolio'."
    )
    reasoning: str = Field(
        description="Multi-sentence reasoning for the trade proposal anchored in analyst reports."
    )
    catalyst_timeline: str = Field(
        description="Expected catalysts and time horizon from ground-truth calendar data."
    )
