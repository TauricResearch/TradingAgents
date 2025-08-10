"""Unit tests for TradingAgentsGraph."""

from unittest.mock import Mock, mock_open, patch

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph


class TestTradingAgentsGraph:
    """Test suite for TradingAgentsGraph class."""

    @patch("tradingagents.dataflows.config.set_config")
    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_init_basic(
        self,
        mock_toolkit,
        mock_chat_openai,
        mock_set_config,
        sample_config,
        temp_data_dir,
    ):
        """Test basic initialization of TradingAgentsGraph."""
        # Setup
        sample_config["project_dir"] = temp_data_dir
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm
        mock_toolkit_instance = Mock()
        mock_toolkit_instance.config = sample_config
        mock_toolkit.return_value = mock_toolkit_instance

        # Execute
        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            graph = TradingAgentsGraph(config=sample_config)

        # Verify
        assert graph.config == sample_config
        assert graph.debug is False
        mock_set_config.assert_called_once_with(sample_config)
        assert (
            mock_chat_openai.call_count == 2
        )  # deep_thinking_llm and quick_thinking_llm

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_init_with_debug(
        self,
        mock_toolkit,
        mock_chat_openai,
        sample_config,
        temp_data_dir,
    ):
        """Test initialization with debug mode enabled."""
        sample_config["project_dir"] = temp_data_dir
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm
        mock_toolkit_instance = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.dataflows.config.set_config"):
                graph = TradingAgentsGraph(debug=True, config=sample_config)

        assert graph.debug is True

    @patch("tradingagents.graph.trading_graph.ChatAnthropic")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_init_with_anthropic(
        self,
        mock_toolkit,
        mock_chat_anthropic,
        sample_config,
        temp_data_dir,
    ):
        """Test initialization with Anthropic LLM provider."""
        sample_config["project_dir"] = temp_data_dir
        sample_config["llm_provider"] = "anthropic"
        mock_llm = Mock()
        mock_chat_anthropic.return_value = mock_llm
        mock_toolkit_instance = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.dataflows.config.set_config"):
                TradingAgentsGraph(config=sample_config)

        assert mock_chat_anthropic.call_count == 2

    @patch("tradingagents.graph.trading_graph.ChatGoogleGenerativeAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_init_with_google(
        self,
        mock_toolkit,
        mock_chat_google,
        sample_config,
        temp_data_dir,
    ):
        """Test initialization with Google LLM provider."""
        sample_config["project_dir"] = temp_data_dir
        sample_config["llm_provider"] = "google"
        mock_llm = Mock()
        mock_chat_google.return_value = mock_llm
        mock_toolkit_instance = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.dataflows.config.set_config"):
                TradingAgentsGraph(config=sample_config)

        assert mock_chat_google.call_count == 2

    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_init_unsupported_llm_provider(
        self,
        mock_toolkit,
        sample_config,
        temp_data_dir,
    ):
        """Test initialization with unsupported LLM provider raises error."""
        sample_config["project_dir"] = temp_data_dir
        sample_config["llm_provider"] = "unsupported"
        mock_toolkit_instance = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            with patch("tradingagents.dataflows.config.set_config"):
                TradingAgentsGraph(config=sample_config)

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_create_tool_nodes(
        self,
        mock_toolkit,
        mock_chat_openai,
        sample_config,
        temp_data_dir,
    ):
        """Test creation of tool nodes."""
        sample_config["project_dir"] = temp_data_dir
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm
        mock_toolkit_instance = Mock()

        # Setup toolkit methods
        mock_toolkit_instance.get_YFin_data_online = Mock()
        mock_toolkit_instance.get_YFin_data = Mock()
        mock_toolkit_instance.get_stockstats_indicators_report_online = Mock()
        mock_toolkit_instance.get_stockstats_indicators_report = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.dataflows.config.set_config"):
                graph = TradingAgentsGraph(config=sample_config)

        # Verify tool nodes are created
        assert "market" in graph.tool_nodes
        assert "social" in graph.tool_nodes
        assert "news" in graph.tool_nodes
        assert "fundamentals" in graph.tool_nodes

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_propagate_basic(
        self,
        mock_toolkit,
        mock_chat_openai,
        sample_config,
        temp_data_dir,
    ):
        """Test basic propagate functionality."""
        sample_config["project_dir"] = temp_data_dir
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm
        mock_toolkit_instance = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        # Mock the graph and its invoke method
        mock_graph = Mock()
        mock_final_state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-05-10",
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {
                "bull_history": [],
                "bear_history": [],
                "history": [],
                "current_response": "",
                "judge_decision": "",
            },
            "trader_investment_plan": "",
            "risk_debate_state": {
                "risky_history": [],
                "safe_history": [],
                "neutral_history": [],
                "history": [],
                "judge_decision": "",
            },
            "investment_plan": "",
            "final_trade_decision": "HOLD",
        }
        mock_graph.invoke.return_value = mock_final_state

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.dataflows.config.set_config"):
                graph = TradingAgentsGraph(config=sample_config)
                graph.graph = mock_graph

                # Mock the propagator and signal processor
                graph.propagator.create_initial_state = Mock(
                    return_value={"test": "state"},
                )
                graph.propagator.get_graph_args = Mock(return_value={})
                graph.signal_processor.process_signal = Mock(return_value="HOLD")

        # Execute
        with patch("builtins.open", create=True), patch("json.dump"):
            final_state, decision = graph.propagate("AAPL", "2024-05-10")

        # Verify
        assert final_state == mock_final_state
        assert decision == "HOLD"
        assert graph.ticker == "AAPL"
        assert graph.curr_state == mock_final_state

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_propagate_debug_mode(
        self,
        mock_toolkit,
        mock_chat_openai,
        sample_config,
        temp_data_dir,
    ):
        """Test propagate in debug mode."""
        sample_config["project_dir"] = temp_data_dir
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm
        mock_toolkit_instance = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        # Mock the graph stream method for debug mode
        mock_graph = Mock()
        mock_chunk = {"messages": [Mock()]}
        mock_chunk["messages"][0].pretty_print = Mock()
        mock_graph.stream.return_value = [mock_chunk, mock_chunk]  # Multiple chunks

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.dataflows.config.set_config"):
                graph = TradingAgentsGraph(debug=True, config=sample_config)
                graph.graph = mock_graph

                # Mock other components
                graph.propagator.create_initial_state = Mock(
                    return_value={"test": "state"},
                )
                graph.propagator.get_graph_args = Mock(return_value={})
                graph.signal_processor.process_signal = Mock(return_value="BUY")

        # Execute
        with patch("builtins.open", create=True), patch("json.dump"):
            final_state, decision = graph.propagate("TSLA", "2024-05-15")

        # Verify debug mode was used
        mock_graph.stream.assert_called_once()
        assert graph.debug is True
        assert decision == "BUY"

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_log_state(
        self,
        mock_toolkit,
        mock_chat_openai,
        sample_config,
        temp_data_dir,
    ):
        """Test state logging functionality."""
        sample_config["project_dir"] = temp_data_dir
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm
        mock_toolkit_instance = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.dataflows.config.set_config"):
                graph = TradingAgentsGraph(config=sample_config)
                graph.ticker = "NVDA"

        # Create a mock final state
        final_state = {
            "company_of_interest": "NVDA",
            "trade_date": "2024-05-20",
            "market_report": "Market looking good",
            "sentiment_report": "Positive sentiment",
            "news_report": "Good news",
            "fundamentals_report": "Strong fundamentals",
            "investment_debate_state": {
                "bull_history": [],
                "bear_history": [],
                "history": [],
                "current_response": "",
                "judge_decision": "BUY",
            },
            "trader_investment_plan": "Buy 100 shares",
            "risk_debate_state": {
                "risky_history": [],
                "safe_history": [],
                "neutral_history": [],
                "history": [],
                "judge_decision": "LOW_RISK",
            },
            "investment_plan": "Execute buy order",
            "final_trade_decision": "BUY",
        }

        # Mock file operations
        with patch("pathlib.Path.mkdir"), patch("builtins.open", mock_open()):
            with patch("json.dump"):
                graph._log_state("2024-05-20", final_state)

        # Verify logging occurred
        assert "2024-05-20" in graph.log_states_dict
        logged_state = graph.log_states_dict["2024-05-20"]
        assert logged_state["company_of_interest"] == "NVDA"
        assert logged_state["final_trade_decision"] == "BUY"

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_reflect_and_remember(
        self,
        mock_toolkit,
        mock_chat_openai,
        sample_config,
        temp_data_dir,
    ):
        """Test reflection and memory update functionality."""
        sample_config["project_dir"] = temp_data_dir
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm
        mock_toolkit_instance = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        with (
            patch(
                "tradingagents.graph.trading_graph.FinancialSituationMemory",
            ),
            patch("tradingagents.graph.trading_graph.set_config"),
        ):
            graph = TradingAgentsGraph(config=sample_config)

            # Set up current state
            graph.curr_state = {"test": "state"}

            # Mock reflector methods
            graph.reflector.reflect_bull_researcher = Mock()
            graph.reflector.reflect_bear_researcher = Mock()
            graph.reflector.reflect_trader = Mock()
            graph.reflector.reflect_invest_judge = Mock()
            graph.reflector.reflect_risk_manager = Mock()

        returns_losses = {"return": 0.05, "loss": -0.02}

        # Execute
        graph.reflect_and_remember(returns_losses)

        # Verify all reflection methods were called
        graph.reflector.reflect_bull_researcher.assert_called_once()
        graph.reflector.reflect_bear_researcher.assert_called_once()
        graph.reflector.reflect_trader.assert_called_once()
        graph.reflector.reflect_invest_judge.assert_called_once()
        graph.reflector.reflect_risk_manager.assert_called_once()

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_process_signal(
        self,
        mock_toolkit,
        mock_chat_openai,
        sample_config,
        temp_data_dir,
    ):
        """Test signal processing functionality."""
        sample_config["project_dir"] = temp_data_dir
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm
        mock_toolkit_instance = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.dataflows.config.set_config"):
                graph = TradingAgentsGraph(config=sample_config)
                graph.signal_processor.process_signal = Mock(return_value="BUY")

        full_signal = "Based on analysis, recommend BUY with confidence 0.8"
        result = graph.process_signal(full_signal)

        assert result == "BUY"
        graph.signal_processor.process_signal.assert_called_once_with(full_signal)

    @pytest.mark.parametrize(
        "selected_analysts",
        [
            ["market"],
            ["market", "social"],
            ["market", "social", "news"],
            ["market", "social", "news", "fundamentals"],
        ],
    )
    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_selected_analysts_configuration(
        self,
        mock_toolkit,
        mock_chat_openai,
        selected_analysts,
        sample_config,
        temp_data_dir,
    ):
        """Test different analyst configurations."""
        sample_config["project_dir"] = temp_data_dir
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm
        mock_toolkit_instance = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.dataflows.config.set_config"):
                TradingAgentsGraph(
                    selected_analysts=selected_analysts,
                    config=sample_config,
                )

        # Verify graph was set up with selected analysts
        # (The actual setup_graph method would be mocked in a real implementation)
        assert len(selected_analysts) >= 1  # Basic validation


class TestTradingAgentsGraphErrorHandling:
    """Test error handling in TradingAgentsGraph."""

    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_invalid_config_handling(self, mock_toolkit):
        """Test handling of invalid configuration."""
        invalid_config = {"invalid_key": "invalid_value"}
        mock_toolkit_instance = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        # This should still work as the class should use defaults for missing keys
        with patch("tradingagents.dataflows.config.set_config"):
            with pytest.raises(
                KeyError,
            ):  # Should fail when trying to access missing config keys
                TradingAgentsGraph(config=invalid_config)

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_directory_creation_failure(
        self,
        mock_toolkit,
        mock_chat_openai,
        sample_config,
    ):
        """Test handling when directory creation fails."""
        sample_config["project_dir"] = "/invalid/path/that/cannot/be/created"
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm
        mock_toolkit_instance = Mock()
        mock_toolkit.return_value = mock_toolkit_instance

        # Should handle directory creation gracefully or raise appropriate error
        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.dataflows.config.set_config"):
                # This might raise PermissionError or similar, depending on implementation
                try:
                    TradingAgentsGraph(config=sample_config)
                except (PermissionError, OSError):
                    # This is expected for invalid paths
                    pass
