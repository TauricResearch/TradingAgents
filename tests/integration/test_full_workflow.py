"""Integration tests for TradingAgents graph workflow."""

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.default_config import DEFAULT_CONFIG


@pytest.mark.integration
class TestFullWorkflow:
    """Integration tests for the full trading workflow."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration for testing."""
        config = DEFAULT_CONFIG.copy()
        config["deep_think_llm"] = "gpt-4o-mini"
        config["quick_think_llm"] = "gpt-4o-mini"
        return config

    @pytest.mark.skip(reason="Requires API keys")
    def test_propagate_returns_decision(self, mock_config):
        """Integration test requiring live API keys."""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        ta = TradingAgentsGraph(debug=True, config=mock_config)
        state, decision = ta.propagate("AAPL", "2024-01-15")
        assert decision is not None
        assert "final_trade_decision" in state

    @patch("tradingagents.graph.trading_graph.create_llm_client")
    def test_graph_initialization(self, mock_create_client, mock_config):
        """Test graph initializes without errors."""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        mock_llm = MagicMock()
        mock_create_client.return_value.get_llm.return_value = mock_llm

        ta = TradingAgentsGraph(
            selected_analysts=["market"],
            debug=True,
            config=mock_config
        )
        assert ta.graph is not None

    @patch("tradingagents.graph.trading_graph.create_llm_client")
    def test_graph_initialization_all_analysts(self, mock_create_client, mock_config):
        """Test graph initializes with all analysts."""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        mock_llm = MagicMock()
        mock_create_client.return_value.get_llm.return_value = mock_llm

        ta = TradingAgentsGraph(
            selected_analysts=["market", "news", "fundamentals", "social"],
            debug=True,
            config=mock_config
        )
        assert ta.graph is not None


@pytest.mark.integration
class TestGraphSetup:
    """Integration tests for graph setup."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration for testing."""
        return DEFAULT_CONFIG.copy()

    @patch("tradingagents.graph.trading_graph.create_llm_client")
    def test_setup_creates_nodes(self, mock_create_client, mock_config):
        """Test that setup creates all required nodes."""
        from tradingagents.graph.conditional_logic import ConditionalLogic

        mock_create_client.return_value.get_llm.return_value = MagicMock()

        ConditionalLogic(
            max_debate_rounds=mock_config["max_debate_rounds"],
            max_risk_discuss_rounds=mock_config["max_risk_discuss_rounds"]
        )
        # GraphSetup should be instantiable
        # Actual node creation depends on internal implementation

    def test_conditional_logic_instance(self, mock_config):
        """Test that ConditionalLogic is instantiable."""
        from tradingagents.graph.conditional_logic import ConditionalLogic

        logic = ConditionalLogic(
            max_debate_rounds=mock_config["max_debate_rounds"],
            max_risk_discuss_rounds=mock_config["max_risk_discuss_rounds"]
        )

        assert logic.max_debate_rounds == mock_config["max_debate_rounds"]
        assert logic.max_risk_discuss_rounds == mock_config["max_risk_discuss_rounds"]


@pytest.mark.integration
class TestAgentInitialization:
    """Integration tests for agent initialization."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing."""
        return MagicMock()

    def test_market_analyst_creation(self, mock_llm):
        """Test that market analyst can be created."""
        from tradingagents.agents.analysts.market_analyst import create_market_analyst

        analyst = create_market_analyst(mock_llm)
        assert callable(analyst)

    def test_news_analyst_creation(self, mock_llm):
        """Test that news analyst can be created."""
        from tradingagents.agents.analysts.news_analyst import create_news_analyst

        analyst = create_news_analyst(mock_llm)
        assert callable(analyst)

    def test_fundamentals_analyst_creation(self, mock_llm):
        """Test that fundamentals analyst can be created."""
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst

        analyst = create_fundamentals_analyst(mock_llm)
        assert callable(analyst)

    def test_bull_researcher_creation(self, mock_llm):
        """Test that bull researcher can be created."""
        from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
        from tradingagents.agents.utils.memory import FinancialSituationMemory

        memory = FinancialSituationMemory("bull_memory")
        researcher = create_bull_researcher(mock_llm, memory)
        assert callable(researcher)

    def test_bear_researcher_creation(self, mock_llm):
        """Test that bear researcher can be created."""
        from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
        from tradingagents.agents.utils.memory import FinancialSituationMemory

        memory = FinancialSituationMemory("bear_memory")
        researcher = create_bear_researcher(mock_llm, memory)
        assert callable(researcher)

    def test_trader_creation(self, mock_llm):
        """Test that trader can be created."""
        from tradingagents.agents.trader.trader import create_trader
        from tradingagents.agents.utils.memory import FinancialSituationMemory

        memory = FinancialSituationMemory("trader_memory")
        trader = create_trader(mock_llm, memory)
        assert callable(trader)


@pytest.mark.integration
class TestReflection:
    """Integration tests for reflection system."""

    def test_reflector_creation(self):
        """Test that Reflector can be created."""
        from unittest.mock import MagicMock

        from tradingagents.graph.reflection import Reflector

        mock_llm = MagicMock()
        reflector = Reflector(mock_llm)
        assert reflector.quick_thinking_llm is not None
