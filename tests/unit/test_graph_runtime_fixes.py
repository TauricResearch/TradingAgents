"""Tests for graph runtime fixes - TDD approach.

These tests verify:
1. Tools_* nodes are removed from graph compilation
2. ConditionalLogic handles missing debate/risk state fields safely
3. Portfolio initial state includes ticker_analyses
4. Trading graph logging handles incomplete nested state
"""

from unittest.mock import MagicMock, patch

from tradingagents.agents.utils.agent_states import InvestDebateState
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.portfolio_graph import PortfolioGraph
from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.trading_graph import TradingAgentsGraph

# ---------------------------------------------------------------------------
# A. Test tools_* nodes are removed from graph
# ---------------------------------------------------------------------------


class TestToolsNodesRemoved:
    """Verify that dormant tools_* nodes are no longer compiled into the graph."""

    def test_graph_does_not_contain_tools_market_node(self):
        """Market analyst should go directly to Msg Clear, not tools_market."""
        quick_llm = MagicMock(name="quick")
        mid_llm = MagicMock(name="mid")
        deep_llm = MagicMock(name="deep")

        news_evidence_store = MagicMock(name="news_evidence_store")

        setup = GraphSetup(
            quick_thinking_llm=quick_llm,
            mid_thinking_llm=mid_llm,
            deep_thinking_llm=deep_llm,
            bull_memory=MagicMock(),
            bear_memory=MagicMock(),
            trader_memory=MagicMock(),
            invest_judge_memory=MagicMock(),
            portfolio_manager_memory=MagicMock(),
            conditional_logic=MagicMock(),
            news_evidence_store=news_evidence_store,
        )

        compiled_graph = setup.setup_graph(selected_analysts=["market"])

        # Get the list of nodes in the compiled graph
        nodes = list(compiled_graph.nodes.keys())

        # Assert tools_market is NOT in the graph
        assert "tools_market" not in nodes

    def test_graph_does_not_contain_any_tools_nodes(self):
        """All tools_* nodes should be removed from the graph."""
        quick_llm = MagicMock(name="quick")
        mid_llm = MagicMock(name="mid")
        deep_llm = MagicMock(name="deep")

        news_evidence_store = MagicMock(name="news_evidence_store")

        setup = GraphSetup(
            quick_thinking_llm=quick_llm,
            mid_thinking_llm=mid_llm,
            deep_thinking_llm=deep_llm,
            bull_memory=MagicMock(),
            bear_memory=MagicMock(),
            trader_memory=MagicMock(),
            invest_judge_memory=MagicMock(),
            portfolio_manager_memory=MagicMock(),
            conditional_logic=MagicMock(),
            news_evidence_store=news_evidence_store,
        )

        compiled_graph = setup.setup_graph(
            selected_analysts=["market", "social", "news", "fundamentals"]
        )
        nodes = list(compiled_graph.nodes.keys())

        # None of the tools_* nodes should exist
        assert "tools_market" not in nodes
        assert "tools_social" not in nodes
        assert "tools_news" not in nodes
        assert "tools_fundamentals" not in nodes


# ---------------------------------------------------------------------------
# C. Test ConditionalLogic defensive behavior
# ---------------------------------------------------------------------------


class TestConditionalLogicDefensive:
    """Verify ConditionalLogic handles missing state fields gracefully."""

    def test_should_continue_debate_handles_missing_investment_debate_state(self):
        """should_continue_debate should not crash when investment_debate_state is missing."""
        cl = ConditionalLogic(max_debate_rounds=2)

        # State missing investment_debate_state entirely
        state = {}

        # Should not crash; should return a sensible default (Research Manager to finish)
        result = cl.should_continue_debate(state)
        assert result == "Research Manager"

    def test_should_continue_debate_handles_missing_count(self):
        """should_continue_debate should handle missing count field."""
        cl = ConditionalLogic(max_debate_rounds=2)

        # State with investment_debate_state but no count
        state = {
            "investment_debate_state": InvestDebateState(
                bull_history="",
                bear_history="",
                history="",
                current_response="Bull: some argument",
                judge_decision="",
                count=None,  # Missing or None
            )
        }

        # Should not crash
        result = cl.should_continue_debate(state)
        # When count is missing, should default to ending debate
        assert result == "Research Manager"

    def test_should_continue_debate_handles_missing_current_response(self):
        """should_continue_debate should handle missing current_response field."""
        cl = ConditionalLogic(max_debate_rounds=2)

        state = {
            "investment_debate_state": InvestDebateState(
                bull_history="",
                bear_history="",
                history="",
                current_response=None,  # Missing
                judge_decision="",
                count=0,
            )
        }

        # Should not crash; should default to one of the speakers
        result = cl.should_continue_debate(state)
        assert result in ["Bull Researcher", "Bear Researcher", "Research Manager"]


# ---------------------------------------------------------------------------
# D. Test Portfolio initial state includes ticker_analyses
# ---------------------------------------------------------------------------


class TestPortfolioInitialState:
    """Verify PortfolioGraph.run() initializes ticker_analyses."""

    def test_portfolio_run_initializes_ticker_analyses(self):
        """PortfolioGraph.run() initial state should include ticker_analyses = {}."""
        config = {
            "llm_provider": "openai",
            "quick_think_llm": "gpt-4",
            "mid_think_llm": "gpt-4",
            "deep_think_llm": "gpt-4",
            "portfolio_id": "test",
        }

        with (
            patch("tradingagents.graph.portfolio_graph.create_holding_reviewer"),
            patch("tradingagents.graph.portfolio_graph.create_pm_decision_agent"),
            patch("tradingagents.graph.portfolio_graph.create_macro_summary_agent"),
            patch("tradingagents.graph.portfolio_graph.create_micro_summary_agent"),
            patch("tradingagents.graph.portfolio_graph.PortfolioGraphSetup") as mock_setup,
            patch("tradingagents.graph.portfolio_graph.create_llm_client") as mock_llm_client,
        ):
            # Mock the LLM client
            mock_llm = MagicMock()
            mock_llm_client.return_value.get_llm.return_value = mock_llm

            # Mock the graph
            mock_compiled_graph = MagicMock()
            mock_setup.return_value.setup_graph.return_value = mock_compiled_graph

            # Capture the initial_state passed to invoke
            def capture_invoke(initial_state):
                # Verify ticker_analyses is in initial_state
                assert "ticker_analyses" in initial_state
                assert initial_state["ticker_analyses"] == {}
                return {"execution_result": "done"}

            mock_compiled_graph.invoke = capture_invoke

            portfolio_graph = PortfolioGraph(config=config, debug=False)

            result = portfolio_graph.run(
                portfolio_id="test_portfolio",
                date="2024-01-01",
                prices={"AAPL": 150.0},
                scan_summary={"stocks_to_investigate": []},
            )

            # If we got here without assertion error, test passed
            assert result is not None


# ---------------------------------------------------------------------------
# B. Test trading graph logging handles incomplete state
# ---------------------------------------------------------------------------


class TestTradingGraphLogging:
    """Verify TradingAgentsGraph._log_state() handles incomplete nested state."""

    def test_log_state_handles_missing_investment_debate_fields(self):
        """_log_state should not crash when investment_debate_state fields are missing."""
        config = {
            "llm_provider": "openai",
            "quick_think_llm": "gpt-4",
            "mid_think_llm": "gpt-4",
            "deep_think_llm": "gpt-4",
            "project_dir": "/tmp/test",
        }

        with (
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_llm_client,
            patch("tradingagents.graph.trading_graph.set_config"),
            patch("os.makedirs"),
        ):
            mock_llm = MagicMock()
            mock_llm_client.return_value.get_llm.return_value = mock_llm

            graph = TradingAgentsGraph(
                selected_analysts=["market"],
                debug=False,
                config=config,
            )

            # Create a state with incomplete investment_debate_state
            incomplete_state = {
                "company_of_interest": "AAPL",
                "trade_date": "2024-01-01",
                "market_report": "Market report",
                "macro_regime_report": "",
                "sentiment_report": "Sentiment report",
                "news_report": "News report",
                "fundamentals_report": "Fundamentals report",
                "research_packet_summary": "",
                "investment_debate_state": {
                    # Missing bull_history, bear_history, etc.
                },
                "trader_investment_plan": "Trader plan",
                "risk_debate_state": {
                    # Missing aggressive_history, etc.
                },
                "investment_plan": "Investment plan",
                "final_trade_decision": "Hold",
            }

            # Mock the file writing to avoid actual I/O
            with (
                patch("builtins.open"),
                patch("tradingagents.report_paths.get_eval_dir") as mock_get_dir,
            ):
                mock_dir = MagicMock()
                mock_dir.mkdir = MagicMock()
                mock_get_dir.return_value = mock_dir

                # Set the ticker so get_eval_dir doesn't fail
                graph.ticker = "AAPL"

                # This should not crash
                graph._log_state("2024-01-01", incomplete_state)

                # Verify the log dict was created
                assert "2024-01-01" in graph.log_states_dict

    def test_log_state_handles_missing_risk_debate_fields(self):
        """_log_state should not crash when risk_debate_state fields are missing."""
        config = {
            "llm_provider": "openai",
            "quick_think_llm": "gpt-4",
            "mid_think_llm": "gpt-4",
            "deep_think_llm": "gpt-4",
            "project_dir": "/tmp/test",
        }

        with (
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_llm_client,
            patch("tradingagents.graph.trading_graph.set_config"),
            patch("os.makedirs"),
        ):
            mock_llm = MagicMock()
            mock_llm_client.return_value.get_llm.return_value = mock_llm

            graph = TradingAgentsGraph(
                selected_analysts=["market"],
                debug=False,
                config=config,
            )

            # Create a state with incomplete risk_debate_state
            incomplete_state = {
                "company_of_interest": "AAPL",
                "trade_date": "2024-01-01",
                "market_report": "Market report",
                "macro_regime_report": "",
                "sentiment_report": "Sentiment report",
                "news_report": "News report",
                "fundamentals_report": "Fundamentals report",
                "research_packet_summary": "",
                "investment_debate_state": {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                },
                "trader_investment_plan": "Trader plan",
                "risk_debate_state": {
                    # Missing fields like aggressive_history
                    "judge_decision": "Decision",
                },
                "investment_plan": "Investment plan",
                "final_trade_decision": "Hold",
            }

            with (
                patch("builtins.open"),
                patch("tradingagents.report_paths.get_eval_dir") as mock_get_dir,
            ):
                mock_dir = MagicMock()
                mock_dir.mkdir = MagicMock()
                mock_get_dir.return_value = mock_dir

                # Set the ticker so get_eval_dir doesn't fail
                graph.ticker = "AAPL"

                # This should not crash
                graph._log_state("2024-01-01", incomplete_state)

                assert "2024-01-01" in graph.log_states_dict
