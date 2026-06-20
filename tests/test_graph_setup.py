import unittest
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.graph.setup import GraphSetup


def _mock_llm():
    return MagicMock()


def _mock_tool_nodes():
    return {
        "market": MagicMock(),
        "social": MagicMock(),
        "news": MagicMock(),
        "fundamentals": MagicMock(),
        "governance": MagicMock(),
        "industry": MagicMock(),
    }


@pytest.mark.unit
class GraphSetupConstructorTests(unittest.TestCase):
    def test_stores_components(self):
        quick = _mock_llm()
        deep = _mock_llm()
        tools = _mock_tool_nodes()
        cl = MagicMock()
        gs = GraphSetup(quick, deep, tools, cl, analyst_concurrency_limit=2)
        self.assertIs(gs.quick_thinking_llm, quick)
        self.assertIs(gs.deep_thinking_llm, deep)
        self.assertIs(gs.tool_nodes, tools)
        self.assertIs(gs.conditional_logic, cl)
        self.assertEqual(gs.analyst_concurrency_limit, 2)

    def test_default_concurrency(self):
        gs = GraphSetup(_mock_llm(), _mock_llm(), _mock_tool_nodes(), MagicMock())
        self.assertEqual(gs.analyst_concurrency_limit, 1)


@pytest.mark.unit
class SetupGraphTests(unittest.TestCase):
    def setUp(self):
        self.quick = _mock_llm()
        self.deep = _mock_llm()
        self.tools = _mock_tool_nodes()
        self.cl = MagicMock()
        self.gs = GraphSetup(self.quick, self.deep, self.tools, self.cl)

    @patch("tradingagents.graph.setup.StateGraph")
    @patch("tradingagents.graph.setup.create_market_analyst")
    @patch("tradingagents.graph.setup.create_sentiment_analyst")
    @patch("tradingagents.graph.setup.create_news_analyst")
    @patch("tradingagents.graph.setup.create_fundamentals_analyst")
    @patch("tradingagents.graph.setup.create_bull_researcher")
    @patch("tradingagents.graph.setup.create_bear_researcher")
    @patch("tradingagents.graph.setup.create_research_manager")
    @patch("tradingagents.graph.setup.create_trader")
    @patch("tradingagents.graph.setup.create_aggressive_debator")
    @patch("tradingagents.graph.setup.create_neutral_debator")
    @patch("tradingagents.graph.setup.create_conservative_debator")
    @patch("tradingagents.graph.setup.create_portfolio_manager")
    @patch("tradingagents.graph.setup.create_msg_delete")
    def test_setup_graph_default_analysts(
        self,
        mock_delete,
        mock_pm,
        mock_cons,
        mock_neutral,
        mock_agg,
        mock_trader,
        mock_rm,
        mock_bear,
        mock_bull,
        mock_fund,
        mock_news,
        mock_sent,
        mock_market,
        mock_stategraph,
    ):
        workflow_instance = MagicMock()
        mock_stategraph.return_value = workflow_instance
        workflow = self.gs.setup_graph()
        self.assertIs(workflow, workflow_instance)

        mock_stategraph.assert_called_once()
        mock_market.assert_called_once_with(self.quick)
        mock_bull.assert_called_once_with(self.quick)
        mock_trader.assert_called_once_with(self.quick)
        mock_pm.assert_called_once_with(self.deep)

        add_node_calls = [
            c[0][0] for c in workflow_instance.add_node.call_args_list
        ]
        self.assertIn("Market Analyst", add_node_calls)
        self.assertIn("Sentiment Analyst", add_node_calls)
        self.assertIn("News Analyst", add_node_calls)
        self.assertIn("Fundamentals Analyst", add_node_calls)
        self.assertIn("Bull Researcher", add_node_calls)
        self.assertIn("Bear Researcher", add_node_calls)
        self.assertIn("Research Manager", add_node_calls)
        self.assertIn("Trader", add_node_calls)
        self.assertIn("Aggressive Analyst", add_node_calls)
        self.assertIn("Neutral Analyst", add_node_calls)
        self.assertIn("Conservative Analyst", add_node_calls)
        self.assertIn("Portfolio Manager", add_node_calls)

        add_edge_calls = [
            c[0][0] for c in workflow_instance.add_edge.call_args_list
        ]
        self.assertIn("Portfolio Manager", add_edge_calls)

    @patch("tradingagents.graph.setup.StateGraph")
    @patch("tradingagents.graph.setup.create_market_analyst")
    @patch("tradingagents.graph.setup.create_sentiment_analyst")
    @patch("tradingagents.graph.setup.create_news_analyst")
    @patch("tradingagents.graph.setup.create_fundamentals_analyst")
    @patch("tradingagents.graph.setup.create_governance_analyst")
    @patch("tradingagents.graph.setup.create_industry_analyst")
    @patch("tradingagents.graph.setup.create_bull_researcher")
    @patch("tradingagents.graph.setup.create_bear_researcher")
    @patch("tradingagents.graph.setup.create_research_manager")
    @patch("tradingagents.graph.setup.create_trader")
    @patch("tradingagents.graph.setup.create_aggressive_debator")
    @patch("tradingagents.graph.setup.create_neutral_debator")
    @patch("tradingagents.graph.setup.create_conservative_debator")
    @patch("tradingagents.graph.setup.create_portfolio_manager")
    @patch("tradingagents.graph.setup.create_msg_delete")
    def test_setup_graph_custom_analysts(
        self,
        mock_delete,
        mock_pm,
        mock_cons,
        mock_neutral,
        mock_agg,
        mock_trader,
        mock_rm,
        mock_bear,
        mock_bull,
        mock_gov,
        mock_ind,
        mock_fund,
        mock_news,
        mock_sent,
        mock_market,
        mock_stategraph,
    ):
        workflow_instance = MagicMock()
        mock_stategraph.return_value = workflow_instance
        workflow = self.gs.setup_graph(
            selected_analysts=["market", "governance", "industry"]
        )
        self.assertIs(workflow, workflow_instance)
        mock_market.assert_called_once()
        mock_gov.assert_called_once()
        mock_ind.assert_called_once()

    @patch("tradingagents.graph.setup.StateGraph")
    def test_uses_provided_tool_nodes(self, mock_stategraph):
        workflow = MagicMock()
        mock_stategraph.return_value = workflow
        gs = GraphSetup(self.quick, self.deep, self.tools, self.cl)
        gs.setup_graph()
        tool_node_short_keys = {"market", "social", "news", "fundamentals"}
        for call in workflow.add_node.call_args_list:
            name = call[0][0]
            short = name.replace("tools_", "")
            if short in tool_node_short_keys:
                self.assertIn(short, self.tools)


if __name__ == "__main__":
    unittest.main()
