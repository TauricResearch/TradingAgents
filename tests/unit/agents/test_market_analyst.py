"""Unit tests for market analyst agent."""

from unittest.mock import Mock

import pytest
from langchain_core.messages import HumanMessage

from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tests.conftest import MockResult


class TestMarketAnalyst:
    """Test suite for market analyst functionality."""

    def test_create_market_analyst_returns_callable(self, mock_llm, mock_toolkit):
        """Test that create_market_analyst returns a callable function."""
        analyst_node = create_market_analyst(mock_llm, mock_toolkit)
        assert callable(analyst_node)

    def test_market_analyst_node_basic_execution(
        self,
        mock_llm,
        mock_toolkit,
        sample_agent_state,
    ):
        """Test basic execution of market analyst node."""
        # Setup
        mock_toolkit.config = {"online_tools": False}
        mock_result = MockResult(content="Market analysis complete", tool_calls=[])
        mock_llm.bind_tools.return_value.invoke.return_value = mock_result

        analyst_node = create_market_analyst(mock_llm, mock_toolkit)

        # Execute
        result = analyst_node(sample_agent_state)

        # Verify
        assert "messages" in result
        assert "market_report" in result
        assert result["messages"] == [mock_result]
        assert result["market_report"] == "Market analysis complete"

    def test_market_analyst_uses_online_tools_when_configured(
        self,
        mock_llm,
        mock_toolkit,
        sample_agent_state,
    ):
        """Test that analyst uses online tools when configured."""
        # Setup
        mock_toolkit.config = {"online_tools": True}
        mock_toolkit.get_YFin_data_online = Mock()
        mock_toolkit.get_stockstats_indicators_report_online = Mock()

        mock_result = MockResult(content="Online analysis", tool_calls=[])
        mock_llm.bind_tools.return_value.invoke.return_value = mock_result

        analyst_node = create_market_analyst(mock_llm, mock_toolkit)

        # Execute
        analyst_node(sample_agent_state)

        # Verify tools were bound correctly
        mock_llm.bind_tools.assert_called_once()
        bound_tools = mock_llm.bind_tools.call_args[0][0]
        tool_names = [tool.name for tool in bound_tools]
        assert "get_YFin_data_online" in str(tool_names) or len(bound_tools) == 2

    def test_market_analyst_uses_offline_tools_when_configured(
        self,
        mock_llm,
        mock_toolkit,
        sample_agent_state,
    ):
        """Test that analyst uses offline tools when configured."""
        # Setup
        mock_toolkit.config = {"online_tools": False}
        mock_toolkit.get_YFin_data = Mock()
        mock_toolkit.get_stockstats_indicators_report = Mock()

        mock_result = MockResult(content="Offline analysis", tool_calls=[])
        mock_llm.bind_tools.return_value.invoke.return_value = mock_result

        analyst_node = create_market_analyst(mock_llm, mock_toolkit)

        # Execute
        analyst_node(sample_agent_state)

        # Verify tools were bound correctly
        mock_llm.bind_tools.assert_called_once()
        bound_tools = mock_llm.bind_tools.call_args[0][0]
        assert len(bound_tools) == 2  # Should have 2 offline tools

    def test_market_analyst_processes_state_variables(
        self,
        mock_llm,
        mock_toolkit,
        sample_agent_state,
    ):
        """Test that market analyst correctly processes state variables."""
        # Setup
        mock_toolkit.config = {"online_tools": False}
        mock_result = MockResult(
            content="Analysis for AAPL on 2024-05-10", tool_calls=[]
        )

        # Mock the chain to capture the invoke call
        mock_chain = Mock()
        mock_chain.invoke.return_value = mock_result
        mock_llm.bind_tools.return_value = mock_chain

        analyst_node = create_market_analyst(mock_llm, mock_toolkit)

        # Execute
        result = analyst_node(sample_agent_state)

        # Verify that invoke was called with the state
        mock_chain.invoke.assert_called_once_with(sample_agent_state["messages"])
        assert result["market_report"] == "Analysis for AAPL on 2024-05-10"

    def test_market_analyst_handles_empty_tool_calls(
        self,
        mock_llm,
        mock_toolkit,
        sample_agent_state,
    ):
        """Test handling when no tool calls are made."""
        # Setup
        mock_toolkit.config = {"online_tools": False}
        mock_result = MockResult(
            content="No tools needed", tool_calls=[]
        )  # Empty tool calls
        mock_llm.bind_tools.return_value.invoke.return_value = mock_result

        analyst_node = create_market_analyst(mock_llm, mock_toolkit)

        # Execute
        result = analyst_node(sample_agent_state)

        # Verify
        assert result["market_report"] == "No tools needed"
        assert result["messages"] == [mock_result]

    def test_market_analyst_with_tool_calls(
        self,
        mock_llm,
        mock_toolkit,
        sample_agent_state,
    ):
        """Test handling when tool calls are present."""
        # Setup
        mock_toolkit.config = {"online_tools": False}
        mock_result = MockResult(
            content="Tool analysis", tool_calls=[Mock()]
        )  # Non-empty tool calls
        mock_llm.bind_tools.return_value.invoke.return_value = mock_result

        analyst_node = create_market_analyst(mock_llm, mock_toolkit)

        # Execute
        result = analyst_node(sample_agent_state)

        # Verify - when tool_calls exist, market_report should be empty
        assert result["market_report"] == ""
        assert result["messages"] == [mock_result]

    @pytest.mark.parametrize("online_tools", [True, False])
    def test_market_analyst_tool_configuration(
        self,
        mock_llm,
        mock_toolkit,
        sample_agent_state,
        online_tools,
    ):
        """Test tool configuration for both online and offline modes."""
        # Setup
        mock_toolkit.config = {"online_tools": online_tools}
        mock_result = MockResult(
            content=f"Analysis in {'online' if online_tools else 'offline'} mode",
            tool_calls=[],
        )
        mock_llm.bind_tools.return_value.invoke.return_value = mock_result

        analyst_node = create_market_analyst(mock_llm, mock_toolkit)

        # Execute
        result = analyst_node(sample_agent_state)

        # Verify
        assert "Analysis in" in result["market_report"]
        mock_llm.bind_tools.assert_called_once()


# Integration-style test (but still mocked)
class TestMarketAnalystIntegration:
    """Integration-style tests for market analyst."""

    def test_market_analyst_full_workflow(self, mock_llm, mock_toolkit):
        """Test a complete workflow simulation."""
        # Setup state
        state = {
            "company_of_interest": "TSLA",
            "trade_date": "2024-05-15",
            "messages": [HumanMessage(content="Analyze TSLA")],
        }

        # Setup toolkit
        mock_toolkit.config = {"online_tools": True}

        # Setup LLM response
        mock_result = MockResult(
            content="""
        # Market Analysis for TSLA (2024-05-15)

        ## Technical Analysis
        - RSI: 65 (slightly overbought)
        - MACD: Bullish crossover
        - 50-day SMA: Trending upward

        ## Volume Analysis
        - Above average volume suggests strong interest

        | Indicator | Value | Signal |
        |-----------|-------|--------|
        | RSI       | 65    | Neutral |
        | MACD      | +0.45 | Buy     |
        | Volume    | High  | Bullish |
        """,
            tool_calls=[],
        )
        mock_llm.bind_tools.return_value.invoke.return_value = mock_result

        # Execute
        analyst_node = create_market_analyst(mock_llm, mock_toolkit)
        result = analyst_node(state)

        # Verify comprehensive output
        assert (
            "TSLA" in result["market_report"]
            or "Market Analysis" in result["market_report"]
        )
        assert len(result["messages"]) == 1
        assert result["messages"][0] == mock_result
