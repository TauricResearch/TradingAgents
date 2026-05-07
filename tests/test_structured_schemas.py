"""Tests for structured_schemas module: normalize_rating, ResearchPlanSchema, TraderProposalSchema.

Feature: upstream-feature-adoption, Property 13: Rating Synonym Mapping
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from tradingagents.agents.utils.structured_schemas import (
    CANONICAL_RATINGS,
    RATING_SYNONYMS,
    ResearchPlanSchema,
    TraderProposalSchema,
    normalize_rating,
)

# ---------------------------------------------------------------------------
# Property 13: normalize_rating(synonym) returns canonical;
#              normalize_rating(canonical) returns itself
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(synonym=st.sampled_from(list(RATING_SYNONYMS.keys())))
def test_prop13_synonym_maps_to_canonical(synonym: str):
    """For any synonym key, normalize_rating returns the mapped canonical value."""
    # Feature: upstream-feature-adoption, Property 13: Rating Synonym Mapping
    result = normalize_rating(synonym)
    assert result == RATING_SYNONYMS[synonym]
    assert result in CANONICAL_RATINGS


@settings(max_examples=100)
@given(canonical=st.sampled_from(list(CANONICAL_RATINGS)))
def test_prop13_canonical_returns_itself(canonical: str):
    """For any canonical rating, normalize_rating returns it unchanged."""
    # Feature: upstream-feature-adoption, Property 13: Rating Synonym Mapping
    assert normalize_rating(canonical) == canonical


@settings(max_examples=100)
@given(canonical=st.sampled_from(list(CANONICAL_RATINGS)))
def test_prop13_canonical_case_insensitive(canonical: str):
    """Canonical ratings are matched case-insensitively."""
    # Feature: upstream-feature-adoption, Property 13: Rating Synonym Mapping
    assert normalize_rating(canonical.upper()) == canonical
    assert normalize_rating(canonical.lower()) == canonical


@settings(max_examples=100)
@given(synonym=st.sampled_from(list(RATING_SYNONYMS.keys())))
def test_prop13_synonym_case_insensitive(synonym: str):
    """Synonyms are matched case-insensitively."""
    # Feature: upstream-feature-adoption, Property 13: Rating Synonym Mapping
    expected = RATING_SYNONYMS[synonym]
    assert normalize_rating(synonym.upper()) == expected
    assert normalize_rating(synonym.lower()) == expected


# ---------------------------------------------------------------------------
# Unit: normalize_rating with unknown input defaults to "Hold"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "Unknown Rating",
        "XYZZY",
        "maybe buy",
        "   ",
        "",
        "123",
    ],
)
def test_normalize_rating_unknown_defaults_to_hold(raw: str):
    """Unknown or unmappable inputs default to 'Hold'."""
    assert normalize_rating(raw) == "Hold"


def test_normalize_rating_whitespace_handling():
    """Leading/trailing whitespace is stripped before matching."""
    assert normalize_rating("  Buy  ") == "Buy"
    assert normalize_rating("\tStrong Buy\n") == "Buy"


# ---------------------------------------------------------------------------
# Unit: ResearchPlanSchema validates correct input
# ---------------------------------------------------------------------------


def test_research_plan_schema_valid():
    """ResearchPlanSchema accepts valid input and produces correct fields."""
    data = {
        "recommendation": "Buy",
        "confidence": "HIGH",
        "bull_evidence": [
            "Revenue grew +15% YoY (source: Q3 earnings)",
            "FCF margin expanded to 22% (source: 10-Q)",
            "Institutional accumulation +3.2% (source: 13F filings)",
        ],
        "bear_evidence": [
            "Debt/equity ratio at 1.8x (source: balance sheet)",
            "Sector rotation risk (source: macro report)",
            "Valuation premium vs peers (source: comps)",
        ],
        "rationale": "Strong revenue growth and expanding margins outweigh leverage concerns.",
        "strategic_actions": "Enter at $150 with stop at $135, target $175.",
        "conflict_resolution": "Bull evidence is HIGH confidence from primary sources; bear evidence is MED confidence from secondary analysis.",
    }
    schema = ResearchPlanSchema(**data)
    assert schema.recommendation == "Buy"
    assert schema.confidence == "HIGH"
    assert len(schema.bull_evidence) == 3
    assert len(schema.bear_evidence) == 3
    assert schema.rationale.startswith("Strong revenue")


def test_research_plan_schema_rejects_invalid_recommendation():
    """ResearchPlanSchema rejects invalid recommendation values."""
    with pytest.raises(ValidationError):
        ResearchPlanSchema(
            recommendation="Strong Buy",  # Not in Literal
            confidence="HIGH",
            bull_evidence=["a"],
            bear_evidence=["b"],
            rationale="test",
            strategic_actions="test",
            conflict_resolution="test",
        )


def test_research_plan_schema_rejects_invalid_confidence():
    """ResearchPlanSchema rejects invalid confidence values."""
    with pytest.raises(ValidationError):
        ResearchPlanSchema(
            recommendation="Buy",
            confidence="VERY_HIGH",  # Not in Literal
            bull_evidence=["a"],
            bear_evidence=["b"],
            rationale="test",
            strategic_actions="test",
            conflict_resolution="test",
        )


# ---------------------------------------------------------------------------
# Unit: TraderProposalSchema validates correct input
# ---------------------------------------------------------------------------


def test_trader_proposal_schema_valid():
    """TraderProposalSchema accepts valid input with all fields."""
    data = {
        "action": "Buy",
        "entry_price": 150.25,
        "stop_loss": 135.00,
        "take_profit": 175.50,
        "position_sizing": "5% of portfolio",
        "reasoning": "Strong momentum with institutional support. Entry near 200-day SMA.",
        "catalyst_timeline": "Earnings on 2025-07-15, FOMC on 2025-07-30.",
    }
    schema = TraderProposalSchema(**data)
    assert schema.action == "Buy"
    assert schema.entry_price == 150.25
    assert schema.stop_loss == 135.00
    assert schema.take_profit == 175.50
    assert schema.position_sizing == "5% of portfolio"


def test_trader_proposal_schema_optional_fields():
    """TraderProposalSchema allows None for optional fields."""
    data = {
        "action": "Hold",
        "reasoning": "No clear entry signal at current levels.",
        "catalyst_timeline": "Waiting for Q4 earnings in January.",
    }
    schema = TraderProposalSchema(**data)
    assert schema.action == "Hold"
    assert schema.entry_price is None
    assert schema.stop_loss is None
    assert schema.take_profit is None
    assert schema.position_sizing is None


def test_trader_proposal_schema_rejects_invalid_action():
    """TraderProposalSchema rejects invalid action values."""
    with pytest.raises(ValidationError):
        TraderProposalSchema(
            action="Overweight",  # Not in Literal for trader
            reasoning="test",
            catalyst_timeline="test",
        )
