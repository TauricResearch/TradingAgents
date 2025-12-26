"""
Test suite for Output Validation Utilities.

This module tests:
1. ValidationResult dataclass behavior
2. Report completeness validation (length, markdown, sections)
3. Decision quality validation (signal extraction, reasoning)
4. Debate state validation (history, count, judge_decision)
5. Complete agent state validation (orchestration)

All tests use mocked data (no real API calls).
"""

import pytest
from typing import Dict, Any

from tradingagents.utils.output_validator import (
    ValidationResult,
    validate_report_completeness,
    validate_decision_quality,
    validate_debate_state,
    validate_agent_state,
)

pytestmark = pytest.mark.unit


# ============================================================================
# Test ValidationResult Dataclass
# ============================================================================

class TestValidationResult:
    """Test ValidationResult dataclass behavior."""

    def test_default_valid_result(self):
        """Test ValidationResult defaults to valid with empty lists."""
        result = ValidationResult(is_valid=True)

        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.metrics == {}

    def test_add_error_marks_invalid(self):
        """Test that add_error() marks result as invalid."""
        result = ValidationResult(is_valid=True)
        result.add_error("Something went wrong")

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0] == "Something went wrong"

    def test_add_warning_keeps_valid(self):
        """Test that add_warning() doesn't change validity."""
        result = ValidationResult(is_valid=True)
        result.add_warning("This could be better")

        assert result.is_valid is True
        assert len(result.warnings) == 1
        assert result.warnings[0] == "This could be better"

    def test_add_metric(self):
        """Test that add_metric() stores key-value pairs."""
        result = ValidationResult(is_valid=True)
        result.add_metric("length", 500)
        result.add_metric("signal", "BUY")

        assert result.metrics["length"] == 500
        assert result.metrics["signal"] == "BUY"

    def test_multiple_errors_and_warnings(self):
        """Test accumulating multiple errors and warnings."""
        result = ValidationResult(is_valid=True)
        result.add_error("Error 1")
        result.add_error("Error 2")
        result.add_warning("Warning 1")
        result.add_warning("Warning 2")

        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 2


# ============================================================================
# Test Report Validation
# ============================================================================

class TestReportValidation:
    """Test validate_report_completeness() function."""

    def test_valid_report_passes(self):
        """Test that a valid report passes validation."""
        report = "# Market Analysis\n\n" + "This is a comprehensive report. " * 50

        result = validate_report_completeness(report, min_length=500)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.metrics["length"] > 500

    def test_none_report_fails(self):
        """Test that None report fails validation."""
        result = validate_report_completeness(None)

        assert result.is_valid is False
        assert "None" in result.errors[0]

    def test_empty_report_fails(self):
        """Test that empty report fails validation."""
        result = validate_report_completeness("")

        assert result.is_valid is False
        assert "empty" in result.errors[0].lower()

    def test_short_report_fails(self):
        """Test that report below min_length fails."""
        short_report = "Too short"

        result = validate_report_completeness(short_report, min_length=500)

        assert result.is_valid is False
        assert any("minimum" in err.lower() for err in result.errors)
        assert result.metrics["length"] < 500

    def test_wrong_type_fails(self):
        """Test that non-string report fails validation."""
        result = validate_report_completeness(123)

        assert result.is_valid is False
        assert "string" in result.errors[0].lower()

    def test_markdown_table_detection(self):
        """Test detection of markdown tables."""
        report_with_table = """
        # Analysis

        | Metric | Value |
        |--------|-------|
        | Price  | $100  |
        | Volume | 1M    |
        """ + "Additional text. " * 50

        result = validate_report_completeness(
            report_with_table,
            min_length=200,
            require_markdown_tables=True
        )

        assert result.is_valid is True
        assert result.metrics["markdown_tables"] > 0

    def test_missing_markdown_table_fails_when_required(self):
        """Test that missing markdown tables fails when required."""
        report = "# Analysis\n\n" + "No tables here. " * 50

        result = validate_report_completeness(
            report,
            min_length=200,
            require_markdown_tables=True
        )

        assert result.is_valid is False
        assert any("table" in err.lower() for err in result.errors)

    def test_section_header_detection(self):
        """Test detection of section headers."""
        report_with_headers = """
        # Main Title
        ## Subsection
        ### Details

        Content here.
        """ + "More content. " * 50

        result = validate_report_completeness(
            report_with_headers,
            min_length=200,
            require_sections=True
        )

        assert result.is_valid is True
        assert result.metrics["section_headers"] >= 3

    def test_missing_sections_fails_when_required(self):
        """Test that missing sections fails when required."""
        report = "Just plain text. " * 50

        result = validate_report_completeness(
            report,
            min_length=200,
            require_sections=True
        )

        assert result.is_valid is False
        assert any("section" in err.lower() for err in result.errors)

    def test_short_report_warning(self):
        """Test warning for relatively short reports."""
        # Report is above min but below 1.5x min
        report = "Short but valid. " * 40  # ~680 chars

        result = validate_report_completeness(report, min_length=500)

        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert any("short" in warn.lower() for warn in result.warnings)

    def test_bullet_point_detection(self):
        """Test detection of bullet points."""
        report_with_bullets = """
        # Analysis

        - Point 1
        - Point 2
        * Point 3

        """ + "Additional content. " * 50

        result = validate_report_completeness(report_with_bullets, min_length=200)

        assert result.metrics["has_bullet_points"] is True

    def test_unstructured_content_warning(self):
        """Test warning for content lacking structure."""
        unstructured_report = "Just a long stream of text without any structure. " * 50

        result = validate_report_completeness(unstructured_report, min_length=500)

        assert result.is_valid is True
        assert any("structured" in warn.lower() for warn in result.warnings)


# ============================================================================
# Test Decision Validation
# ============================================================================

class TestDecisionValidation:
    """Test validate_decision_quality() function."""

    def test_valid_buy_decision(self):
        """Test that valid BUY decision passes."""
        decision = "BUY: Strong fundamentals and positive momentum"

        result = validate_decision_quality(decision)

        assert result.is_valid is True
        assert result.metrics["signal"] == "BUY"
        assert result.metrics["has_reasoning"] is True

    def test_valid_sell_decision(self):
        """Test that valid SELL decision passes."""
        decision = "SELL: Overvalued with deteriorating fundamentals"

        result = validate_decision_quality(decision)

        assert result.is_valid is True
        assert result.metrics["signal"] == "SELL"

    def test_valid_hold_decision(self):
        """Test that valid HOLD decision passes."""
        decision = "HOLD: Mixed signals, awaiting clarity"

        result = validate_decision_quality(decision)

        assert result.is_valid is True
        assert result.metrics["signal"] == "HOLD"

    def test_case_insensitive_signal_extraction(self):
        """Test that signals are extracted case-insensitively."""
        decisions = [
            "buy the stock",
            "BUY the stock",
            "Buy the stock",
            "We should buy",
        ]

        for decision in decisions:
            result = validate_decision_quality(decision)
            assert result.metrics["signal"] == "BUY"

    def test_none_decision_fails(self):
        """Test that None decision fails validation."""
        result = validate_decision_quality(None)

        assert result.is_valid is False
        assert "None" in result.errors[0]

    def test_empty_decision_fails(self):
        """Test that empty decision fails validation."""
        result = validate_decision_quality("")

        assert result.is_valid is False
        assert "empty" in result.errors[0].lower()

    def test_no_signal_fails(self):
        """Test that decision without signal fails."""
        decision = "This is a decision without a clear signal"

        result = validate_decision_quality(decision)

        assert result.is_valid is False
        assert any("signal" in err.lower() for err in result.errors)
        assert result.metrics["signal"] is None

    def test_wrong_type_fails(self):
        """Test that non-string decision fails."""
        result = validate_decision_quality({"decision": "BUY"})

        assert result.is_valid is False
        assert "string" in result.errors[0].lower()

    def test_multiple_signals_warning(self):
        """Test warning for multiple conflicting signals."""
        decision = "BUY or maybe SELL, hard to decide, could HOLD"

        result = validate_decision_quality(decision)

        # Should still extract first signal
        assert result.metrics["signal"] == "BUY"
        # But warn about conflicts
        assert len(result.warnings) > 0
        assert any("conflicting" in warn.lower() for warn in result.warnings)

    def test_short_decision_warning(self):
        """Test warning for very short decisions."""
        decision = "BUY"

        result = validate_decision_quality(decision)

        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert any("short" in warn.lower() for warn in result.warnings)

    def test_decision_with_reasoning_markers(self):
        """Test that reasoning markers are detected."""
        decisions_with_reasoning = [
            "BUY: Strong fundamentals",
            "SELL. Company is overvalued.",
            "HOLD because market is uncertain",
        ]

        for decision in decisions_with_reasoning:
            result = validate_decision_quality(decision)
            assert result.metrics["has_reasoning"] is True

    def test_signal_count_metric(self):
        """Test that signal_count metric is accurate."""
        decision = "BUY BUY BUY! Strong signal to buy"

        result = validate_decision_quality(decision)

        assert result.metrics["signal_count"] == 4
        assert result.metrics["signal"] == "BUY"


# ============================================================================
# Test Debate State Validation
# ============================================================================

class TestDebateStateValidation:
    """Test validate_debate_state() function."""

    def test_valid_invest_debate_state(self):
        """Test that valid invest debate state passes."""
        debate_state = {
            "history": "Round 1: Bull argues...\nRound 2: Bear counters...",
            "count": 2,
            "judge_decision": "BUY: Bulls made stronger case",
            "bull_history": "Bull argument",
            "bear_history": "Bear argument",
        }

        result = validate_debate_state(debate_state, debate_type="invest")

        assert result.is_valid is True
        assert result.metrics["history_length"] > 0
        assert result.metrics["count"] == 2
        assert result.metrics["judge_signal"] == "BUY"

    def test_valid_risk_debate_state(self):
        """Test that valid risk debate state passes."""
        debate_state = {
            "history": "Round 1: Risky argues...\nRound 2: Safe counters...",
            "count": 2,
            "judge_decision": "HOLD: Balanced risk profile",
            "risky_history": "Risky argument",
            "safe_history": "Safe argument",
            "neutral_history": "Neutral argument",
        }

        result = validate_debate_state(debate_state, debate_type="risk")

        assert result.is_valid is True
        assert result.metrics["count"] == 2

    def test_none_debate_state_fails(self):
        """Test that None debate state fails."""
        result = validate_debate_state(None)

        assert result.is_valid is False
        assert "None" in result.errors[0]

    def test_wrong_type_fails(self):
        """Test that non-dict debate state fails."""
        result = validate_debate_state("not a dict")

        assert result.is_valid is False
        assert "dict" in result.errors[0].lower()

    def test_missing_required_fields_fails(self):
        """Test that missing required fields fails."""
        incomplete_state = {
            "history": "Some history",
            # Missing count and judge_decision
        }

        result = validate_debate_state(incomplete_state)

        assert result.is_valid is False
        assert any("missing" in err.lower() for err in result.errors)

    def test_invalid_debate_type_fails(self):
        """Test that unknown debate type fails."""
        debate_state = {
            "history": "History",
            "count": 1,
            "judge_decision": "BUY",
        }

        result = validate_debate_state(debate_state, debate_type="unknown")

        assert result.is_valid is False
        assert "unknown" in result.errors[0].lower()

    def test_empty_history_warning(self):
        """Test warning for empty history."""
        debate_state = {
            "history": "",
            "count": 0,
            "judge_decision": "HOLD",
        }

        result = validate_debate_state(debate_state)

        assert result.is_valid is True
        assert any("empty" in warn.lower() for warn in result.warnings)

    def test_negative_count_fails(self):
        """Test that negative count fails."""
        debate_state = {
            "history": "History",
            "count": -1,
            "judge_decision": "BUY",
        }

        result = validate_debate_state(debate_state)

        assert result.is_valid is False
        assert any("negative" in err.lower() for err in result.errors)

    def test_high_count_warning(self):
        """Test warning for very high debate count."""
        debate_state = {
            "history": "Long debate...",
            "count": 15,
            "judge_decision": "SELL",
        }

        result = validate_debate_state(debate_state)

        assert result.is_valid is True
        assert any("high" in warn.lower() for warn in result.warnings)

    def test_invalid_judge_decision_warning(self):
        """Test warning for poor quality judge decision."""
        debate_state = {
            "history": "History",
            "count": 2,
            "judge_decision": "No clear signal here",
        }

        result = validate_debate_state(debate_state)

        assert result.is_valid is True
        assert len(result.warnings) > 0

    def test_optional_fields_metric(self):
        """Test that optional fields are counted."""
        debate_state = {
            "history": "History",
            "count": 1,
            "judge_decision": "BUY",
            "bull_history": "Bull",
            "bear_history": "Bear",
        }

        result = validate_debate_state(debate_state, debate_type="invest")

        assert result.metrics["optional_fields_present"] >= 2

    def test_wrong_history_type_fails(self):
        """Test that non-string history fails."""
        debate_state = {
            "history": 123,
            "count": 1,
            "judge_decision": "BUY",
        }

        result = validate_debate_state(debate_state)

        assert result.is_valid is False
        assert any("string" in err.lower() for err in result.errors)

    def test_wrong_count_type_fails(self):
        """Test that non-int count fails."""
        debate_state = {
            "history": "History",
            "count": "two",
            "judge_decision": "BUY",
        }

        result = validate_debate_state(debate_state)

        assert result.is_valid is False
        assert any("int" in err.lower() for err in result.errors)


# ============================================================================
# Test Agent State Validation
# ============================================================================

class TestAgentStateValidation:
    """Test validate_agent_state() function."""

    def test_valid_complete_agent_state(self):
        """Test that complete valid agent state passes."""
        state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "market_report": "# Market Analysis\n\n" + "Detailed analysis. " * 100,
            "sentiment_report": "# Sentiment Report\n\n" + "Social sentiment. " * 100,
            "news_report": "# News Report\n\n" + "Latest news. " * 100,
            "fundamentals_report": "# Fundamentals\n\n" + "Financial data. " * 100,
            "investment_debate_state": {
                "history": "Debate history",
                "count": 3,
                "judge_decision": "BUY: Strong case",
            },
            "risk_debate_state": {
                "history": "Risk debate",
                "count": 2,
                "judge_decision": "HOLD: Moderate risk",
            },
            "final_trade_decision": "BUY: All signals align positively",
        }

        result = validate_agent_state(state)

        assert result.is_valid is True
        assert result.metrics["company_of_interest"] == "AAPL"
        assert result.metrics["trade_date"] == "2024-01-15"
        assert result.metrics["reports_present"] == 4
        assert result.metrics["final_signal"] == "BUY"

    def test_none_state_fails(self):
        """Test that None state fails."""
        result = validate_agent_state(None)

        assert result.is_valid is False
        assert "None" in result.errors[0]

    def test_wrong_type_fails(self):
        """Test that non-dict state fails."""
        result = validate_agent_state("not a dict")

        assert result.is_valid is False
        assert "dict" in result.errors[0].lower()

    def test_missing_company_fails(self):
        """Test that missing company fails."""
        state = {
            "trade_date": "2024-01-15",
        }

        result = validate_agent_state(state)

        assert result.is_valid is False
        assert any("company" in err.lower() for err in result.errors)

    def test_missing_trade_date_fails(self):
        """Test that missing trade date fails."""
        state = {
            "company_of_interest": "AAPL",
        }

        result = validate_agent_state(state)

        assert result.is_valid is False
        assert any("trade_date" in err.lower() for err in result.errors)

    def test_incomplete_reports_warning(self):
        """Test warning when some reports are missing."""
        state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "market_report": "Market analysis. " * 100,
            # Missing other reports
        }

        result = validate_agent_state(state)

        # Basic fields present, so valid
        assert result.is_valid is True
        # But warn about missing reports
        assert len(result.warnings) > 0
        assert result.metrics["reports_present"] < 4

    def test_invalid_report_warning(self):
        """Test warning for invalid report content."""
        state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "market_report": "Too short",  # Below min length
        }

        result = validate_agent_state(state)

        assert result.is_valid is True
        assert any("market_report" in warn.lower() for warn in result.warnings)

    def test_invalid_invest_debate_warning(self):
        """Test warning for invalid investment debate."""
        state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "investment_debate_state": {
                # Missing required fields
                "history": "History",
            },
        }

        result = validate_agent_state(state)

        assert result.is_valid is True
        assert any("investment debate" in warn.lower() for warn in result.warnings)

    def test_invalid_risk_debate_warning(self):
        """Test warning for invalid risk debate."""
        state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "risk_debate_state": {
                "count": -1,  # Invalid
            },
        }

        result = validate_agent_state(state)

        assert result.is_valid is True
        assert any("risk debate" in warn.lower() for warn in result.warnings)

    def test_invalid_final_decision_warning(self):
        """Test warning for invalid final decision."""
        state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "final_trade_decision": "No clear signal",
        }

        result = validate_agent_state(state)

        assert result.is_valid is True
        assert any("final decision" in warn.lower() for warn in result.warnings)

    def test_incomplete_state_warning(self):
        """Test warning for very incomplete state."""
        state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            # No debates or decision
        }

        result = validate_agent_state(state)

        assert result.is_valid is True
        assert any("incomplete" in warn.lower() for warn in result.warnings)

    def test_reports_count_metrics(self):
        """Test that report counts are tracked."""
        state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "market_report": "Report. " * 100,
            "sentiment_report": "Report. " * 100,
        }

        result = validate_agent_state(state)

        assert result.metrics["reports_present"] == 2
        assert result.metrics["total_reports_expected"] == 4
