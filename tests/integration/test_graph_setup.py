from unittest.mock import MagicMock, patch

import pytest

from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import GraphSetup


class TestGraphSetup:
    def setup_method(self):
        self.mock_llm = MagicMock()
        self.mock_tool_nodes = {
            "market": MagicMock(),
            "social": MagicMock(),
            "news": MagicMock(),
            "fundamentals": MagicMock(),
        }
        self.mock_memory = MagicMock()
        self.conditional_logic = ConditionalLogic()

    def create_graph_setup(self):
        return GraphSetup(
            quick_thinking_llm=self.mock_llm,
            deep_thinking_llm=self.mock_llm,
            tool_nodes=self.mock_tool_nodes,
            bull_memory=self.mock_memory,
            bear_memory=self.mock_memory,
            trader_memory=self.mock_memory,
            invest_judge_memory=self.mock_memory,
            risk_manager_memory=self.mock_memory,
            conditional_logic=self.conditional_logic,
        )

    def test_graph_setup_initialization(self):
        setup = self.create_graph_setup()

        assert setup.quick_thinking_llm == self.mock_llm
        assert setup.deep_thinking_llm == self.mock_llm
        assert setup.tool_nodes == self.mock_tool_nodes
        assert setup.conditional_logic == self.conditional_logic

    def test_setup_graph_with_all_analysts(self):
        setup = self.create_graph_setup()

        with (
            patch("tradingagents.graph.setup.create_market_analyst") as mock_market,
            patch(
                "tradingagents.graph.setup.create_social_media_analyst"
            ) as mock_social,
            patch("tradingagents.graph.setup.create_news_analyst") as mock_news,
            patch("tradingagents.graph.setup.create_fundamentals_analyst") as mock_fund,
            patch("tradingagents.graph.setup.create_bull_researcher") as mock_bull,
            patch("tradingagents.graph.setup.create_bear_researcher") as mock_bear,
            patch("tradingagents.graph.setup.create_research_manager") as mock_rm,
            patch("tradingagents.graph.setup.create_trader") as mock_trader,
            patch("tradingagents.graph.setup.create_risky_debator") as mock_risky,
            patch("tradingagents.graph.setup.create_neutral_debator") as mock_neutral,
            patch("tradingagents.graph.setup.create_safe_debator") as mock_safe,
            patch("tradingagents.graph.setup.create_risk_manager") as mock_risk_mgr,
        ):
            mock_market.return_value = MagicMock()
            mock_social.return_value = MagicMock()
            mock_news.return_value = MagicMock()
            mock_fund.return_value = MagicMock()
            mock_bull.return_value = MagicMock()
            mock_bear.return_value = MagicMock()
            mock_rm.return_value = MagicMock()
            mock_trader.return_value = MagicMock()
            mock_risky.return_value = MagicMock()
            mock_neutral.return_value = MagicMock()
            mock_safe.return_value = MagicMock()
            mock_risk_mgr.return_value = MagicMock()

            graph = setup.setup_graph(["market", "social", "news", "fundamentals"])

            mock_market.assert_called_once()
            mock_social.assert_called_once()
            mock_news.assert_called_once()
            mock_fund.assert_called_once()
            mock_bull.assert_called_once()
            mock_bear.assert_called_once()
            mock_rm.assert_called_once()
            mock_trader.assert_called_once()

    def test_setup_graph_with_single_analyst(self):
        setup = self.create_graph_setup()

        with (
            patch("tradingagents.graph.setup.create_market_analyst") as mock_market,
            patch(
                "tradingagents.graph.setup.create_social_media_analyst"
            ) as mock_social,
            patch("tradingagents.graph.setup.create_news_analyst") as mock_news,
            patch("tradingagents.graph.setup.create_fundamentals_analyst") as mock_fund,
            patch("tradingagents.graph.setup.create_bull_researcher") as mock_bull,
            patch("tradingagents.graph.setup.create_bear_researcher") as mock_bear,
            patch("tradingagents.graph.setup.create_research_manager") as mock_rm,
            patch("tradingagents.graph.setup.create_trader") as mock_trader,
            patch("tradingagents.graph.setup.create_risky_debator") as mock_risky,
            patch("tradingagents.graph.setup.create_neutral_debator") as mock_neutral,
            patch("tradingagents.graph.setup.create_safe_debator") as mock_safe,
            patch("tradingagents.graph.setup.create_risk_manager") as mock_risk_mgr,
        ):
            mock_market.return_value = MagicMock()
            mock_bull.return_value = MagicMock()
            mock_bear.return_value = MagicMock()
            mock_rm.return_value = MagicMock()
            mock_trader.return_value = MagicMock()
            mock_risky.return_value = MagicMock()
            mock_neutral.return_value = MagicMock()
            mock_safe.return_value = MagicMock()
            mock_risk_mgr.return_value = MagicMock()

            graph = setup.setup_graph(["market"])

            mock_market.assert_called_once()
            mock_social.assert_not_called()
            mock_news.assert_not_called()
            mock_fund.assert_not_called()

    def test_setup_graph_empty_analysts_raises(self):
        setup = self.create_graph_setup()

        with pytest.raises(ValueError, match="no analysts selected"):
            setup.setup_graph([])

    def test_setup_graph_returns_compiled_graph(self):
        setup = self.create_graph_setup()

        with (
            patch("tradingagents.graph.setup.create_market_analyst") as mock_market,
            patch("tradingagents.graph.setup.create_bull_researcher") as mock_bull,
            patch("tradingagents.graph.setup.create_bear_researcher") as mock_bear,
            patch("tradingagents.graph.setup.create_research_manager") as mock_rm,
            patch("tradingagents.graph.setup.create_trader") as mock_trader,
            patch("tradingagents.graph.setup.create_risky_debator") as mock_risky,
            patch("tradingagents.graph.setup.create_neutral_debator") as mock_neutral,
            patch("tradingagents.graph.setup.create_safe_debator") as mock_safe,
            patch("tradingagents.graph.setup.create_risk_manager") as mock_risk_mgr,
        ):
            mock_market.return_value = MagicMock()
            mock_bull.return_value = MagicMock()
            mock_bear.return_value = MagicMock()
            mock_rm.return_value = MagicMock()
            mock_trader.return_value = MagicMock()
            mock_risky.return_value = MagicMock()
            mock_neutral.return_value = MagicMock()
            mock_safe.return_value = MagicMock()
            mock_risk_mgr.return_value = MagicMock()

            graph = setup.setup_graph(["market"])

            assert graph is not None
            assert hasattr(graph, "invoke") or hasattr(graph, "stream")
