"""Tests for the Factor Extractor node (decision_mode="structured",
trading-workspace TradingAgents#19). No real LLM calls -- mocked structured
output, same pattern as test_global_shock.py."""
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.factor_extractor import create_factor_extractor
from tradingagents.agents.schemas import FactorExtraction

_STATE = {
    "company_of_interest": "NVDA",
    "market_report": "RSI 70, overbought.",
    "sentiment_report": "Bullish social chatter.",
    "news_report": "Guidance raised, resolves in 2h.",
    "fundamentals_report": "P/E 45x.",
}


def _llm_returning(factors: FactorExtraction):
    structured = MagicMock()
    structured.invoke.return_value = factors
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestFactorExtractorNode:
    def test_extracted_factors_and_investment_plan_are_populated(self):
        factors = FactorExtraction(
            dated_catalyst_present=True, catalyst_hours_to_resolution=2.0,
            technical_direction=0.8, technical_confidence=0.8,
            sentiment_direction=0.7, sentiment_confidence=0.7,
        )
        node = create_factor_extractor(_llm_returning(factors))
        result = node(_STATE)
        assert result["extracted_factors"] is factors
        assert "**Recommendation**: Buy" in result["investment_plan"]

    def test_structured_output_failure_falls_back_to_neutral_hold(self):
        """Must NOT fall back to free-text -- decision_model.py needs an
        actual FactorExtraction object, not a rendered string."""
        structured = MagicMock()
        structured.invoke.side_effect = RuntimeError("provider error")
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        node = create_factor_extractor(llm)

        result = node(_STATE)

        assert isinstance(result["extracted_factors"], FactorExtraction)
        assert result["extracted_factors"].dated_catalyst_present is False
        assert "**Recommendation**: Hold" in result["investment_plan"]

    def test_provider_without_structured_output_support_falls_back_to_neutral(self):
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError
        node = create_factor_extractor(llm)

        result = node(_STATE)

        assert isinstance(result["extracted_factors"], FactorExtraction)
        assert "**Recommendation**: Hold" in result["investment_plan"]


@pytest.mark.unit
class TestScorePersistence:
    """TradingAgents#19 step 4 -- the scorer's numbers have to survive the run.

    27 of the 28 post-#21-fix structured retro decisions have no recoverable
    score, because only the Trader's prose was persisted and it restates the
    score only occasionally. Every "which gate stopped this one" question then
    costs a fresh billed batch. These tests lock the data path open.
    """

    def test_node_emits_score_rating_and_reason(self):
        factors = FactorExtraction(
            dated_catalyst_present=True, catalyst_hours_to_resolution=2.0,
            technical_direction=0.8, technical_confidence=0.8,
            sentiment_direction=0.7, sentiment_confidence=0.7,
        )
        result = create_factor_extractor(_llm_returning(factors))(_STATE)

        # 0.8x0.8 + 0.7x0.7 = 1.13, clamped to the score's [-1, 1] cap.
        assert result["structured_rating"] == "Buy"
        assert result["structured_score"] == pytest.approx(1.0)
        assert "confidence-weighted score" in result["structured_reason"]

    def test_score_is_the_uncapped_sum_when_inside_the_clamp(self):
        factors = FactorExtraction(
            dated_catalyst_present=True, catalyst_hours_to_resolution=2.0,
            technical_direction=0.4, technical_confidence=0.5,
            sentiment_direction=0.3, sentiment_confidence=0.5,
        )
        result = create_factor_extractor(_llm_returning(factors))(_STATE)
        assert result["structured_score"] == pytest.approx(0.4 * 0.5 + 0.3 * 0.5)

    def test_score_is_post_risk_flag_damping(self):
        """The persisted number must be the one the rating was made from --
        a pre-damping score would misattribute every near-miss."""
        factors = FactorExtraction(
            dated_catalyst_present=True, catalyst_hours_to_resolution=2.0,
            technical_direction=0.5, technical_confidence=1.0,
            sentiment_direction=0.0, sentiment_confidence=0.0,
            risk_flags=["a", "b"],
        )
        result = create_factor_extractor(_llm_returning(factors))(_STATE)
        assert result["structured_score"] == pytest.approx(0.5 * (1 - 0.15 * 2))

    def test_catalyst_gate_reason_names_the_gate_that_fired(self):
        """The two hard gates must be distinguishable after the fact -- "no
        catalyst at all" and "catalyst too far out" are different findings and
        point at different fixes."""
        absent = FactorExtraction(
            dated_catalyst_present=False, catalyst_hours_to_resolution=None,
            technical_direction=0.9, technical_confidence=0.9,
            sentiment_direction=0.9, sentiment_confidence=0.9,
        )
        r1 = create_factor_extractor(_llm_returning(absent))(_STATE)
        assert r1["structured_score"] == 0.0
        assert "No dated catalyst" in r1["structured_reason"]

        too_far = FactorExtraction(
            dated_catalyst_present=True, catalyst_hours_to_resolution=48.0,
            technical_direction=0.9, technical_confidence=0.9,
            sentiment_direction=0.9, sentiment_confidence=0.9,
        )
        r2 = create_factor_extractor(_llm_returning(too_far))(_STATE)
        assert r2["structured_score"] == 0.0
        assert "48.0h" in r2["structured_reason"]
        assert "beyond the 24h window" in r2["structured_reason"]

    def test_persisted_rating_matches_the_rendered_plan(self):
        """The number and the prose must never disagree -- they come from one
        compute_rating() call, and this asserts that stays true."""
        factors = FactorExtraction(
            dated_catalyst_present=True, catalyst_hours_to_resolution=1.0,
            technical_direction=-0.9, technical_confidence=0.9,
            sentiment_direction=-0.5, sentiment_confidence=0.5,
        )
        result = create_factor_extractor(_llm_returning(factors))(_STATE)
        assert f"**Recommendation**: {result['structured_rating']}" in result["investment_plan"]
