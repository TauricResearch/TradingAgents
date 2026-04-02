"""Comprehensive unit tests for Fast-Reject [CRITICAL ABORT] feature.

This module tests the critical abort mechanism that short-circuits the trading agent
workflow when catastrophic conditions are detected in market or fundamentals reports.
"""

import pytest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.managers.critical_abort_terminal import create_critical_abort_terminal
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.graph.conditional_logic import ConditionalLogic, CRITICAL_ABORT_NODE


# ---------------------------------------------------------------------------
# Mock Data
# ---------------------------------------------------------------------------

# Market report with abort
market_report_abort = "[CRITICAL ABORT] Reason: Trading halted pending SEC investigation"

# Fundamentals report with abort
fundamentals_report_abort = "[CRITICAL ABORT] Reason: Negative gross margin with bankruptcy filing"

# News report with abort
news_report_abort = "[CRITICAL ABORT] Reason: News analysis failed source-validation twice for AAPL (unknown_source) - Unknown source citations detected"

# Normal market report
normal_market_report = "Market analysis shows strong bullish trend with positive momentum..."

# Normal fundamentals report
normal_fundamentals_report = "Company fundamentals are strong with healthy margins and growth prospects..."

# Bearish but non-terminal reports
strong_sell_market_report = "Market view: strong sell due to weak momentum and downside risk, but no hard-stop event detected."
strong_sell_fundamentals_report = "Fundamentals view: strong sell because margins are compressing, but there is no bankruptcy, delisting, or critical event."

# Real-world false-positive pattern captured from an NVDA run artifact.
nvda_false_positive_market_report = """# NVDA Technical Analysis Report — Final Update

## Executive Summary

NVDA is currently in a correction mode within a broader bullish structural frame. With VIX elevated at 30.6 and the macro regime in TRANSITION, volatility should be expected.

## Risk Framing

Given the elevated volatility, transition regime uncertainty, and bearish momentum, a cautious approach is warranted. Aggressive entries or unwarranted long exposure in a pullback environment under VIX=30.6 is not aligned with the current macro setup.

[CRITICAL ABORT] No catastrophic conditions detected in the pre-loaded data.

## Final Transaction Recommendation

HOLD / CAUTIOUS DEFENSIVE
"""

# Macro regime report
macro_regime_report = "Current macro environment shows stable interest rates and moderate inflation."


# ---------------------------------------------------------------------------
# ConditionalLogic Tests
# ---------------------------------------------------------------------------

class TestConditionalLogicAbortDetection:
    """Tests for critical abort detection in ConditionalLogic."""

    def test_check_critical_abort_detected_in_market_report(self):
        """Verify abort is detected in market_report."""
        cl = ConditionalLogic()
        state = {
            "market_report": market_report_abort,
            "fundamentals_report": normal_fundamentals_report,
        }
        result = cl._check_critical_abort(state, "market_report")
        assert result is True

    def test_check_critical_abort_detected_in_fundamentals_report(self):
        """Verify abort is detected in fundamentals_report."""
        cl = ConditionalLogic()
        state = {
            "market_report": normal_market_report,
            "fundamentals_report": fundamentals_report_abort,
        }
        result = cl._check_critical_abort(state, "fundamentals_report")
        assert result is True

    def test_check_critical_abort_not_detected(self):
        """Verify normal reports pass through without abort detection."""
        cl = ConditionalLogic()
        state = {
            "market_report": normal_market_report,
            "fundamentals_report": normal_fundamentals_report,
        }
        result = cl._check_critical_abort(state, "market_report")
        assert result is False

    def test_check_critical_abort_empty_report(self):
        """Verify abort is not detected when report field is empty."""
        cl = ConditionalLogic()
        state = {
            "market_report": "",
            "fundamentals_report": normal_fundamentals_report,
        }
        result = cl._check_critical_abort(state, "market_report")
        assert result is False

    def test_check_critical_abort_missing_report_field(self):
        """Verify abort is not detected when report field is missing."""
        cl = ConditionalLogic()
        state = {
            "fundamentals_report": normal_fundamentals_report,
        }
        result = cl._check_critical_abort(state, "market_report")
        assert result is False

    def test_check_critical_abort_partial_match(self):
        """Embedded markers must not trigger the terminal abort path."""
        cl = ConditionalLogic()
        state = {
            "market_report": "Some text [CRITICAL ABORT] Reason: Test",
            "fundamentals_report": normal_fundamentals_report,
        }
        result = cl._check_critical_abort(state, "market_report")
        assert result is False

    def test_check_critical_abort_detected_with_leading_whitespace(self):
        """Leading whitespace before the marker is allowed."""
        cl = ConditionalLogic()
        state = {
            "market_report": " \n\t[CRITICAL ABORT] Reason: Trading halted pending SEC investigation",
            "fundamentals_report": normal_fundamentals_report,
        }
        result = cl._check_critical_abort(state, "market_report")
        assert result is True

    def test_check_critical_abort_not_detected_for_nvda_false_positive_phrase(self):
        """A mid-report explanatory sentence must not abort the graph."""
        cl = ConditionalLogic()
        state = {
            "market_report": nvda_false_positive_market_report,
            "fundamentals_report": normal_fundamentals_report,
        }
        result = cl._check_critical_abort(state, "market_report")
        assert result is False

    def test_nvda_market_report_does_not_bypass_debate_flow(self):
        """NVDA-style mid-report marker must not short-circuit the graph."""
        cl = ConditionalLogic()
        state = {
            "market_report": nvda_false_positive_market_report,
            "fundamentals_report": normal_fundamentals_report,
            "investment_debate_state": {
                "history": [],
                "bull_history": [],
                "bear_history": [],
                "current_response": "",
                "judge_decision": "",
                "count": 0,
            },
        }
        assert cl.should_continue_debate(state) == "Bull Researcher"

    def test_check_critical_abort_not_triggered_by_strong_sell_language(self):
        """Sell wording alone must not be treated as a critical abort."""
        cl = ConditionalLogic()
        state = {
            "market_report": strong_sell_market_report,
            "fundamentals_report": strong_sell_fundamentals_report,
        }
        assert cl._check_critical_abort(state, "market_report") is False
        assert cl._check_critical_abort(state, "fundamentals_report") is False


class TestConditionalLogicFlowControl:
    """Tests for flow control when abort is detected."""

    def test_should_continue_debate_with_abort(self):
        """Verify debate is bypassed when abort detected."""
        cl = ConditionalLogic()
        state = {
            "market_report": market_report_abort,
            "fundamentals_report": normal_fundamentals_report,
            "investment_debate_state": {
                "history": [],
                "bull_history": [],
                "bear_history": [],
                "current_response": "",
                "judge_decision": "",
                "count": 0,
            },
        }
        result = cl.should_continue_debate(state)
        assert result == CRITICAL_ABORT_NODE

    def test_should_continue_debate_with_news_abort(self):
        cl = ConditionalLogic()
        state = {
            "market_report": normal_market_report,
            "news_report": news_report_abort,
            "fundamentals_report": normal_fundamentals_report,
            "investment_debate_state": {
                "history": [],
                "bull_history": [],
                "bear_history": [],
                "current_response": "",
                "judge_decision": "",
                "count": 0,
            },
        }
        assert cl.should_continue_debate(state) == CRITICAL_ABORT_NODE

    def test_should_continue_risk_analysis_with_abort(self):
        """Verify risk analysis is bypassed when abort detected."""
        cl = ConditionalLogic()
        state = {
            "market_report": market_report_abort,
            "fundamentals_report": normal_fundamentals_report,
            "risk_debate_state": {
                "history": [],
                "aggressive_history": [],
                "conservative_history": [],
                "neutral_history": [],
                "latest_speaker": "Aggressive",
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "judge_decision": "",
                "count": 0,
            },
        }
        result = cl.should_continue_risk_analysis(state)
        assert result == CRITICAL_ABORT_NODE

    def test_should_continue_risk_analysis_with_news_abort(self):
        cl = ConditionalLogic()
        state = {
            "market_report": normal_market_report,
            "news_report": news_report_abort,
            "fundamentals_report": normal_fundamentals_report,
            "risk_debate_state": {
                "history": [],
                "aggressive_history": [],
                "conservative_history": [],
                "neutral_history": [],
                "latest_speaker": "Aggressive",
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "judge_decision": "",
                "count": 0,
            },
        }
        assert cl.should_continue_risk_analysis(state) == CRITICAL_ABORT_NODE

    def test_normal_flow_without_abort(self):
        """Verify normal flow continues when no abort detected."""
        cl = ConditionalLogic()
        state = {
            "market_report": normal_market_report,
            "fundamentals_report": normal_fundamentals_report,
            "investment_debate_state": {
                "history": [],
                "bull_history": [],
                "bear_history": [],
                "current_response": "",
                "judge_decision": "",
                "count": 0,
            },
        }
        result = cl.should_continue_debate(state)
        assert result == "Bull Researcher"  # Bull speaks first when current_response is empty

    def test_normal_flow_without_abort_risk_analysis(self):
        """Verify normal risk analysis flow continues when no abort detected."""
        cl = ConditionalLogic()
        state = {
            "market_report": normal_market_report,
            "fundamentals_report": normal_fundamentals_report,
            "risk_debate_state": {
                "history": [],
                "aggressive_history": [],
                "conservative_history": [],
                "neutral_history": [],
                "latest_speaker": "Aggressive",
                "count": 0,
            },
        }
        result = cl.should_continue_risk_analysis(state)
        assert result == "Conservative Analyst"

    def test_abort_in_fundamentals_bypasses_debate(self):
        """Verify debate is bypassed when fundamentals report contains abort."""
        cl = ConditionalLogic()
        state = {
            "market_report": normal_market_report,
            "fundamentals_report": fundamentals_report_abort,
            "investment_debate_state": {
                "history": [],
                "bull_history": [],
                "bear_history": [],
                "current_response": "",
                "judge_decision": "",
                "count": 0,
            },
        }
        result = cl.should_continue_debate(state)
        assert result == CRITICAL_ABORT_NODE

    def test_abort_in_fundamentals_bypasses_risk_analysis(self):
        """Verify risk analysis is bypassed when fundamentals report contains abort."""
        cl = ConditionalLogic()
        state = {
            "market_report": normal_market_report,
            "fundamentals_report": fundamentals_report_abort,
            "risk_debate_state": {
                "history": [],
                "aggressive_history": [],
                "conservative_history": [],
                "neutral_history": [],
                "latest_speaker": "Aggressive",
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "judge_decision": "",
                "count": 0,
            },
        }
        result = cl.should_continue_risk_analysis(state)
        assert result == CRITICAL_ABORT_NODE

    def test_abort_in_market_bypasses_risk_analysis(self):
        """Verify market abort bypasses risk analysis."""
        cl = ConditionalLogic()
        state = {
            "market_report": market_report_abort,
            "fundamentals_report": normal_fundamentals_report,
            "risk_debate_state": {
                "history": [],
                "aggressive_history": [],
                "conservative_history": [],
                "neutral_history": [],
                "latest_speaker": "Aggressive",
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "judge_decision": "",
                "count": 0,
            },
        }
        result = cl.should_continue_risk_analysis(state)
        assert result == CRITICAL_ABORT_NODE

    def test_strong_sell_language_does_not_bypass_debate(self):
        """A bearish recommendation without CRITICAL ABORT must continue normal debate flow."""
        cl = ConditionalLogic()
        state = {
            "market_report": strong_sell_market_report,
            "fundamentals_report": normal_fundamentals_report,
            "investment_debate_state": {
                "history": [],
                "bull_history": [],
                "bear_history": [],
                "current_response": "",
                "judge_decision": "",
                "count": 0,
            },
        }
        assert cl.should_continue_debate(state) == "Bull Researcher"

    def test_strong_sell_language_does_not_bypass_risk_analysis(self):
        """A bearish recommendation without CRITICAL ABORT must continue normal risk flow."""
        cl = ConditionalLogic()
        state = {
            "market_report": normal_market_report,
            "fundamentals_report": strong_sell_fundamentals_report,
            "risk_debate_state": {
                "history": [],
                "aggressive_history": [],
                "conservative_history": [],
                "neutral_history": [],
                "latest_speaker": "Aggressive",
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "judge_decision": "",
                "count": 0,
            },
        }
        assert cl.should_continue_risk_analysis(state) == "Conservative Analyst"


class TestCriticalAbortTerminal:
    """Tests for the dedicated abort terminal node."""

    def test_holding_abort_returns_sell_terminal_action(self):
        node = create_critical_abort_terminal()
        result = node(
            {
                "company_of_interest": "AAPL",
                "portfolio_context": "holding",
                "market_report": market_report_abort,
                "fundamentals_report": "",
                "risk_debate_state": {},
            }
        )
        assert result["analysis_status"] == "aborted"
        assert result["terminal_action"] == "SELL"
        assert "Terminal Action: SELL" in result["final_trade_decision"]

    def test_candidate_abort_returns_avoid_terminal_action(self):
        node = create_critical_abort_terminal()
        result = node(
            {
                "company_of_interest": "AAPL",
                "portfolio_context": "candidate",
                "market_report": "",
                "fundamentals_report": fundamentals_report_abort,
                "risk_debate_state": {},
            }
        )
        assert result["analysis_status"] == "aborted"
        assert result["terminal_action"] == "AVOID"
        assert "Terminal Action: AVOID" in result["final_trade_decision"]

    def test_news_abort_is_selected_by_terminal(self):
        node = create_critical_abort_terminal()
        result = node(
            {
                "company_of_interest": "AAPL",
                "portfolio_context": "candidate",
                "market_report": "",
                "news_report": news_report_abort,
                "fundamentals_report": "",
                "risk_debate_state": {},
            }
        )
        assert "news report" in result["final_trade_decision"].lower()
        assert news_report_abort in result["final_trade_decision"]


# ---------------------------------------------------------------------------
# Analyst Report Tests
# ---------------------------------------------------------------------------

class TestMarketAnalystAbortInstructions:
    """Tests for market analyst abort instructions in system prompt."""

    def test_market_analyst_includes_abort_instructions(self):
        """Verify market analyst produces abort report when LLM signals critical abort."""
        # run_tool_loop is the injectable boundary — patch it to return the abort message
        # without making any network calls.
        mock_result = MagicMock()
        mock_result.content = market_report_abort
        mock_result.tool_calls = []

        with patch("tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel", return_value={}), \
             patch("tradingagents.agents.analysts.market_analyst.run_tool_loop", return_value=mock_result):
            market_analyst = create_market_analyst(MagicMock())
            state = {
                "trade_date": "2024-01-01",
                "company_of_interest": "AAPL",
                "messages": [],
            }
            result = market_analyst(state)

        # Verify the report contains abort
        assert "[CRITICAL ABORT]" in result.get("market_report", "")

    def test_market_analyst_abort_conditions(self):
        """Verify market analyst abort conditions are documented in the system prompt constant."""
        market_analyst = create_market_analyst(MagicMock())

        # The system_message is built from adjacent string literals that the compiler
        # concatenates into one big string constant stored in co_consts.
        # Check that at least one constant contains the trigger phrase as a substring.
        assert any(
            "CRITICAL ABORT TRIGGER" in str(c)
            for c in market_analyst.__code__.co_consts
        )


class TestFundamentalsAnalystAbortInstructions:
    """Tests for fundamentals analyst abort instructions in system prompt."""

    def test_fundamentals_analyst_includes_abort_instructions(self):
        """Verify fundamentals analyst produces abort report when LLM signals critical abort."""
        mock_result = MagicMock()
        mock_result.content = fundamentals_report_abort
        mock_result.tool_calls = []

        with patch("tradingagents.agents.analysts.fundamentals_analyst.prefetch_tools_parallel", return_value={}), \
             patch("tradingagents.agents.analysts.fundamentals_analyst.run_tool_loop", return_value=mock_result):
            fundamentals_analyst = create_fundamentals_analyst(MagicMock())
            state = {
                "trade_date": "2024-01-01",
                "company_of_interest": "AAPL",
                "messages": [],
            }
            result = fundamentals_analyst(state)

        # Verify the report contains abort
        assert "[CRITICAL ABORT]" in result.get("fundamentals_report", "")

    def test_fundamentals_analyst_abort_conditions(self):
        """Verify fundamentals analyst abort conditions are documented in the system prompt constant."""
        fundamentals_analyst = create_fundamentals_analyst(MagicMock())

        # The system_message is built from adjacent string literals compiled into one constant.
        assert any(
            "CRITICAL ABORT TRIGGER" in str(c)
            for c in fundamentals_analyst.__code__.co_consts
        )


# ---------------------------------------------------------------------------
# Portfolio Manager Tests
# ---------------------------------------------------------------------------

class TestPortfolioManagerAbortDetection:
    """Tests for portfolio manager abort detection and response."""

    def _make_abort_state(self, market_report, fundamentals_report, news_report=""):
        """Build a minimal state dict suitable for portfolio_manager_node."""
        return {
            "company_of_interest": "AAPL",
            "market_report": market_report,
            "news_report": news_report,
            "fundamentals_report": fundamentals_report,
            "macro_regime_report": macro_regime_report,
            "risk_debate_state": {
                "history": [],
                "aggressive_history": [],
                "conservative_history": [],
                "neutral_history": [],
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "count": 0,
            },
            "sentiment_report": "",
            "investment_plan": "BUY AAPL",
        }

    def test_portfolio_manager_detects_abort(self):
        """Verify PM detects abort and recommends SELL/AVOID."""
        # Create mock LLM *before* the closure so the closure captures it.
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="RECOMMENDATION: SELL - Trading halted pending SEC investigation"
        )
        portfolio_manager = create_portfolio_manager(mock_llm, MagicMock())
        state = self._make_abort_state(market_report_abort, normal_fundamentals_report)

        result = portfolio_manager(state)

        # Verify the closure's LLM was actually called
        assert mock_llm.invoke.called
        # Verify the result contains SELL recommendation
        assert "SELL" in result.get("final_trade_decision", "").upper()

    def test_portfolio_manager_uses_aborting_analyst_report(self):
        """Verify PM decision text reflects the abort reason from the analyst report."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="RECOMMENDATION: SELL - Trading halted pending SEC investigation"
        )
        portfolio_manager = create_portfolio_manager(mock_llm, MagicMock())
        state = self._make_abort_state(market_report_abort, normal_fundamentals_report)

        result = portfolio_manager(state)

        recommendation = result.get("final_trade_decision", "")
        assert "SEC investigation" in recommendation

    def test_portfolio_manager_normal_flow(self):
        """Verify PM works normally without abort."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="RECOMMENDATION: BUY - Strong bullish trend with positive momentum"
        )
        portfolio_manager = create_portfolio_manager(mock_llm, MagicMock())
        state = self._make_abort_state(normal_market_report, normal_fundamentals_report)

        result = portfolio_manager(state)

        # Verify the closure's LLM was actually called
        assert mock_llm.invoke.called
        # Verify the result contains BUY recommendation
        assert "BUY" in result.get("final_trade_decision", "").upper()

    def test_portfolio_manager_uses_fundamentals_abort_report(self):
        """Verify PM uses fundamentals report when it contains abort."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="RECOMMENDATION: AVOID - Negative gross margin with bankruptcy filing"
        )
        portfolio_manager = create_portfolio_manager(mock_llm, MagicMock())
        state = self._make_abort_state(normal_market_report, fundamentals_report_abort)

        result = portfolio_manager(state)

        recommendation = result.get("final_trade_decision", "")
        assert "bankruptcy" in recommendation.lower()

    def test_portfolio_manager_avoids_recommendation(self):
        """Verify PM recommends AVOID when fundamentals report has abort."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="RECOMMENDATION: AVOID - Negative gross margin with bankruptcy filing"
        )
        portfolio_manager = create_portfolio_manager(mock_llm, MagicMock())
        state = self._make_abort_state(normal_market_report, fundamentals_report_abort)

        result = portfolio_manager(state)

        assert "AVOID" in result.get("final_trade_decision", "").upper()

    def test_portfolio_manager_uses_news_abort_report(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="RECOMMENDATION: AVOID - Source validation failed twice"
        )
        portfolio_manager = create_portfolio_manager(mock_llm, MagicMock())
        state = self._make_abort_state(
            normal_market_report,
            normal_fundamentals_report,
            news_report=news_report_abort,
        )

        result = portfolio_manager(state)

        assert "SOURCE VALIDATION FAILED" in result.get("final_trade_decision", "").upper()


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestFastRejectFullFlow:
    """Integration tests for the complete fast-reject short-circuit flow."""

    # Shared initial state template for integration tests
    _base_state = {
        "ticker": "AAPL",
        "trade_date": "2024-01-01",
        "company_of_interest": "AAPL",
        "macro_regime_report": macro_regime_report,
        "risk_debate_state": {
            "history": [],
            "aggressive_history": [],
            "conservative_history": [],
            "neutral_history": [],
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 0,
        },
        "investment_debate_state": {
            "history": [],
            "bull_history": [],
            "bear_history": [],
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        },
        "news_report": "",
        "sentiment_report": "",
        "investment_plan": "BUY AAPL",
        "messages": [],
    }

    def _make_state(self, market_report, fundamentals_report):
        return {**self._base_state, "market_report": market_report, "fundamentals_report": fundamentals_report}

    def test_fast_reject_full_flow(self):
        """Test the complete short-circuit flow from analyst to portfolio manager."""
        mock_market_ai = MagicMock()
        mock_market_ai.content = market_report_abort
        mock_market_ai.tool_calls = []

        state = self._make_state(market_report_abort, normal_fundamentals_report)

        # Patch network-calling helpers; control analyst output via run_tool_loop mock
        with patch("tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel", return_value={}), \
             patch("tradingagents.agents.analysts.market_analyst.run_tool_loop", return_value=mock_market_ai):
            market_analyst = create_market_analyst(MagicMock())
            analyst_result = market_analyst(state)
            state = {**state, **analyst_result}  # merge so all keys are preserved

        # Verify market report contains abort
        assert "[CRITICAL ABORT]" in state.get("market_report", "")

        abort_terminal = create_critical_abort_terminal()
        abort_result = abort_terminal(state)
        state = {**state, **abort_result}

        assert "SELL" in state.get("final_trade_decision", "").upper()
        assert state.get("analysis_status") == "aborted"

        # Verify conditional logic would bypass debate and risk analysis
        cl = ConditionalLogic()
        assert cl.should_continue_debate(state) == CRITICAL_ABORT_NODE
        assert cl.should_continue_risk_analysis(state) == CRITICAL_ABORT_NODE

    def test_fast_reject_fundamentals_flow(self):
        """Test the complete short-circuit flow with fundamentals abort."""
        mock_market_ai = MagicMock()
        mock_market_ai.content = normal_market_report
        mock_market_ai.tool_calls = []

        state = self._make_state(normal_market_report, fundamentals_report_abort)

        with patch("tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel", return_value={}), \
             patch("tradingagents.agents.analysts.market_analyst.run_tool_loop", return_value=mock_market_ai):
            market_analyst = create_market_analyst(MagicMock())
            analyst_result = market_analyst(state)
            state = {**state, **analyst_result}

        # Market report should be normal (abort is in fundamentals)
        assert "[CRITICAL ABORT]" not in state.get("market_report", "")
        # Fundamentals abort must survive the merge
        assert "[CRITICAL ABORT]" in state.get("fundamentals_report", "")

        abort_terminal = create_critical_abort_terminal()
        abort_result = abort_terminal({**state, "portfolio_context": "candidate"})
        state = {**state, **abort_result}

        assert "AVOID" in state.get("final_trade_decision", "").upper()
        assert state.get("analysis_status") == "aborted"

        cl = ConditionalLogic()
        assert cl.should_continue_debate(state) == CRITICAL_ABORT_NODE
        assert cl.should_continue_risk_analysis(state) == CRITICAL_ABORT_NODE

    def test_fast_reject_normal_flow(self):
        """Test the complete flow without abort."""
        mock_market_ai = MagicMock()
        mock_market_ai.content = normal_market_report
        mock_market_ai.tool_calls = []

        state = self._make_state(normal_market_report, normal_fundamentals_report)

        with patch("tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel", return_value={}), \
             patch("tradingagents.agents.analysts.market_analyst.run_tool_loop", return_value=mock_market_ai):
            market_analyst = create_market_analyst(MagicMock())
            analyst_result = market_analyst(state)
            state = {**state, **analyst_result}

        assert "[CRITICAL ABORT]" not in state.get("market_report", "")

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="RECOMMENDATION: BUY - Strong bullish trend with positive momentum"
        )
        portfolio_manager = create_portfolio_manager(mock_llm, MagicMock())
        pm_result = portfolio_manager(state)
        state = {**state, **pm_result}

        assert "BUY" in state.get("final_trade_decision", "").upper()

        # Normal flow: conditional logic must NOT route directly to Portfolio Manager
        cl = ConditionalLogic()
        debate_result = cl.should_continue_debate(state)
        risk_result = cl.should_continue_risk_analysis(state)

        assert debate_result != "Portfolio Manager"
        assert risk_result != "Portfolio Manager"
