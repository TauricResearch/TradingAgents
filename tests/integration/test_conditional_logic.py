import pytest
from unittest.mock import MagicMock
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.agents.utils.agent_states import InvestDebateState, RiskDebateState


class TestConditionalLogicAnalysts:
    def setup_method(self):
        self.logic = ConditionalLogic(max_debate_rounds=2, max_risk_discuss_rounds=2)

    def test_should_continue_market_with_tool_calls(self):
        mock_message = MagicMock()
        mock_message.tool_calls = [{"name": "get_stock_data"}]
        state = {"messages": [mock_message]}

        result = self.logic.should_continue_market(state)
        assert result == "tools_market"

    def test_should_continue_market_without_tool_calls(self):
        mock_message = MagicMock()
        mock_message.tool_calls = []
        state = {"messages": [mock_message]}

        result = self.logic.should_continue_market(state)
        assert result == "Msg Clear Market"

    def test_should_continue_social_with_tool_calls(self):
        mock_message = MagicMock()
        mock_message.tool_calls = [{"name": "get_news"}]
        state = {"messages": [mock_message]}

        result = self.logic.should_continue_social(state)
        assert result == "tools_social"

    def test_should_continue_social_without_tool_calls(self):
        mock_message = MagicMock()
        mock_message.tool_calls = []
        state = {"messages": [mock_message]}

        result = self.logic.should_continue_social(state)
        assert result == "Msg Clear Social"

    def test_should_continue_news_with_tool_calls(self):
        mock_message = MagicMock()
        mock_message.tool_calls = [{"name": "get_global_news"}]
        state = {"messages": [mock_message]}

        result = self.logic.should_continue_news(state)
        assert result == "tools_news"

    def test_should_continue_news_without_tool_calls(self):
        mock_message = MagicMock()
        mock_message.tool_calls = []
        state = {"messages": [mock_message]}

        result = self.logic.should_continue_news(state)
        assert result == "Msg Clear News"

    def test_should_continue_fundamentals_with_tool_calls(self):
        mock_message = MagicMock()
        mock_message.tool_calls = [{"name": "get_balance_sheet"}]
        state = {"messages": [mock_message]}

        result = self.logic.should_continue_fundamentals(state)
        assert result == "tools_fundamentals"

    def test_should_continue_fundamentals_without_tool_calls(self):
        mock_message = MagicMock()
        mock_message.tool_calls = []
        state = {"messages": [mock_message]}

        result = self.logic.should_continue_fundamentals(state)
        assert result == "Msg Clear Fundamentals"


class TestConditionalLogicDebate:
    def setup_method(self):
        self.logic = ConditionalLogic(max_debate_rounds=2, max_risk_discuss_rounds=2)

    def test_should_continue_debate_to_bear(self):
        state = {
            "investment_debate_state": InvestDebateState(
                bull_history="",
                bear_history="",
                history="",
                current_response="Bull: I think we should buy",
                judge_decision="",
                count=1,
            )
        }

        result = self.logic.should_continue_debate(state)
        assert result == "Bear Researcher"

    def test_should_continue_debate_to_bull(self):
        state = {
            "investment_debate_state": InvestDebateState(
                bull_history="",
                bear_history="",
                history="",
                current_response="Bear: I disagree",
                judge_decision="",
                count=2,
            )
        }

        result = self.logic.should_continue_debate(state)
        assert result == "Bull Researcher"

    def test_should_continue_debate_to_manager_max_rounds(self):
        state = {
            "investment_debate_state": InvestDebateState(
                bull_history="",
                bear_history="",
                history="",
                current_response="Bull: Final argument",
                judge_decision="",
                count=4,
            )
        }

        result = self.logic.should_continue_debate(state)
        assert result == "Research Manager"

    def test_debate_rounds_configurable(self):
        logic_one_round = ConditionalLogic(max_debate_rounds=1)
        state = {
            "investment_debate_state": InvestDebateState(
                bull_history="",
                bear_history="",
                history="",
                current_response="Bull: argument",
                judge_decision="",
                count=2,
            )
        }

        result = logic_one_round.should_continue_debate(state)
        assert result == "Research Manager"


class TestConditionalLogicRiskAnalysis:
    def setup_method(self):
        self.logic = ConditionalLogic(max_debate_rounds=2, max_risk_discuss_rounds=2)

    def test_should_continue_risk_to_safe(self):
        state = {
            "risk_debate_state": RiskDebateState(
                risky_history="",
                safe_history="",
                neutral_history="",
                history="",
                latest_speaker="Risky Analyst",
                current_risky_response="",
                current_safe_response="",
                current_neutral_response="",
                judge_decision="",
                count=1,
            )
        }

        result = self.logic.should_continue_risk_analysis(state)
        assert result == "Safe Analyst"

    def test_should_continue_risk_to_neutral(self):
        state = {
            "risk_debate_state": RiskDebateState(
                risky_history="",
                safe_history="",
                neutral_history="",
                history="",
                latest_speaker="Safe Analyst",
                current_risky_response="",
                current_safe_response="",
                current_neutral_response="",
                judge_decision="",
                count=2,
            )
        }

        result = self.logic.should_continue_risk_analysis(state)
        assert result == "Neutral Analyst"

    def test_should_continue_risk_to_risky(self):
        state = {
            "risk_debate_state": RiskDebateState(
                risky_history="",
                safe_history="",
                neutral_history="",
                history="",
                latest_speaker="Neutral Analyst",
                current_risky_response="",
                current_safe_response="",
                current_neutral_response="",
                judge_decision="",
                count=3,
            )
        }

        result = self.logic.should_continue_risk_analysis(state)
        assert result == "Risky Analyst"

    def test_should_continue_risk_to_judge_max_rounds(self):
        state = {
            "risk_debate_state": RiskDebateState(
                risky_history="",
                safe_history="",
                neutral_history="",
                history="",
                latest_speaker="Risky Analyst",
                current_risky_response="",
                current_safe_response="",
                current_neutral_response="",
                judge_decision="",
                count=6,
            )
        }

        result = self.logic.should_continue_risk_analysis(state)
        assert result == "Risk Judge"

    def test_risk_rounds_configurable(self):
        logic_one_round = ConditionalLogic(max_risk_discuss_rounds=1)
        state = {
            "risk_debate_state": RiskDebateState(
                risky_history="",
                safe_history="",
                neutral_history="",
                history="",
                latest_speaker="Neutral Analyst",
                current_risky_response="",
                current_safe_response="",
                current_neutral_response="",
                judge_decision="",
                count=3,
            )
        }

        result = logic_one_round.should_continue_risk_analysis(state)
        assert result == "Risk Judge"
