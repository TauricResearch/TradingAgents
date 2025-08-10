"""Integration tests for the full TradingAgents workflow."""

import pytest
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG


@pytest.mark.integration
class TestFullWorkflowIntegration:
    """Integration tests for the complete trading workflow."""

    @pytest.fixture
    def integration_config(self, temp_data_dir):
        """Configuration for integration tests."""
        config = DEFAULT_CONFIG.copy()
        config.update(
            {
                "online_tools": False,  # Use offline mode for integration tests
                "max_debate_rounds": 1,  # Limit rounds for faster tests
                "llm_provider": "openai",
                "deep_think_llm": "gpt-4o-mini",
                "quick_think_llm": "gpt-4o-mini",
                "project_dir": temp_data_dir,
            }
        )
        return config

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_end_to_end_trading_workflow(
        self, mock_toolkit, mock_chat_openai, integration_config
    ):
        """Test complete end-to-end trading workflow."""
        # Setup mocks
        mock_llm = Mock()
        mock_llm.model_name = "gpt-4o-mini"
        mock_chat_openai.return_value = mock_llm

        mock_toolkit_instance = Mock()
        mock_toolkit_instance.config = integration_config

        # Mock all toolkit methods
        self._setup_toolkit_methods(mock_toolkit_instance)
        mock_toolkit.return_value = mock_toolkit_instance

        # Mock the graph workflow
        mock_graph = Mock()
        mock_final_state = self._create_mock_final_state()
        mock_graph.invoke.return_value = mock_final_state

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.graph.trading_graph.set_config"):
                # Initialize the trading graph
                trading_graph = TradingAgentsGraph(
                    selected_analysts=["market", "social", "news", "fundamentals"],
                    debug=False,
                    config=integration_config,
                )
                trading_graph.graph = mock_graph

                # Mock components
                trading_graph.propagator.create_initial_state = Mock(
                    return_value={
                        "company_of_interest": "AAPL",
                        "trade_date": "2024-05-10",
                        "messages": [],
                    }
                )
                trading_graph.propagator.get_graph_args = Mock(return_value={})
                trading_graph.signal_processor.process_signal = Mock(return_value="BUY")

        # Execute the full workflow
        with patch("builtins.open", create=True):
            with patch("json.dump"):
                final_state, decision = trading_graph.propagate("AAPL", "2024-05-10")

        # Verify the workflow completed successfully
        assert final_state is not None
        assert decision == "BUY"
        assert final_state["company_of_interest"] == "AAPL"
        assert final_state["trade_date"] == "2024-05-10"
        assert final_state["final_trade_decision"] in ["BUY", "SELL", "HOLD"]

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_multiple_analysts_integration(
        self, mock_toolkit, mock_chat_openai, integration_config
    ):
        """Test integration with different analyst combinations."""
        analyst_combinations = [
            ["market"],
            ["market", "social"],
            ["market", "fundamentals"],
            ["market", "social", "news", "fundamentals"],
        ]

        for analysts in analyst_combinations:
            # Setup mocks for each combination
            mock_llm = Mock()
            mock_chat_openai.return_value = mock_llm

            mock_toolkit_instance = Mock()
            mock_toolkit_instance.config = integration_config
            self._setup_toolkit_methods(mock_toolkit_instance)
            mock_toolkit.return_value = mock_toolkit_instance

            mock_graph = Mock()
            mock_final_state = self._create_mock_final_state()
            mock_graph.invoke.return_value = mock_final_state

            with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
                with patch("tradingagents.graph.trading_graph.set_config"):
                    # Test each analyst combination
                    trading_graph = TradingAgentsGraph(
                        selected_analysts=analysts, config=integration_config
                    )
                    trading_graph.graph = mock_graph

                    # Mock components
                    trading_graph.propagator.create_initial_state = Mock(
                        return_value={
                            "company_of_interest": "TSLA",
                            "trade_date": "2024-05-15",
                            "messages": [],
                        }
                    )
                    trading_graph.propagator.get_graph_args = Mock(return_value={})
                    trading_graph.signal_processor.process_signal = Mock(
                        return_value="HOLD"
                    )

            # Execute
            with patch("builtins.open", create=True):
                with patch("json.dump"):
                    final_state, decision = trading_graph.propagate(
                        "TSLA", "2024-05-15"
                    )

            # Verify
            assert final_state is not None
            assert decision in ["BUY", "SELL", "HOLD"]

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_memory_and_reflection_integration(
        self, mock_toolkit, mock_chat_openai, integration_config
    ):
        """Test integration of memory and reflection components."""
        # Setup
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm

        mock_toolkit_instance = Mock()
        mock_toolkit_instance.config = integration_config
        self._setup_toolkit_methods(mock_toolkit_instance)
        mock_toolkit.return_value = mock_toolkit_instance

        mock_graph = Mock()
        mock_final_state = self._create_mock_final_state()
        mock_graph.invoke.return_value = mock_final_state

        with patch(
            "tradingagents.graph.trading_graph.FinancialSituationMemory"
        ) as mock_memory:
            mock_memory_instance = Mock()
            mock_memory.return_value = mock_memory_instance

            with patch("tradingagents.graph.trading_graph.set_config"):
                trading_graph = TradingAgentsGraph(config=integration_config)
                trading_graph.graph = mock_graph

                # Mock components
                trading_graph.propagator.create_initial_state = Mock(
                    return_value={
                        "company_of_interest": "NVDA",
                        "trade_date": "2024-05-20",
                        "messages": [],
                    }
                )
                trading_graph.propagator.get_graph_args = Mock(return_value={})
                trading_graph.signal_processor.process_signal = Mock(
                    return_value="SELL"
                )

                # Mock reflection methods
                trading_graph.reflector.reflect_bull_researcher = Mock()
                trading_graph.reflector.reflect_bear_researcher = Mock()
                trading_graph.reflector.reflect_trader = Mock()
                trading_graph.reflector.reflect_invest_judge = Mock()
                trading_graph.reflector.reflect_risk_manager = Mock()

        # Execute workflow
        with patch("builtins.open", create=True):
            with patch("json.dump"):
                final_state, decision = trading_graph.propagate("NVDA", "2024-05-20")

        # Test reflection and memory update
        returns_losses = {"return": -0.03, "loss": -0.08}
        trading_graph.reflect_and_remember(returns_losses)

        # Verify reflection was called for all components
        trading_graph.reflector.reflect_bull_researcher.assert_called_once()
        trading_graph.reflector.reflect_bear_researcher.assert_called_once()
        trading_graph.reflector.reflect_trader.assert_called_once()
        trading_graph.reflector.reflect_invest_judge.assert_called_once()
        trading_graph.reflector.reflect_risk_manager.assert_called_once()

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_debug_mode_integration(
        self, mock_toolkit, mock_chat_openai, integration_config
    ):
        """Test integration in debug mode."""
        # Setup
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm

        mock_toolkit_instance = Mock()
        mock_toolkit_instance.config = integration_config
        self._setup_toolkit_methods(mock_toolkit_instance)
        mock_toolkit.return_value = mock_toolkit_instance

        # Mock graph stream for debug mode
        mock_graph = Mock()
        mock_chunks = [
            {"messages": [Mock()]},
            {"messages": [Mock()]},
            self._create_mock_final_state(),  # Final chunk
        ]
        for chunk in mock_chunks:
            if "messages" in chunk and chunk["messages"]:
                for msg in chunk["messages"]:
                    if hasattr(msg, "pretty_print"):
                        msg.pretty_print = Mock()
                    else:
                        msg.pretty_print = Mock()

        mock_graph.stream.return_value = mock_chunks

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.graph.trading_graph.set_config"):
                trading_graph = TradingAgentsGraph(
                    debug=True, config=integration_config
                )
                trading_graph.graph = mock_graph

                # Mock components
                trading_graph.propagator.create_initial_state = Mock(
                    return_value={
                        "company_of_interest": "AMZN",
                        "trade_date": "2024-05-25",
                        "messages": [],
                    }
                )
                trading_graph.propagator.get_graph_args = Mock(return_value={})
                trading_graph.signal_processor.process_signal = Mock(return_value="BUY")

        # Execute in debug mode
        with patch("builtins.open", create=True):
            with patch("json.dump"):
                final_state, decision = trading_graph.propagate("AMZN", "2024-05-25")

        # Verify debug mode was used
        mock_graph.stream.assert_called_once()
        assert final_state is not None
        assert decision == "BUY"

    @pytest.mark.parametrize(
        "ticker,date",
        [
            ("AAPL", "2024-01-15"),
            ("TSLA", "2024-02-20"),
            ("NVDA", "2024-03-10"),
            ("MSFT", "2024-04-05"),
        ],
    )
    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_multiple_stocks_integration(
        self, mock_toolkit, mock_chat_openai, ticker, date, integration_config
    ):
        """Test integration with different stocks and dates."""
        # Setup
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm

        mock_toolkit_instance = Mock()
        mock_toolkit_instance.config = integration_config
        self._setup_toolkit_methods(mock_toolkit_instance)
        mock_toolkit.return_value = mock_toolkit_instance

        mock_graph = Mock()
        mock_final_state = self._create_mock_final_state(ticker, date)
        mock_graph.invoke.return_value = mock_final_state

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.graph.trading_graph.set_config"):
                trading_graph = TradingAgentsGraph(config=integration_config)
                trading_graph.graph = mock_graph

                # Mock components
                trading_graph.propagator.create_initial_state = Mock(
                    return_value={
                        "company_of_interest": ticker,
                        "trade_date": date,
                        "messages": [],
                    }
                )
                trading_graph.propagator.get_graph_args = Mock(return_value={})
                trading_graph.signal_processor.process_signal = Mock(
                    return_value="HOLD"
                )

        # Execute
        with patch("builtins.open", create=True):
            with patch("json.dump"):
                final_state, decision = trading_graph.propagate(ticker, date)

        # Verify
        assert final_state["company_of_interest"] == ticker
        assert final_state["trade_date"] == date
        assert decision in ["BUY", "SELL", "HOLD"]

    def _setup_toolkit_methods(self, toolkit_mock):
        """Helper method to setup all toolkit methods."""
        # Market analyst tools
        toolkit_mock.get_YFin_data = Mock()
        toolkit_mock.get_YFin_data_online = Mock()
        toolkit_mock.get_stockstats_indicators_report = Mock()
        toolkit_mock.get_stockstats_indicators_report_online = Mock()

        # Social media analyst tools
        toolkit_mock.get_reddit_stock_info = Mock()
        toolkit_mock.get_stock_news_openai = Mock()

        # News analyst tools
        toolkit_mock.get_finnhub_news = Mock()
        toolkit_mock.get_reddit_news = Mock()
        toolkit_mock.get_global_news_openai = Mock()
        toolkit_mock.get_google_news = Mock()

        # Fundamentals analyst tools
        toolkit_mock.get_fundamentals_openai = Mock()
        toolkit_mock.get_finnhub_company_insider_sentiment = Mock()
        toolkit_mock.get_finnhub_company_insider_transactions = Mock()
        toolkit_mock.get_simfin_balance_sheet = Mock()
        toolkit_mock.get_simfin_cashflow = Mock()
        toolkit_mock.get_simfin_income_stmt = Mock()

    def _create_mock_final_state(self, ticker="AAPL", date="2024-05-10"):
        """Helper method to create a mock final state."""
        return {
            "company_of_interest": ticker,
            "trade_date": date,
            "market_report": f"Market analysis for {ticker} shows positive trends.",
            "sentiment_report": "Social sentiment is bullish.",
            "news_report": "Recent news is favorable.",
            "fundamentals_report": "Strong fundamental indicators.",
            "investment_debate_state": {
                "bull_history": ["Bull argument 1", "Bull argument 2"],
                "bear_history": ["Bear argument 1"],
                "history": ["Debate round 1"],
                "current_response": "Final bull argument",
                "judge_decision": "BUY recommended based on analysis",
            },
            "trader_investment_plan": "Buy 100 shares at market price",
            "risk_debate_state": {
                "risky_history": ["High risk tolerance argument"],
                "safe_history": ["Conservative approach argument"],
                "neutral_history": ["Balanced view"],
                "history": ["Risk assessment round 1"],
                "judge_decision": "MODERATE_RISK acceptable",
            },
            "investment_plan": "Execute buy order with stop-loss at 5%",
            "final_trade_decision": "BUY",
        }


@pytest.mark.integration
@pytest.mark.slow
class TestPerformanceIntegration:
    """Performance and stress tests for the trading system."""

    @patch("tradingagents.graph.trading_graph.ChatOpenAI")
    @patch("tradingagents.graph.trading_graph.Toolkit")
    def test_multiple_consecutive_runs(
        self, mock_toolkit, mock_chat_openai, sample_config, temp_data_dir
    ):
        """Test multiple consecutive trading decisions."""
        sample_config["project_dir"] = temp_data_dir

        # Setup
        mock_llm = Mock()
        mock_chat_openai.return_value = mock_llm

        mock_toolkit_instance = Mock()
        mock_toolkit_instance.config = sample_config
        mock_toolkit.return_value = mock_toolkit_instance

        mock_graph = Mock()

        with patch("tradingagents.graph.trading_graph.FinancialSituationMemory"):
            with patch("tradingagents.graph.trading_graph.set_config"):
                trading_graph = TradingAgentsGraph(config=sample_config)
                trading_graph.graph = mock_graph

                # Mock components
                trading_graph.propagator.create_initial_state = Mock()
                trading_graph.propagator.get_graph_args = Mock(return_value={})
                trading_graph.signal_processor.process_signal = Mock()

        # Run multiple consecutive decisions
        decisions = []
        for i, ticker in enumerate(["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL"]):
            date = f"2024-05-{10+i:02d}"

            # Mock responses for each run
            mock_final_state = {
                "company_of_interest": ticker,
                "trade_date": date,
                "final_trade_decision": ["BUY", "SELL", "HOLD"][i % 3],
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
            }
            mock_graph.invoke.return_value = mock_final_state
            trading_graph.propagator.create_initial_state.return_value = {
                "company_of_interest": ticker,
                "trade_date": date,
                "messages": [],
            }
            trading_graph.signal_processor.process_signal.return_value = (
                mock_final_state["final_trade_decision"]
            )

            with patch("builtins.open", create=True):
                with patch("json.dump"):
                    final_state, decision = trading_graph.propagate(ticker, date)

            decisions.append(decision)

        # Verify all runs completed successfully
        assert len(decisions) == 5
        assert all(d in ["BUY", "SELL", "HOLD"] for d in decisions)
