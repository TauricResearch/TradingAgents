import unittest
from unittest.mock import MagicMock

import pytest

from tradingagents.graph.conditional_logic import ConditionalLogic


def _make_state(messages, debate_state=None, risk_state=None):
    return {
        "messages": messages,
        "investment_debate_state": debate_state
        or {"count": 0, "current_response": ""},
        "risk_debate_state": risk_state
        or {"count": 0, "latest_speaker": ""},
    }


@pytest.mark.unit
class ConditionalLogicConstructorTests(unittest.TestCase):
    def test_default_params(self):
        cl = ConditionalLogic()
        self.assertEqual(cl.max_debate_rounds, 1)
        self.assertEqual(cl.max_risk_discuss_rounds, 1)

    def test_custom_params(self):
        cl = ConditionalLogic(max_debate_rounds=3, max_risk_discuss_rounds=2)
        self.assertEqual(cl.max_debate_rounds, 3)
        self.assertEqual(cl.max_risk_discuss_rounds, 2)


@pytest.mark.unit
class ContinueToolOrClearTests(unittest.TestCase):
    def test_returns_tool_node_when_last_message_has_tool_calls(self):
        msg = MagicMock()
        msg.tool_calls = [{"name": "get_stock_data"}]
        state = _make_state([msg])
        result = ConditionalLogic._continue_tool_or_clear(
            state, "tools_market", "Msg Clear Market"
        )
        self.assertEqual(result, "tools_market")

    def test_returns_clear_node_when_last_message_has_no_tool_calls(self):
        msg = MagicMock()
        msg.tool_calls = []
        state = _make_state([msg])
        result = ConditionalLogic._continue_tool_or_clear(
            state, "tools_news", "Msg Clear News"
        )
        self.assertEqual(result, "Msg Clear News")

    def test_multiple_messages_uses_last(self):
        msg1 = MagicMock()
        msg1.tool_calls = [{"name": "some_tool"}]
        msg2 = MagicMock()
        msg2.tool_calls = []
        state = _make_state([msg1, msg2])
        result = ConditionalLogic._continue_tool_or_clear(
            state, "tools_market", "Msg Clear Market"
        )
        self.assertEqual(result, "Msg Clear Market")


@pytest.mark.unit
class PerAnalystContinueTests(unittest.TestCase):
    def _make_tool_state(self):
        msg = MagicMock()
        msg.tool_calls = [{"name": "x"}]
        return _make_state([msg])

    def _make_clear_state(self):
        msg = MagicMock()
        msg.tool_calls = []
        return _make_state([msg])

    def test_should_continue_market_tool(self):
        cl = ConditionalLogic()
        self.assertEqual(
            cl.should_continue_market(self._make_tool_state()), "tools_market"
        )

    def test_should_continue_market_clear(self):
        cl = ConditionalLogic()
        self.assertEqual(
            cl.should_continue_market(self._make_clear_state()), "Msg Clear Market"
        )

    def test_should_continue_social_tool(self):
        cl = ConditionalLogic()
        self.assertEqual(
            cl.should_continue_social(self._make_tool_state()), "tools_social"
        )

    def test_should_continue_social_clear(self):
        cl = ConditionalLogic()
        self.assertEqual(
            cl.should_continue_social(self._make_clear_state()), "Msg Clear Sentiment"
        )

    def test_should_continue_news_tool(self):
        cl = ConditionalLogic()
        self.assertEqual(
            cl.should_continue_news(self._make_tool_state()), "tools_news"
        )

    def test_should_continue_news_clear(self):
        cl = ConditionalLogic()
        self.assertEqual(
            cl.should_continue_news(self._make_clear_state()), "Msg Clear News"
        )

    def test_should_continue_fundamentals_tool(self):
        cl = ConditionalLogic()
        self.assertEqual(
            cl.should_continue_fundamentals(self._make_tool_state()),
            "tools_fundamentals",
        )

    def test_should_continue_fundamentals_clear(self):
        cl = ConditionalLogic()
        self.assertEqual(
            cl.should_continue_fundamentals(self._make_clear_state()),
            "Msg Clear Fundamentals",
        )

    def test_should_continue_governance_tool(self):
        cl = ConditionalLogic()
        self.assertEqual(
            cl.should_continue_governance(self._make_tool_state()), "tools_governance"
        )

    def test_should_continue_governance_clear(self):
        cl = ConditionalLogic()
        self.assertEqual(
            cl.should_continue_governance(self._make_clear_state()),
            "Msg Clear Governance",
        )

    def test_should_continue_industry_tool(self):
        cl = ConditionalLogic()
        self.assertEqual(
            cl.should_continue_industry(self._make_tool_state()), "tools_industry"
        )

    def test_should_continue_industry_clear(self):
        cl = ConditionalLogic()
        self.assertEqual(
            cl.should_continue_industry(self._make_clear_state()),
            "Msg Clear Industry",
        )


@pytest.mark.unit
class DebateContinueTests(unittest.TestCase):
    def test_debate_returns_research_manager_when_max_rounds_exceeded(self):
        cl = ConditionalLogic(max_debate_rounds=2)
        state = _make_state([], debate_state={"count": 5, "current_response": ""})
        self.assertEqual(cl.should_continue_debate(state), "Research Manager")

    def test_debate_returns_bear_when_bull_just_spoke(self):
        cl = ConditionalLogic()
        state = _make_state(
            [], debate_state={"count": 1, "current_response": "Bull says buy"}
        )
        self.assertEqual(cl.should_continue_debate(state), "Bear Researcher")

    def test_debate_returns_bull_when_bear_just_spoke(self):
        cl = ConditionalLogic()
        state = _make_state(
            [], debate_state={"count": 1, "current_response": "Bear says sell"}
        )
        self.assertEqual(cl.should_continue_debate(state), "Bull Researcher")


@pytest.mark.unit
class RiskDebateContinueTests(unittest.TestCase):
    def test_risk_returns_portfolio_manager_when_max_rounds_exceeded(self):
        cl = ConditionalLogic(max_risk_discuss_rounds=2)
        state = _make_state([], risk_state={"count": 7, "latest_speaker": "Aggressive"})
        self.assertEqual(
            cl.should_continue_risk_analysis(state), "Portfolio Manager"
        )

    def test_risk_returns_conservative_after_aggressive(self):
        cl = ConditionalLogic()
        state = _make_state(
            [], risk_state={"count": 1, "latest_speaker": "Aggressive"}
        )
        self.assertEqual(
            cl.should_continue_risk_analysis(state), "Conservative Analyst"
        )

    def test_risk_returns_neutral_after_conservative(self):
        cl = ConditionalLogic()
        state = _make_state(
            [], risk_state={"count": 2, "latest_speaker": "Conservative"}
        )
        self.assertEqual(
            cl.should_continue_risk_analysis(state), "Neutral Analyst"
        )

    def test_risk_returns_aggressive_after_neutral(self):
        cl = ConditionalLogic()
        state = _make_state([], risk_state={"count": 2, "latest_speaker": "Neutral"})
        self.assertEqual(
            cl.should_continue_risk_analysis(state), "Aggressive Analyst"
        )


if __name__ == "__main__":
    unittest.main()
