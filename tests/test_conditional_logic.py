"""Tests for ConditionalLogic graph routing.

Validates all should_continue_* methods to ensure correct routing based
on message tool calls, debate counts, and latest speaker state.
"""

from unittest.mock import MagicMock

import pytest

from tradingagents.graph.conditional_logic import ConditionalLogic


def _msg_with_tool_calls():
    msg = MagicMock()
    msg.tool_calls = [{"name": "get_stock_data", "args": {}}]
    return msg


def _msg_without_tool_calls():
    msg = MagicMock()
    msg.tool_calls = []
    return msg


def _analyst_state(has_tool_calls=False):
    msg = _msg_with_tool_calls() if has_tool_calls else _msg_without_tool_calls()
    return {"messages": [msg]}


# ---------------------------------------------------------------------------
# Analyst routing: should_continue_market / social / news / fundamentals
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalystRouting:
    def test_market_routes_to_tools_when_tool_calls(self):
        cl = ConditionalLogic()
        assert cl.should_continue_market(_analyst_state(True)) == "tools_market"

    def test_market_routes_to_clear_when_no_tool_calls(self):
        cl = ConditionalLogic()
        assert cl.should_continue_market(_analyst_state(False)) == "Msg Clear Market"

    def test_social_routes_to_tools_when_tool_calls(self):
        cl = ConditionalLogic()
        assert cl.should_continue_social(_analyst_state(True)) == "tools_social"

    def test_social_routes_to_clear_when_no_tool_calls(self):
        cl = ConditionalLogic()
        assert cl.should_continue_social(_analyst_state(False)) == "Msg Clear Sentiment"

    def test_news_routes_to_tools_when_tool_calls(self):
        cl = ConditionalLogic()
        assert cl.should_continue_news(_analyst_state(True)) == "tools_news"

    def test_news_routes_to_clear_when_no_tool_calls(self):
        cl = ConditionalLogic()
        assert cl.should_continue_news(_analyst_state(False)) == "Msg Clear News"

    def test_fundamentals_routes_to_tools_when_tool_calls(self):
        cl = ConditionalLogic()
        assert cl.should_continue_fundamentals(_analyst_state(True)) == "tools_fundamentals"

    def test_fundamentals_routes_to_clear_when_no_tool_calls(self):
        cl = ConditionalLogic()
        assert cl.should_continue_fundamentals(_analyst_state(False)) == "Msg Clear Fundamentals"


# ---------------------------------------------------------------------------
# Investment debate routing: should_continue_debate
# ---------------------------------------------------------------------------

def _debate_state(count, current_response=""):
    return {
        "messages": [],
        "investment_debate_state": {
            "count": count,
            "current_response": current_response,
            "bull_history": "",
            "bear_history": "",
            "history": "",
            "judge_decision": "",
        },
    }


@pytest.mark.unit
class TestDebateRouting:
    def test_routes_to_research_manager_when_max_rounds_reached(self):
        cl = ConditionalLogic(max_debate_rounds=1)
        state = _debate_state(count=2, current_response="Bull: something")
        assert cl.should_continue_debate(state) == "Research Manager"

    def test_routes_to_research_manager_when_exceeds_max_rounds(self):
        cl = ConditionalLogic(max_debate_rounds=2)
        state = _debate_state(count=4, current_response="Bear: something")
        assert cl.should_continue_debate(state) == "Research Manager"

    def test_routes_to_bear_after_bull_speaks(self):
        cl = ConditionalLogic(max_debate_rounds=3)
        state = _debate_state(count=1, current_response="Bull: AI is the future.")
        assert cl.should_continue_debate(state) == "Bear Researcher"

    def test_routes_to_bull_after_bear_speaks(self):
        cl = ConditionalLogic(max_debate_rounds=3)
        state = _debate_state(count=1, current_response="Bear: Market is overvalued.")
        assert cl.should_continue_debate(state) == "Bull Researcher"

    def test_routes_to_bull_when_no_response_yet(self):
        cl = ConditionalLogic(max_debate_rounds=3)
        state = _debate_state(count=0, current_response="")
        assert cl.should_continue_debate(state) == "Bull Researcher"

    def test_multi_round_config(self):
        cl = ConditionalLogic(max_debate_rounds=5)
        state = _debate_state(count=9, current_response="Bull: final point")
        assert cl.should_continue_debate(state) == "Bear Researcher"
        state2 = _debate_state(count=10, current_response="Bear: something")
        assert cl.should_continue_debate(state2) == "Research Manager"


# ---------------------------------------------------------------------------
# Risk analysis routing: should_continue_risk_analysis
# ---------------------------------------------------------------------------

def _risk_state(count, latest_speaker=""):
    return {
        "messages": [],
        "risk_debate_state": {
            "count": count,
            "latest_speaker": latest_speaker,
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
        },
    }


@pytest.mark.unit
class TestRiskAnalysisRouting:
    def test_routes_to_portfolio_manager_when_max_rounds_reached(self):
        cl = ConditionalLogic(max_risk_discuss_rounds=1)
        state = _risk_state(count=3, latest_speaker="Neutral")
        assert cl.should_continue_risk_analysis(state) == "Portfolio Manager"

    def test_routes_to_portfolio_manager_when_exceeds_max_rounds(self):
        cl = ConditionalLogic(max_risk_discuss_rounds=2)
        state = _risk_state(count=6, latest_speaker="Aggressive")
        assert cl.should_continue_risk_analysis(state) == "Portfolio Manager"

    def test_routes_to_conservative_after_aggressive(self):
        cl = ConditionalLogic(max_risk_discuss_rounds=3)
        state = _risk_state(count=1, latest_speaker="Aggressive")
        assert cl.should_continue_risk_analysis(state) == "Conservative Analyst"

    def test_routes_to_neutral_after_conservative(self):
        cl = ConditionalLogic(max_risk_discuss_rounds=3)
        state = _risk_state(count=2, latest_speaker="Conservative")
        assert cl.should_continue_risk_analysis(state) == "Neutral Analyst"

    def test_routes_to_aggressive_after_neutral(self):
        cl = ConditionalLogic(max_risk_discuss_rounds=3)
        state = _risk_state(count=3, latest_speaker="Neutral")
        assert cl.should_continue_risk_analysis(state) == "Aggressive Analyst"

    def test_routes_to_aggressive_when_no_speaker_yet(self):
        cl = ConditionalLogic(max_risk_discuss_rounds=3)
        state = _risk_state(count=0, latest_speaker="")
        assert cl.should_continue_risk_analysis(state) == "Aggressive Analyst"

    def test_multi_round_risk_config(self):
        cl = ConditionalLogic(max_risk_discuss_rounds=3)
        state = _risk_state(count=8, latest_speaker="Conservative")
        assert cl.should_continue_risk_analysis(state) == "Neutral Analyst"
        state2 = _risk_state(count=9, latest_speaker="Neutral")
        assert cl.should_continue_risk_analysis(state2) == "Portfolio Manager"


# ---------------------------------------------------------------------------
# Constructor defaults
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestConditionalLogicDefaults:
    def test_default_max_debate_rounds(self):
        cl = ConditionalLogic()
        assert cl.max_debate_rounds == 1

    def test_default_max_risk_rounds(self):
        cl = ConditionalLogic()
        assert cl.max_risk_discuss_rounds == 1

    def test_custom_config(self):
        cl = ConditionalLogic(max_debate_rounds=5, max_risk_discuss_rounds=10)
        assert cl.max_debate_rounds == 5
        assert cl.max_risk_discuss_rounds == 10
