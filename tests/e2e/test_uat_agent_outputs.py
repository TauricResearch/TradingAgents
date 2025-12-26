"""
UAT (User Acceptance Testing) for Agent Output Quality.

This module provides end-to-end tests for complete agent workflows:
1. Complete analysis workflow (BUY/SELL/HOLD scenarios)
2. Edge case handling (missing data, conflicting reports)
3. Content quality validation (length, structure, clarity)
4. State integrity checks (field presence, debate coherence)

All tests use mocked data to avoid real API calls.
"""

import pytest
from typing import Dict, Any

from tradingagents.utils.output_validator import (
    validate_agent_state,
    validate_decision_quality,
    validate_debate_state,
    validate_report_completeness,
)

pytestmark = pytest.mark.e2e


# ============================================================================
# Test Complete Analysis Workflow
# ============================================================================

class TestCompleteAnalysisWorkflow:
    """Test complete agent analysis workflow for different trading scenarios."""

    def test_buy_scenario_complete_workflow(self, sample_agent_state_buy):
        """
        Test complete BUY scenario workflow.

        Validates:
        - All reports generated
        - Investment debate concludes with BUY
        - Risk debate validates decision
        - Final decision is BUY with reasoning
        """
        state = sample_agent_state_buy

        # Validate complete state
        result = validate_agent_state(state)

        assert result.is_valid is True
        assert result.metrics["company_of_interest"] == "AAPL"
        assert result.metrics["reports_present"] == 4
        assert result.metrics["final_signal"] == "BUY"
        assert result.metrics["investment_debate_valid"] is True
        assert result.metrics["risk_debate_valid"] is True

    def test_sell_scenario_complete_workflow(self, sample_agent_state_sell):
        """
        Test complete SELL scenario workflow.

        Validates:
        - All reports generated
        - Investment debate concludes with SELL
        - Risk debate validates decision
        - Final decision is SELL with reasoning
        """
        state = sample_agent_state_sell

        result = validate_agent_state(state)

        assert result.is_valid is True
        assert result.metrics["final_signal"] == "SELL"
        assert result.metrics["reports_present"] == 4

    def test_hold_scenario_complete_workflow(self, sample_agent_state_hold):
        """
        Test complete HOLD scenario workflow.

        Validates:
        - All reports generated
        - Investment debate is inconclusive or balanced
        - Risk debate recommends caution
        - Final decision is HOLD with reasoning
        """
        state = sample_agent_state_hold

        result = validate_agent_state(state)

        assert result.is_valid is True
        assert result.metrics["final_signal"] == "HOLD"

    def test_workflow_preserves_debate_history(self, sample_agent_state_buy):
        """Test that debate history is preserved throughout workflow."""
        state = sample_agent_state_buy

        invest_debate = state["investment_debate_state"]
        risk_debate = state["risk_debate_state"]

        # Validate both debates have history
        invest_result = validate_debate_state(invest_debate, debate_type="invest")
        risk_result = validate_debate_state(risk_debate, debate_type="risk")

        assert invest_result.metrics["history_length"] > 0
        assert risk_result.metrics["history_length"] > 0
        assert invest_result.metrics["count"] > 0
        assert risk_result.metrics["count"] > 0

    def test_workflow_all_reports_meet_quality_standards(self, sample_agent_state_buy):
        """Test that all generated reports meet quality standards."""
        state = sample_agent_state_buy

        reports = [
            state["market_report"],
            state["sentiment_report"],
            state["news_report"],
            state["fundamentals_report"],
        ]

        for report in reports:
            result = validate_report_completeness(
                report,
                min_length=500,
                require_markdown_tables=False,
                require_sections=False,
            )
            assert result.is_valid is True
            assert result.metrics["length"] >= 500


# ============================================================================
# Test Edge Case Scenarios
# ============================================================================

class TestEdgeCaseScenarios:
    """Test handling of edge cases and unusual scenarios."""

    def test_missing_single_report_graceful_degradation(self):
        """Test that workflow continues with one missing report."""
        state = {
            "company_of_interest": "TSLA",
            "trade_date": "2024-01-20",
            "market_report": "Market analysis. " * 100,
            "sentiment_report": "Sentiment analysis. " * 100,
            "news_report": "News analysis. " * 100,
            # Missing fundamentals_report
            "investment_debate_state": {
                "history": "Debate based on available data",
                "count": 3,
                "judge_decision": "HOLD: Incomplete data, proceeding cautiously",
            },
            "risk_debate_state": {
                "history": "Risk assessment",
                "count": 2,
                "judge_decision": "HOLD: Missing fundamentals increases uncertainty",
            },
            "final_trade_decision": "HOLD: Awaiting fundamental data",
        }

        result = validate_agent_state(state)

        # Should still be valid but with warnings
        assert result.is_valid is True
        assert result.metrics["reports_present"] == 3
        assert len(result.warnings) > 0

    def test_conflicting_debate_conclusions_warning(self):
        """Test warning when investment and risk debates conflict."""
        state = {
            "company_of_interest": "GOOGL",
            "trade_date": "2024-01-22",
            "market_report": "Report. " * 100,
            "sentiment_report": "Report. " * 100,
            "news_report": "Report. " * 100,
            "fundamentals_report": "Report. " * 100,
            "investment_debate_state": {
                "history": "Bullish debate",
                "count": 2,
                "judge_decision": "BUY: Strong upside potential",
            },
            "risk_debate_state": {
                "history": "Risk concerns",
                "count": 2,
                "judge_decision": "SELL: Risk too high",  # Conflicts with invest
            },
            "final_trade_decision": "HOLD: Conflicting signals from teams",
        }

        result = validate_agent_state(state)

        assert result.is_valid is True
        # Different signals detected
        assert result.metrics.get("final_signal") == "HOLD"

    def test_empty_debate_history_but_valid_decision(self):
        """Test handling of empty debate history with valid decision."""
        state = {
            "company_of_interest": "MSFT",
            "trade_date": "2024-01-25",
            "market_report": "Report. " * 100,
            "investment_debate_state": {
                "history": "",  # Empty history
                "count": 0,
                "judge_decision": "HOLD: Insufficient deliberation",
            },
            "final_trade_decision": "HOLD: More analysis needed",
        }

        result = validate_agent_state(state)

        assert result.is_valid is True
        assert len(result.warnings) > 0  # Should warn about empty history

    def test_very_long_debate_convergence_issue(self):
        """Test detection of debates that went too long."""
        state = {
            "company_of_interest": "NVDA",
            "trade_date": "2024-01-28",
            "market_report": "Report. " * 100,
            "investment_debate_state": {
                "history": "Round 1...\nRound 2...\n" * 15,
                "count": 15,  # Very high count
                "judge_decision": "BUY: Finally reached consensus",
            },
            "final_trade_decision": "BUY: After extensive deliberation",
        }

        result = validate_agent_state(state)

        assert result.is_valid is True
        # Should have warnings about high debate count
        invest_debate_result = validate_debate_state(
            state["investment_debate_state"],
            debate_type="invest"
        )
        assert len(invest_debate_result.warnings) > 0

    def test_malformed_but_extractable_decision(self):
        """Test extraction of signal from poorly formatted decision."""
        decisions = [
            "i think we should BUY this stock",
            "recommendation: buy",
            "buy!!!",
            "Final call is to buy the position",
        ]

        for decision in decisions:
            result = validate_decision_quality(decision)
            assert result.metrics["signal"] == "BUY"

    def test_missing_all_debate_states(self):
        """Test handling when no debates occurred."""
        state = {
            "company_of_interest": "META",
            "trade_date": "2024-02-01",
            "market_report": "Report. " * 100,
            # No debate states
            "final_trade_decision": "HOLD: No consensus reached",
        }

        result = validate_agent_state(state)

        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert any("incomplete" in w.lower() for w in result.warnings)


# ============================================================================
# Test Content Quality
# ============================================================================

class TestContentQuality:
    """Test content quality validation across all outputs."""

    def test_report_minimum_length_enforcement(self):
        """Test that all reports meet minimum length requirements."""
        short_reports = [
            "Too short",
            "Also short",
            "Brief",
        ]

        for report in short_reports:
            result = validate_report_completeness(report, min_length=500)
            assert result.is_valid is False

    def test_report_markdown_structure_quality(self):
        """Test that well-structured reports are recognized."""
        well_structured_report = """
        # Market Analysis for AAPL

        ## Executive Summary
        Strong buy signal based on comprehensive analysis.

        ## Technical Indicators
        | Indicator | Value | Signal |
        |-----------|-------|--------|
        | RSI       | 45    | Neutral|
        | MACD      | +2.3  | Buy    |

        ## Fundamental Analysis
        - Revenue growth: 15% YoY
        - P/E ratio: 25 (reasonable for tech)
        - Strong balance sheet

        ## Conclusion
        """ + "Detailed conclusion. " * 50

        result = validate_report_completeness(
            well_structured_report,
            min_length=500,
            require_markdown_tables=True,
            require_sections=True,
        )

        assert result.is_valid is True
        assert result.metrics["markdown_tables"] > 0
        assert result.metrics["section_headers"] >= 3
        assert result.metrics["has_bullet_points"] is True

    def test_decision_clarity_with_reasoning(self):
        """Test that clear decisions with reasoning are validated."""
        clear_decisions = [
            "BUY: Strong fundamentals (P/E 20), positive momentum (RSI 55), bullish sentiment",
            "SELL: Overvalued at current P/E of 45, declining revenue, negative news",
            "HOLD: Mixed signals - good fundamentals but uncertain market conditions",
        ]

        for decision in clear_decisions:
            result = validate_decision_quality(decision)
            assert result.is_valid is True
            assert result.metrics["has_reasoning"] is True
            assert len(result.warnings) == 0  # Clear decisions shouldn't warn

    def test_decision_ambiguity_detection(self):
        """Test detection of ambiguous decisions."""
        ambiguous_decisions = [
            "BUY or SELL, not sure",
            "Maybe HOLD, could be BUY",
            "SELL but also considering BUY",
        ]

        for decision in ambiguous_decisions:
            result = validate_decision_quality(decision)
            # Should still extract first signal
            assert result.metrics["signal"] is not None
            # But should warn about ambiguity
            assert len(result.warnings) > 0

    def test_report_content_variety_indicators(self):
        """Test that reports with varied content structure are recognized."""
        varied_report = """
        # Comprehensive Analysis

        ## Overview
        Multiple content types present.

        ## Data Table
        | Metric | Q1 | Q2 | Q3 | Q4 |
        |--------|----|----|----|----|
        | Revenue| 10M| 12M| 15M| 18M|

        ## Key Points
        - Point 1
        - Point 2
        * Point 3

        ## Details
        """ + "Additional detailed analysis. " * 50

        result = validate_report_completeness(varied_report, min_length=500)

        assert result.is_valid is True
        assert result.metrics["markdown_tables"] > 0
        assert result.metrics["section_headers"] > 0
        assert result.metrics["has_bullet_points"] is True
        # No warnings about lacking structure
        assert not any("structured" in w.lower() for w in result.warnings)


# ============================================================================
# Test State Integrity
# ============================================================================

class TestStateIntegrity:
    """Test integrity and consistency of agent state."""

    def test_all_required_fields_present(self, sample_agent_state_buy):
        """Test that all required fields are present in state."""
        state = sample_agent_state_buy

        required_fields = [
            "company_of_interest",
            "trade_date",
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "investment_debate_state",
            "risk_debate_state",
            "final_trade_decision",
        ]

        for field in required_fields:
            assert field in state, f"Missing required field: {field}"

    def test_debate_state_internal_consistency(self, sample_invest_debate):
        """Test internal consistency of debate state."""
        debate = sample_invest_debate

        result = validate_debate_state(debate, debate_type="invest")

        assert result.is_valid is True
        # Count should match history length (approximately)
        assert result.metrics["count"] > 0
        assert result.metrics["history_length"] > 0

    def test_final_decision_aligns_with_debates(self, sample_agent_state_buy):
        """Test that final decision aligns with debate conclusions."""
        state = sample_agent_state_buy

        invest_debate = state["investment_debate_state"]
        risk_debate = state["risk_debate_state"]
        final_decision = state["final_trade_decision"]

        # Extract all signals
        invest_result = validate_debate_state(invest_debate, debate_type="invest")
        risk_result = validate_debate_state(risk_debate, debate_type="risk")
        final_result = validate_decision_quality(final_decision)

        # All should be BUY for this scenario
        assert invest_result.metrics.get("judge_signal") == "BUY"
        assert risk_result.metrics.get("judge_signal") in ["BUY", "HOLD"]
        assert final_result.metrics["signal"] == "BUY"

    def test_state_preserves_company_context(self, sample_agent_state_buy):
        """Test that company context is preserved throughout state."""
        state = sample_agent_state_buy

        company = state["company_of_interest"]
        trade_date = state["trade_date"]

        # Verify basic context
        assert isinstance(company, str)
        assert len(company) > 0
        assert isinstance(trade_date, str)
        assert len(trade_date) > 0

    def test_debate_history_chronological_consistency(self, sample_invest_debate):
        """Test that debate history appears chronologically consistent."""
        debate = sample_invest_debate

        history = debate["history"]
        count = debate["count"]

        # History should exist if count > 0
        if count > 0:
            assert len(history) > 0

        # If multiple rounds, history should reflect that
        if count >= 2:
            # Should have multiple segments or rounds
            assert len(history) > 50  # Reasonable minimum for 2+ rounds

    def test_type_consistency_across_state(self, sample_agent_state_buy):
        """Test that all fields have correct types."""
        state = sample_agent_state_buy

        # String fields
        string_fields = [
            "company_of_interest",
            "trade_date",
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "final_trade_decision",
        ]

        for field in string_fields:
            if field in state:
                assert isinstance(state[field], str), f"{field} should be string"

        # Dict fields
        dict_fields = ["investment_debate_state", "risk_debate_state"]

        for field in dict_fields:
            if field in state:
                assert isinstance(state[field], dict), f"{field} should be dict"

    def test_empty_state_detection(self):
        """Test detection of completely empty state."""
        empty_state = {}

        result = validate_agent_state(empty_state)

        assert result.is_valid is False
        assert len(result.errors) >= 2  # At least missing company and date
