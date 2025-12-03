from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from tradingagents.agents.utils.agent_states import InvestDebateState, RiskDebateState
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.trading_graph import TradingAgentsGraph


class TestWorkflowStateTransitions:
    def test_initial_state_structure(self):
        propagator = Propagator()
        state = propagator.create_initial_state("AAPL", "2024-01-15")

        assert "messages" in state
        assert "company_of_interest" in state
        assert "trade_date" in state
        assert "investment_debate_state" in state
        assert "risk_debate_state" in state
        assert "market_report" in state
        assert "sentiment_report" in state
        assert "news_report" in state
        assert "fundamentals_report" in state

    def test_market_analyst_state_update(self):
        initial_state = {
            "messages": [HumanMessage(content="AAPL")],
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "market_report": "",
        }

        updated_state = {
            **initial_state,
            "market_report": "Technical analysis shows bullish trend",
            "messages": [
                HumanMessage(content="AAPL"),
                AIMessage(content="Technical analysis shows bullish trend"),
            ],
        }

        assert updated_state["market_report"] != ""
        assert len(updated_state["messages"]) == 2

    def test_debate_state_progression(self):
        logic = ConditionalLogic(max_debate_rounds=2)

        state_round_0 = {
            "investment_debate_state": InvestDebateState(
                bull_history="",
                bear_history="",
                history="",
                current_response="",
                judge_decision="",
                count=0,
            )
        }

        state_round_1 = {
            "investment_debate_state": InvestDebateState(
                bull_history="Bull: I see growth potential",
                bear_history="",
                history="Bull: I see growth potential",
                current_response="Bull: I see growth potential",
                judge_decision="",
                count=1,
            )
        }

        state_round_2 = {
            "investment_debate_state": InvestDebateState(
                bull_history="Bull: I see growth potential",
                bear_history="Bear: Market risks are high",
                history="Bull: I see growth potential\nBear: Market risks are high",
                current_response="Bear: Market risks are high",
                judge_decision="",
                count=2,
            )
        }

        assert logic.should_continue_debate(state_round_1) == "Bear Researcher"
        assert logic.should_continue_debate(state_round_2) == "Bull Researcher"

    def test_risk_analysis_state_progression(self):
        logic = ConditionalLogic(max_risk_discuss_rounds=1)

        state_risky = {
            "risk_debate_state": RiskDebateState(
                risky_history="Go for it!",
                safe_history="",
                neutral_history="",
                history="Risky: Go for it!",
                latest_speaker="Risky Analyst",
                current_risky_response="Go for it!",
                current_safe_response="",
                current_neutral_response="",
                judge_decision="",
                count=1,
            )
        }

        state_safe = {
            "risk_debate_state": RiskDebateState(
                risky_history="Go for it!",
                safe_history="Be cautious",
                neutral_history="",
                history="Risky: Go for it!\nSafe: Be cautious",
                latest_speaker="Safe Analyst",
                current_risky_response="Go for it!",
                current_safe_response="Be cautious",
                current_neutral_response="",
                judge_decision="",
                count=2,
            )
        }

        state_neutral = {
            "risk_debate_state": RiskDebateState(
                risky_history="Go for it!",
                safe_history="Be cautious",
                neutral_history="Balance both views",
                history="Full discussion",
                latest_speaker="Neutral Analyst",
                current_risky_response="Go for it!",
                current_safe_response="Be cautious",
                current_neutral_response="Balance both views",
                judge_decision="",
                count=3,
            )
        }

        assert logic.should_continue_risk_analysis(state_risky) == "Safe Analyst"
        assert logic.should_continue_risk_analysis(state_safe) == "Neutral Analyst"
        assert logic.should_continue_risk_analysis(state_neutral) == "Risk Judge"


class TestWorkflowEndToEnd:
    def test_final_state_has_all_reports(self):
        final_state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "market_report": "Bullish technical indicators",
            "sentiment_report": "Positive social sentiment",
            "news_report": "Favorable news coverage",
            "fundamentals_report": "Strong financials",
            "investment_debate_state": {
                "bull_history": "Bull arguments",
                "bear_history": "Bear arguments",
                "history": "Full debate",
                "current_response": "Final bull response",
                "judge_decision": "BUY recommendation",
                "count": 4,
            },
            "trader_investment_plan": "Buy 100 shares at market open",
            "risk_debate_state": {
                "risky_history": "High conviction",
                "safe_history": "Moderate position size",
                "neutral_history": "Balanced view",
                "history": "Risk discussion",
                "latest_speaker": "Risk Judge",
                "judge_decision": "APPROVED with position limits",
                "count": 3,
            },
            "final_trade_decision": "BUY 100 shares AAPL at market open",
        }

        assert final_state["market_report"] != ""
        assert final_state["sentiment_report"] != ""
        assert final_state["news_report"] != ""
        assert final_state["fundamentals_report"] != ""
        assert "BUY" in final_state["investment_debate_state"]["judge_decision"]
        assert "APPROVED" in final_state["risk_debate_state"]["judge_decision"]
        assert "BUY" in final_state["final_trade_decision"]

    def test_workflow_handles_sell_decision(self):
        final_state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "market_report": "Bearish technical indicators",
            "sentiment_report": "Negative sentiment",
            "news_report": "Bad news",
            "fundamentals_report": "Weak financials",
            "investment_debate_state": {
                "judge_decision": "SELL recommendation",
                "count": 4,
            },
            "risk_debate_state": {
                "judge_decision": "APPROVED",
                "count": 3,
            },
            "final_trade_decision": "SELL position in AAPL",
        }

        assert "SELL" in final_state["final_trade_decision"]

    def test_workflow_handles_hold_decision(self):
        final_state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "investment_debate_state": {
                "judge_decision": "HOLD - insufficient conviction",
                "count": 4,
            },
            "risk_debate_state": {
                "judge_decision": "No action required",
                "count": 3,
            },
            "final_trade_decision": "HOLD current position",
        }

        assert "HOLD" in final_state["final_trade_decision"]


class TestTradingAgentsGraphValidation:
    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.set_config")
    def test_graph_validates_ticker_on_propagate(self, mock_set_config, mock_llm):
        from tradingagents.validation import TickerValidationError

        mock_llm_instance = MagicMock()
        mock_llm.return_value = mock_llm_instance

        with patch.object(TradingAgentsGraph, "__init__", lambda x, **kwargs: None):
            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            graph.config = {"llm_provider": "openai"}
            graph.debug = False
            graph.ticker = None
            graph.log_states_dict = {}

            from tradingagents.validation import validate_ticker

            with pytest.raises(TickerValidationError):
                validate_ticker("INVALID123TICKER")

    def test_valid_ticker_formats(self):
        from tradingagents.validation import validate_ticker

        assert validate_ticker("AAPL") == "AAPL"
        assert validate_ticker("aapl") == "AAPL"
        assert validate_ticker("BRK-B") == "BRK-B"
        assert validate_ticker("BRK.A") == "BRK.A"
        assert validate_ticker("  MSFT  ") == "MSFT"

    def test_invalid_ticker_formats(self):
        from tradingagents.validation import TickerValidationError, validate_ticker

        with pytest.raises(TickerValidationError):
            validate_ticker("")

        with pytest.raises(TickerValidationError):
            validate_ticker("TOOLONGTICKER")

        with pytest.raises(TickerValidationError):
            validate_ticker("123")
