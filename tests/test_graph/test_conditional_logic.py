"""Unit tests for conditional logic."""

import pytest
from unittest.mock import MagicMock

from tradingagents.graph.conditional_logic import ConditionalLogic


class TestConditionalLogic:
    """Tests for the ConditionalLogic class."""

    @pytest.fixture
    def logic(self):
        """Create a ConditionalLogic instance with default settings."""
        return ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)

    @pytest.fixture
    def logic_extended(self):
        """Create a ConditionalLogic instance with extended rounds."""
        return ConditionalLogic(max_debate_rounds=3, max_risk_discuss_rounds=2)

    @pytest.fixture
    def state_with_tool_call(self):
        """Create a state with a tool call in the last message."""
        msg = MagicMock()
        msg.tool_calls = [{"name": "get_stock_data"}]
        return {"messages": [msg]}

    @pytest.fixture
    def state_without_tool_call(self):
        """Create a state without tool calls."""
        msg = MagicMock()
        msg.tool_calls = []
        return {"messages": [msg]}


class TestShouldContinueMarket(TestConditionalLogic):
    """Tests for should_continue_market method."""

    @pytest.mark.unit
    def test_returns_tools_market_with_tool_call(self, logic, state_with_tool_call):
        """Test that tool calls route to tools_market."""
        result = logic.should_continue_market(state_with_tool_call)
        assert result == "tools_market"

    @pytest.mark.unit
    def test_returns_msg_clear_without_tool_call(self, logic, state_without_tool_call):
        """Test that no tool calls route to Msg Clear Market."""
        result = logic.should_continue_market(state_without_tool_call)
        assert result == "Msg Clear Market"


class TestShouldContinueSocial(TestConditionalLogic):
    """Tests for should_continue_social method."""

    @pytest.mark.unit
    def test_returns_tools_social_with_tool_call(self, logic, state_with_tool_call):
        """Test that tool calls route to tools_social."""
        result = logic.should_continue_social(state_with_tool_call)
        assert result == "tools_social"

    @pytest.mark.unit
    def test_returns_msg_clear_without_tool_call(self, logic, state_without_tool_call):
        """Test that no tool calls route to Msg Clear Social."""
        result = logic.should_continue_social(state_without_tool_call)
        assert result == "Msg Clear Social"


class TestShouldContinueNews(TestConditionalLogic):
    """Tests for should_continue_news method."""

    @pytest.mark.unit
    def test_returns_tools_news_with_tool_call(self, logic, state_with_tool_call):
        """Test that tool calls route to tools_news."""
        result = logic.should_continue_news(state_with_tool_call)
        assert result == "tools_news"

    @pytest.mark.unit
    def test_returns_msg_clear_without_tool_call(self, logic, state_without_tool_call):
        """Test that no tool calls route to Msg Clear News."""
        result = logic.should_continue_news(state_without_tool_call)
        assert result == "Msg Clear News"


class TestShouldContinueFundamentals(TestConditionalLogic):
    """Tests for should_continue_fundamentals method."""

    @pytest.mark.unit
    def test_returns_tools_fundamentals_with_tool_call(self, logic, state_with_tool_call):
        """Test that tool calls route to tools_fundamentals."""
        result = logic.should_continue_fundamentals(state_with_tool_call)
        assert result == "tools_fundamentals"

    @pytest.mark.unit
    def test_returns_msg_clear_without_tool_call(self, logic, state_without_tool_call):
        """Test that no tool calls route to Msg Clear Fundamentals."""
        result = logic.should_continue_fundamentals(state_without_tool_call)
        assert result == "Msg Clear Fundamentals"


class TestShouldContinueDebate(TestConditionalLogic):
    """Tests for should_continue_debate method."""

    @pytest.mark.unit
    def test_returns_research_manager_at_max_rounds(self, logic):
        """Test that debate ends at max rounds."""
        state = {
            "investment_debate_state": {
                "count": 4,  # 2 * max_debate_rounds = 2 * 1 = 2, but 4 > 2
                "current_response": "Bull Analyst: Buy signal",
            }
        }
        result = logic.should_continue_debate(state)
        assert result == "Research Manager"

    @pytest.mark.unit
    def test_returns_bear_when_bull_speaks(self, logic):
        """Test that Bull speaker routes to Bear."""
        state = {
            "investment_debate_state": {
                "count": 1,
                "current_response": "Bull Analyst: Strong buy opportunity",
            }
        }
        result = logic.should_continue_debate(state)
        assert result == "Bear Researcher"

    @pytest.mark.unit
    def test_returns_bull_when_not_bull(self, logic):
        """Test that Bear speaker routes to Bull."""
        state = {
            "investment_debate_state": {
                "count": 1,
                "current_response": "Bear Analyst: High risk warning",
            }
        }
        result = logic.should_continue_debate(state)
        assert result == "Bull Researcher"

    @pytest.mark.unit
    def test_extended_debate_rounds(self, logic_extended):
        """Test debate with extended rounds."""
        # With max_debate_rounds=3, max count = 2 * 3 = 6
        state = {
            "investment_debate_state": {
                "count": 5,  # Still under 6
                "current_response": "Bull Analyst: Buy",
            }
        }
        result = logic_extended.should_continue_debate(state)
        assert result == "Bear Researcher"

    @pytest.mark.unit
    def test_extended_debate_ends_at_max(self, logic_extended):
        """Test extended debate ends at max rounds."""
        state = {
            "investment_debate_state": {
                "count": 6,  # 2 * max_debate_rounds = 6
                "current_response": "Bull Analyst: Buy",
            }
        }
        result = logic_extended.should_continue_debate(state)
        assert result == "Research Manager"


class TestShouldContinueRiskAnalysis(TestConditionalLogic):
    """Tests for should_continue_risk_analysis method."""

    @pytest.mark.unit
    def test_returns_risk_judge_at_max_rounds(self, logic):
        """Test that risk analysis ends at max rounds."""
        state = {
            "risk_debate_state": {
                "count": 6,  # 3 * max_risk_discuss_rounds = 3 * 1 = 3, but 6 > 3
                "latest_speaker": "Aggressive Analyst",
            }
        }
        result = logic.should_continue_risk_analysis(state)
        assert result == "Risk Judge"

    @pytest.mark.unit
    def test_returns_conservative_after_aggressive(self, logic):
        """Test that Aggressive speaker routes to Conservative."""
        state = {
            "risk_debate_state": {
                "count": 1,
                "latest_speaker": "Aggressive Analyst: Go all in!",
            }
        }
        result = logic.should_continue_risk_analysis(state)
        assert result == "Conservative Analyst"

    @pytest.mark.unit
    def test_returns_neutral_after_conservative(self, logic):
        """Test that Conservative speaker routes to Neutral."""
        state = {
            "risk_debate_state": {
                "count": 1,
                "latest_speaker": "Conservative Analyst: Stay cautious",
            }
        }
        result = logic.should_continue_risk_analysis(state)
        assert result == "Neutral Analyst"

    @pytest.mark.unit
    def test_returns_aggressive_after_neutral(self, logic):
        """Test that Neutral speaker routes to Aggressive."""
        state = {
            "risk_debate_state": {
                "count": 1,
                "latest_speaker": "Neutral Analyst: Balanced view",
            }
        }
        result = logic.should_continue_risk_analysis(state)
        assert result == "Aggressive Analyst"

    @pytest.mark.unit
    def test_extended_risk_rounds(self, logic_extended):
        """Test risk analysis with extended rounds."""
        # With max_risk_discuss_rounds=2, max count = 3 * 2 = 6
        state = {
            "risk_debate_state": {
                "count": 5,  # Still under 6
                "latest_speaker": "Aggressive Analyst",
            }
        }
        result = logic_extended.should_continue_risk_analysis(state)
        assert result == "Conservative Analyst"

    @pytest.mark.unit
    def test_extended_risk_ends_at_max(self, logic_extended):
        """Test extended risk analysis ends at max rounds."""
        state = {
            "risk_debate_state": {
                "count": 6,  # 3 * max_risk_discuss_rounds = 6
                "latest_speaker": "Aggressive Analyst",
            }
        }
        result = logic_extended.should_continue_risk_analysis(state)
        assert result == "Risk Judge"
