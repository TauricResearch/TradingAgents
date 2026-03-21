"""Tests for conditional logic routing."""
from unittest.mock import MagicMock


def test_debate_routes_yes_to_no():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = {"investment_debate_state": {"count": 1, "latest_speaker": "YES Advocate"}}
    assert cl.should_continue_debate(state) == "NO Advocate"


def test_debate_routes_no_to_timing():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = {"investment_debate_state": {"count": 2, "latest_speaker": "NO Advocate"}}
    assert cl.should_continue_debate(state) == "Timing Advocate"


def test_debate_routes_timing_to_yes():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=2, max_risk_discuss_rounds=1)
    state = {"investment_debate_state": {"count": 3, "latest_speaker": "Timing Advocate"}}
    assert cl.should_continue_debate(state) == "YES Advocate"


def test_debate_routes_to_manager_after_max_rounds():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = {"investment_debate_state": {"count": 3, "latest_speaker": "Timing Advocate"}}
    assert cl.should_continue_debate(state) == "Research Manager"


def test_debate_initial_routes_to_yes():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = {"investment_debate_state": {"count": 0, "latest_speaker": ""}}
    assert cl.should_continue_debate(state) == "YES Advocate"


def test_should_continue_odds_routes_to_tools():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    msg = MagicMock()
    msg.tool_calls = [{"name": "get_market_data", "args": {}}]
    state = {"messages": [msg]}
    assert cl.should_continue_odds(state) == "tools_odds"


def test_should_continue_odds_routes_to_clear():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    msg = MagicMock()
    msg.tool_calls = []
    state = {"messages": [msg]}
    assert cl.should_continue_odds(state) == "Msg Clear Odds"


def test_risk_routes_aggressive_to_conservative():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = {"risk_debate_state": {"count": 1, "latest_speaker": "Aggressive Analyst"}}
    assert cl.should_continue_risk_analysis(state) == "Conservative Analyst"


def test_risk_routes_to_judge_after_max():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    cl = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = {"risk_debate_state": {"count": 3, "latest_speaker": "Neutral Analyst"}}
    assert cl.should_continue_risk_analysis(state) == "Risk Judge"
