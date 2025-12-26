"""Tests for Issue #17: Analyst integration into graph/setup.py workflow.

This module tests the integration of new analysts (momentum, macro, correlation)
into the TradingAgents graph workflow.
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import get_type_hints
import sys

# Check if langchain dependencies are available
try:
    import langchain_core
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

# Skip all tests if langchain not available
pytestmark = pytest.mark.skipif(
    not LANGCHAIN_AVAILABLE,
    reason="langchain_core not installed"
)


class TestAgentStateReports:
    """Test that AgentState has the new report fields."""

    def test_agent_state_has_momentum_report(self):
        """AgentState should have momentum_report field."""
        from tradingagents.agents.utils.agent_states import AgentState
        hints = get_type_hints(AgentState)
        assert "momentum_report" in hints

    def test_agent_state_has_macro_report(self):
        """AgentState should have macro_report field."""
        from tradingagents.agents.utils.agent_states import AgentState
        hints = get_type_hints(AgentState)
        assert "macro_report" in hints

    def test_agent_state_has_correlation_report(self):
        """AgentState should have correlation_report field."""
        from tradingagents.agents.utils.agent_states import AgentState
        hints = get_type_hints(AgentState)
        assert "correlation_report" in hints


class TestConditionalLogicMethods:
    """Test that ConditionalLogic has methods for new analysts."""

    def test_should_continue_momentum_exists(self):
        """ConditionalLogic should have should_continue_momentum method."""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic()
        assert hasattr(cl, "should_continue_momentum")
        assert callable(cl.should_continue_momentum)

    def test_should_continue_macro_exists(self):
        """ConditionalLogic should have should_continue_macro method."""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic()
        assert hasattr(cl, "should_continue_macro")
        assert callable(cl.should_continue_macro)

    def test_should_continue_correlation_exists(self):
        """ConditionalLogic should have should_continue_correlation method."""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic()
        assert hasattr(cl, "should_continue_correlation")
        assert callable(cl.should_continue_correlation)

    def test_momentum_conditional_returns_tools(self):
        """should_continue_momentum should return 'tools_momentum' when tool_calls exist."""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic()

        mock_message = MagicMock()
        mock_message.tool_calls = [{"name": "test"}]
        state = {"messages": [mock_message]}

        result = cl.should_continue_momentum(state)
        assert result == "tools_momentum"

    def test_momentum_conditional_returns_clear(self):
        """should_continue_momentum should return 'Msg Clear Momentum' when no tool_calls."""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic()

        mock_message = MagicMock()
        mock_message.tool_calls = []
        state = {"messages": [mock_message]}

        result = cl.should_continue_momentum(state)
        assert result == "Msg Clear Momentum"

    def test_macro_conditional_returns_tools(self):
        """should_continue_macro should return 'tools_macro' when tool_calls exist."""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic()

        mock_message = MagicMock()
        mock_message.tool_calls = [{"name": "test"}]
        state = {"messages": [mock_message]}

        result = cl.should_continue_macro(state)
        assert result == "tools_macro"

    def test_macro_conditional_returns_clear(self):
        """should_continue_macro should return 'Msg Clear Macro' when no tool_calls."""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic()

        mock_message = MagicMock()
        mock_message.tool_calls = []
        state = {"messages": [mock_message]}

        result = cl.should_continue_macro(state)
        assert result == "Msg Clear Macro"

    def test_correlation_conditional_returns_tools(self):
        """should_continue_correlation should return 'tools_correlation' when tool_calls exist."""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic()

        mock_message = MagicMock()
        mock_message.tool_calls = [{"name": "test"}]
        state = {"messages": [mock_message]}

        result = cl.should_continue_correlation(state)
        assert result == "tools_correlation"

    def test_correlation_conditional_returns_clear(self):
        """should_continue_correlation should return 'Msg Clear Correlation' when no tool_calls."""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic()

        mock_message = MagicMock()
        mock_message.tool_calls = []
        state = {"messages": [mock_message]}

        result = cl.should_continue_correlation(state)
        assert result == "Msg Clear Correlation"


class TestAgentImports:
    """Test that new analysts are properly exported from agents module."""

    def test_create_momentum_analyst_import(self):
        """create_momentum_analyst should be importable from agents."""
        from tradingagents.agents import create_momentum_analyst
        assert callable(create_momentum_analyst)

    def test_create_macro_analyst_import(self):
        """create_macro_analyst should be importable from agents."""
        from tradingagents.agents import create_macro_analyst
        assert callable(create_macro_analyst)

    def test_create_correlation_analyst_import(self):
        """create_correlation_analyst should be importable from agents."""
        from tradingagents.agents import create_correlation_analyst
        assert callable(create_correlation_analyst)

    def test_create_position_sizing_manager_import(self):
        """create_position_sizing_manager should be importable from agents."""
        from tradingagents.agents import create_position_sizing_manager
        assert callable(create_position_sizing_manager)


class TestAnalystsModuleExports:
    """Test analysts submodule exports."""

    def test_analysts_module_exports_momentum(self):
        """analysts module should export create_momentum_analyst."""
        from tradingagents.agents.analysts import create_momentum_analyst
        assert callable(create_momentum_analyst)

    def test_analysts_module_exports_macro(self):
        """analysts module should export create_macro_analyst."""
        from tradingagents.agents.analysts import create_macro_analyst
        assert callable(create_macro_analyst)

    def test_analysts_module_exports_correlation(self):
        """analysts module should export create_correlation_analyst."""
        from tradingagents.agents.analysts import create_correlation_analyst
        assert callable(create_correlation_analyst)

    def test_analysts_module_all_exports(self):
        """analysts __all__ should include all analyst creators."""
        from tradingagents.agents import analysts
        assert "create_momentum_analyst" in analysts.__all__
        assert "create_macro_analyst" in analysts.__all__
        assert "create_correlation_analyst" in analysts.__all__


class TestManagersModuleExports:
    """Test managers submodule exports."""

    def test_managers_module_exports_position_sizing(self):
        """managers module should export create_position_sizing_manager."""
        from tradingagents.agents.managers import create_position_sizing_manager
        assert callable(create_position_sizing_manager)

    def test_managers_module_all_exports(self):
        """managers __all__ should include position_sizing_manager."""
        from tradingagents.agents import managers
        assert "create_position_sizing_manager" in managers.__all__


class TestToolImports:
    """Test that tool functions are importable from analyst modules."""

    def test_momentum_tools_importable(self):
        """Momentum analyst tools should be importable."""
        from tradingagents.agents.analysts.momentum_analyst import (
            get_multi_timeframe_momentum,
            get_adx_analysis,
            get_momentum_divergence,
        )
        assert callable(get_multi_timeframe_momentum)
        assert callable(get_adx_analysis)
        assert callable(get_momentum_divergence)

    def test_macro_tools_importable(self):
        """Macro analyst tools should be importable."""
        from tradingagents.agents.analysts.macro_analyst import (
            get_economic_regime_analysis,
            get_yield_curve_analysis,
            get_monetary_policy_analysis,
            get_inflation_regime_analysis,
        )
        assert callable(get_economic_regime_analysis)
        assert callable(get_yield_curve_analysis)
        assert callable(get_monetary_policy_analysis)
        assert callable(get_inflation_regime_analysis)

    def test_correlation_tools_importable(self):
        """Correlation analyst tools should be importable."""
        from tradingagents.agents.analysts.correlation_analyst import (
            get_cross_asset_correlation_analysis,
            get_sector_rotation_analysis,
            get_correlation_matrix,
            get_rolling_correlation_trend,
        )
        assert callable(get_cross_asset_correlation_analysis)
        assert callable(get_sector_rotation_analysis)
        assert callable(get_correlation_matrix)
        assert callable(get_rolling_correlation_trend)


class TestTradingGraphToolNodes:
    """Test that trading_graph.py has tool nodes for new analysts."""

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.set_config")
    @patch("os.makedirs")
    def test_tool_nodes_include_momentum(self, mock_makedirs, mock_set_config, mock_llm):
        """_create_tool_nodes should include momentum tools."""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        mock_llm.return_value = MagicMock()

        with patch.object(TradingAgentsGraph, "__init__", lambda self: None):
            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            tool_nodes = graph._create_tool_nodes()

        assert "momentum" in tool_nodes

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.set_config")
    @patch("os.makedirs")
    def test_tool_nodes_include_macro(self, mock_makedirs, mock_set_config, mock_llm):
        """_create_tool_nodes should include macro tools."""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        mock_llm.return_value = MagicMock()

        with patch.object(TradingAgentsGraph, "__init__", lambda self: None):
            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            tool_nodes = graph._create_tool_nodes()

        assert "macro" in tool_nodes

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.set_config")
    @patch("os.makedirs")
    def test_tool_nodes_include_correlation(self, mock_makedirs, mock_set_config, mock_llm):
        """_create_tool_nodes should include correlation tools."""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        mock_llm.return_value = MagicMock()

        with patch.object(TradingAgentsGraph, "__init__", lambda self: None):
            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            tool_nodes = graph._create_tool_nodes()

        assert "correlation" in tool_nodes


class TestGraphSetupDocstring:
    """Test that setup_graph docstring documents new analysts."""

    def test_docstring_mentions_momentum(self):
        """setup_graph docstring should mention momentum analyst."""
        from tradingagents.graph.setup import GraphSetup
        docstring = GraphSetup.setup_graph.__doc__
        assert "momentum" in docstring.lower()

    def test_docstring_mentions_macro(self):
        """setup_graph docstring should mention macro analyst."""
        from tradingagents.graph.setup import GraphSetup
        docstring = GraphSetup.setup_graph.__doc__
        assert "macro" in docstring.lower()

    def test_docstring_mentions_correlation(self):
        """setup_graph docstring should mention correlation analyst."""
        from tradingagents.graph.setup import GraphSetup
        docstring = GraphSetup.setup_graph.__doc__
        assert "correlation" in docstring.lower()


class TestLogStateNewReports:
    """Test that _log_state includes new report fields."""

    def test_log_state_includes_momentum_report(self):
        """_log_state should log momentum_report if present."""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", lambda self: None):
            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            graph.log_states_dict = {}
            graph.ticker = "TEST"

            final_state = {
                "company_of_interest": "TEST",
                "trade_date": "2024-01-01",
                "market_report": "",
                "sentiment_report": "",
                "news_report": "",
                "fundamentals_report": "",
                "momentum_report": "Momentum analysis result",
                "macro_report": "",
                "correlation_report": "",
                "investment_debate_state": {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                },
                "trader_investment_plan": "",
                "risk_debate_state": {
                    "risky_history": "",
                    "safe_history": "",
                    "neutral_history": "",
                    "history": "",
                    "judge_decision": "",
                },
                "investment_plan": "",
                "final_trade_decision": "",
            }

            with patch("builtins.open", MagicMock()):
                with patch("json.dump"):
                    with patch("pathlib.Path.mkdir"):
                        graph._log_state("2024-01-01", final_state)

            logged = graph.log_states_dict["2024-01-01"]
            assert "momentum_report" in logged
            assert logged["momentum_report"] == "Momentum analysis result"

    def test_log_state_includes_macro_report(self):
        """_log_state should log macro_report if present."""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", lambda self: None):
            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            graph.log_states_dict = {}
            graph.ticker = "TEST"

            final_state = {
                "company_of_interest": "TEST",
                "trade_date": "2024-01-01",
                "market_report": "",
                "sentiment_report": "",
                "news_report": "",
                "fundamentals_report": "",
                "momentum_report": "",
                "macro_report": "Macro analysis result",
                "correlation_report": "",
                "investment_debate_state": {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                },
                "trader_investment_plan": "",
                "risk_debate_state": {
                    "risky_history": "",
                    "safe_history": "",
                    "neutral_history": "",
                    "history": "",
                    "judge_decision": "",
                },
                "investment_plan": "",
                "final_trade_decision": "",
            }

            with patch("builtins.open", MagicMock()):
                with patch("json.dump"):
                    with patch("pathlib.Path.mkdir"):
                        graph._log_state("2024-01-01", final_state)

            logged = graph.log_states_dict["2024-01-01"]
            assert "macro_report" in logged
            assert logged["macro_report"] == "Macro analysis result"

    def test_log_state_includes_correlation_report(self):
        """_log_state should log correlation_report if present."""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", lambda self: None):
            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            graph.log_states_dict = {}
            graph.ticker = "TEST"

            final_state = {
                "company_of_interest": "TEST",
                "trade_date": "2024-01-01",
                "market_report": "",
                "sentiment_report": "",
                "news_report": "",
                "fundamentals_report": "",
                "momentum_report": "",
                "macro_report": "",
                "correlation_report": "Correlation analysis result",
                "investment_debate_state": {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                },
                "trader_investment_plan": "",
                "risk_debate_state": {
                    "risky_history": "",
                    "safe_history": "",
                    "neutral_history": "",
                    "history": "",
                    "judge_decision": "",
                },
                "investment_plan": "",
                "final_trade_decision": "",
            }

            with patch("builtins.open", MagicMock()):
                with patch("json.dump"):
                    with patch("pathlib.Path.mkdir"):
                        graph._log_state("2024-01-01", final_state)

            logged = graph.log_states_dict["2024-01-01"]
            assert "correlation_report" in logged
            assert logged["correlation_report"] == "Correlation analysis result"

    def test_log_state_handles_missing_new_reports(self):
        """_log_state should handle missing new report fields gracefully."""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", lambda self: None):
            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            graph.log_states_dict = {}
            graph.ticker = "TEST"

            # State without new report fields (backward compatibility)
            final_state = {
                "company_of_interest": "TEST",
                "trade_date": "2024-01-01",
                "investment_debate_state": {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                },
                "trader_investment_plan": "",
                "risk_debate_state": {
                    "risky_history": "",
                    "safe_history": "",
                    "neutral_history": "",
                    "history": "",
                    "judge_decision": "",
                },
                "investment_plan": "",
                "final_trade_decision": "",
            }

            with patch("builtins.open", MagicMock()):
                with patch("json.dump"):
                    with patch("pathlib.Path.mkdir"):
                        graph._log_state("2024-01-01", final_state)

            logged = graph.log_states_dict["2024-01-01"]
            # Should default to empty string
            assert logged["momentum_report"] == ""
            assert logged["macro_report"] == ""
            assert logged["correlation_report"] == ""
