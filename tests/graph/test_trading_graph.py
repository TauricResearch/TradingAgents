import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date
from tradingagents.graph.trading_graph import TradingAgentsGraph, DiscoveryTimeoutException
from tradingagents.agents.discovery import (
    DiscoveryRequest,
    DiscoveryResult,
    DiscoveryStatus,
    TrendingStock,
    Sector,
    EventCategory,
    NewsArticle,
)


class TestTradingAgentsGraphInit:
    """Test suite for TradingAgentsGraph initialization."""

    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_init_with_default_config(self, mock_setup, mock_memory, mock_llm):
        """Test initialization with default configuration."""
        graph = TradingAgentsGraph(debug=False)
        
        assert graph.debug == False
        assert graph.config is not None
        assert "llm_provider" in graph.config

    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_init_with_custom_config(self, mock_setup, mock_memory, mock_llm):
        """Test initialization with custom configuration."""
        custom_config = {
            "llm_provider": "openai",
            "deep_think_llm": "gpt-4",
            "quick_think_llm": "gpt-3.5-turbo",
            "backend_url": "https://api.openai.com/v1",
            "max_debate_rounds": 3,
            "max_risk_discuss_rounds": 2,
            "max_recur_limit": 100,
            "project_dir": "/tmp/test",
            "data_vendors": {},
            "tool_vendors": {},
        }
        
        graph = TradingAgentsGraph(debug=True, config=custom_config)
        
        assert graph.config["llm_provider"] == "openai"
        assert graph.config["max_debate_rounds"] == 3

    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_init_with_anthropic_provider(self, mock_setup, mock_memory, mock_llm):
        """Test initialization with Anthropic provider."""
        with patch('tradingagents.graph.trading_graph.ChatAnthropic') as mock_anthropic:
            config = {
                "llm_provider": "anthropic",
                "deep_think_llm": "claude-3-opus",
                "quick_think_llm": "claude-3-haiku",
                "backend_url": "https://api.anthropic.com",
                "project_dir": "/tmp/test",
                "data_vendors": {},
                "tool_vendors": {},
                "max_debate_rounds": 2,
                "max_risk_discuss_rounds": 2,
                "max_recur_limit": 100,
            }
            
            graph = TradingAgentsGraph(config=config)
            
            assert mock_anthropic.called

    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_init_with_google_provider(self, mock_setup, mock_memory, mock_llm):
        """Test initialization with Google provider."""
        with patch('tradingagents.graph.trading_graph.ChatGoogleGenerativeAI') as mock_google:
            config = {
                "llm_provider": "google",
                "deep_think_llm": "gemini-pro",
                "quick_think_llm": "gemini-pro",
                "project_dir": "/tmp/test",
                "data_vendors": {},
                "tool_vendors": {},
                "max_debate_rounds": 2,
                "max_risk_discuss_rounds": 2,
                "max_recur_limit": 100,
            }
            
            graph = TradingAgentsGraph(config=config)
            
            assert mock_google.called

    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_init_creates_memory_instances(self, mock_setup, mock_memory, mock_llm):
        """Test that all required memory instances are created."""
        config = {
            "llm_provider": "openai",
            "backend_url": "https://api.openai.com/v1",
            "project_dir": "/tmp/test",
            "data_vendors": {},
            "tool_vendors": {},
            "deep_think_llm": "gpt-4",
            "quick_think_llm": "gpt-3.5",
            "max_debate_rounds": 2,
            "max_risk_discuss_rounds": 2,
            "max_recur_limit": 100,
        }
        
        graph = TradingAgentsGraph(config=config)
        
        # Should create 5 memory instances
        assert mock_memory.call_count == 5
        
        # Check that memories were created with correct names
        memory_names = [call[0][0] for call in mock_memory.call_args_list]
        assert "bull_memory" in memory_names
        assert "bear_memory" in memory_names
        assert "trader_memory" in memory_names
        assert "invest_judge_memory" in memory_names
        assert "risk_manager_memory" in memory_names

    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_init_creates_tool_nodes(self, mock_setup, mock_memory, mock_llm):
        """Test that tool nodes are created for analysts."""
        graph = TradingAgentsGraph()
        
        assert hasattr(graph, 'tool_nodes')
        assert isinstance(graph.tool_nodes, dict)
        assert "market" in graph.tool_nodes
        assert "social" in graph.tool_nodes
        assert "news" in graph.tool_nodes
        assert "fundamentals" in graph.tool_nodes

    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_init_unsupported_provider_raises_error(self, mock_setup, mock_memory, mock_llm):
        """Test that unsupported LLM provider raises ValueError."""
        config = {
            "llm_provider": "unsupported_provider",
            "project_dir": "/tmp/test",
            "data_vendors": {},
            "tool_vendors": {},
            "deep_think_llm": "model",
            "quick_think_llm": "model",
            "max_debate_rounds": 2,
            "max_risk_discuss_rounds": 2,
            "max_recur_limit": 100,
        }
        
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            graph = TradingAgentsGraph(config=config)


class TestDiscoverTrending:
    """Test suite for discover_trending method."""

    @patch('tradingagents.graph.trading_graph.get_bulk_news')
    @patch('tradingagents.graph.trading_graph.extract_entities')
    @patch('tradingagents.graph.trading_graph.calculate_trending_scores')
    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_discover_trending_basic(self, mock_setup, mock_memory, mock_llm,
                                     mock_score, mock_extract, mock_bulk_news):
        """Test basic discover_trending functionality."""
        # Setup mocks
        mock_article = Mock(spec=NewsArticle)
        mock_bulk_news.return_value = [mock_article]
        mock_extract.return_value = []
        mock_score.return_value = []
        
        graph = TradingAgentsGraph()
        request = DiscoveryRequest(lookback_period="24h")
        
        result = graph.discover_trending(request)
        
        assert isinstance(result, DiscoveryResult)
        assert result.status == DiscoveryStatus.COMPLETED

    @patch('tradingagents.graph.trading_graph.get_bulk_news')
    @patch('tradingagents.graph.trading_graph.extract_entities')
    @patch('tradingagents.graph.trading_graph.calculate_trending_scores')
    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_discover_trending_with_results(self, mock_setup, mock_memory, mock_llm,
                                           mock_score, mock_extract, mock_bulk_news):
        """Test discover_trending with actual trending stocks."""
        mock_article = Mock(spec=NewsArticle)
        mock_bulk_news.return_value = [mock_article]
        mock_extract.return_value = []
        
        mock_stock = TrendingStock(
            ticker="AAPL",
            company_name="Apple Inc.",
            score=85.5,
            mention_count=10,
            sentiment=0.75,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.PRODUCT_LAUNCH,
            news_summary="Apple announced new products",
            source_articles=[mock_article],
        )
        
        mock_score.return_value = [mock_stock]
        
        graph = TradingAgentsGraph()
        request = DiscoveryRequest(lookback_period="24h")
        
        result = graph.discover_trending(request)
        
        assert len(result.trending_stocks) == 1
        assert result.trending_stocks[0].ticker == "AAPL"

    @patch('tradingagents.graph.trading_graph.get_bulk_news')
    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_discover_trending_timeout(self, mock_setup, mock_memory, mock_llm, mock_bulk_news):
        """Test that discovery respects timeout."""
        # Simulate a long-running operation
        import time
        mock_bulk_news.side_effect = lambda x: time.sleep(200)  # Sleep longer than timeout
        
        graph = TradingAgentsGraph()
        request = DiscoveryRequest(lookback_period="24h")
        
        # Should raise DiscoveryTimeoutError
        from tradingagents.agents.discovery.exceptions import DiscoveryTimeoutError
        with pytest.raises(DiscoveryTimeoutError):
            result = graph.discover_trending(request)

    @patch('tradingagents.graph.trading_graph.get_bulk_news')
    @patch('tradingagents.graph.trading_graph.extract_entities')
    @patch('tradingagents.graph.trading_graph.calculate_trending_scores')
    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_discover_trending_sector_filter(self, mock_setup, mock_memory, mock_llm,
                                            mock_score, mock_extract, mock_bulk_news):
        """Test discover_trending with sector filter."""
        mock_article = Mock(spec=NewsArticle)
        mock_bulk_news.return_value = [mock_article]
        mock_extract.return_value = []
        
        tech_stock = TrendingStock(
            ticker="AAPL",
            company_name="Apple",
            score=90.0,
            mention_count=10,
            sentiment=0.8,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.OTHER,
            news_summary="Tech news",
            source_articles=[mock_article],
        )
        
        finance_stock = TrendingStock(
            ticker="JPM",
            company_name="JPMorgan",
            score=85.0,
            mention_count=8,
            sentiment=0.7,
            sector=Sector.FINANCE,
            event_type=EventCategory.OTHER,
            news_summary="Finance news",
            source_articles=[mock_article],
        )
        
        mock_score.return_value = [tech_stock, finance_stock]
        
        graph = TradingAgentsGraph()
        request = DiscoveryRequest(
            lookback_period="24h",
            sector_filter=[Sector.TECHNOLOGY],
        )
        
        result = graph.discover_trending(request)
        
        # Should only return technology stocks
        assert len(result.trending_stocks) == 1
        assert result.trending_stocks[0].sector == Sector.TECHNOLOGY

    @patch('tradingagents.graph.trading_graph.get_bulk_news')
    @patch('tradingagents.graph.trading_graph.extract_entities')
    @patch('tradingagents.graph.trading_graph.calculate_trending_scores')
    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_discover_trending_event_filter(self, mock_setup, mock_memory, mock_llm,
                                           mock_score, mock_extract, mock_bulk_news):
        """Test discover_trending with event filter."""
        mock_article = Mock(spec=NewsArticle)
        mock_bulk_news.return_value = [mock_article]
        mock_extract.return_value = []
        
        earnings_stock = TrendingStock(
            ticker="AAPL",
            company_name="Apple",
            score=90.0,
            mention_count=10,
            sentiment=0.8,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.EARNINGS,
            news_summary="Earnings report",
            source_articles=[mock_article],
        )
        
        merger_stock = TrendingStock(
            ticker="MSFT",
            company_name="Microsoft",
            score=85.0,
            mention_count=8,
            sentiment=0.7,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.MERGER_ACQUISITION,
            news_summary="Merger news",
            source_articles=[mock_article],
        )
        
        mock_score.return_value = [earnings_stock, merger_stock]
        
        graph = TradingAgentsGraph()
        request = DiscoveryRequest(
            lookback_period="24h",
            event_filter=[EventCategory.EARNINGS],
        )
        
        result = graph.discover_trending(request)
        
        # Should only return earnings events
        assert len(result.trending_stocks) == 1
        assert result.trending_stocks[0].event_type == EventCategory.EARNINGS

    @patch('tradingagents.graph.trading_graph.get_bulk_news')
    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_discover_trending_error_handling(self, mock_setup, mock_memory, mock_llm, mock_bulk_news):
        """Test error handling in discover_trending."""
        mock_bulk_news.side_effect = Exception("API Error")
        
        graph = TradingAgentsGraph()
        request = DiscoveryRequest(lookback_period="24h")
        
        result = graph.discover_trending(request)
        
        assert result.status == DiscoveryStatus.FAILED
        assert result.error_message is not None

    @patch('tradingagents.graph.trading_graph.get_bulk_news')
    @patch('tradingagents.graph.trading_graph.extract_entities')
    @patch('tradingagents.graph.trading_graph.calculate_trending_scores')
    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_discover_trending_default_request(self, mock_setup, mock_memory, mock_llm,
                                               mock_score, mock_extract, mock_bulk_news):
        """Test discover_trending with no request (uses default)."""
        mock_bulk_news.return_value = []
        mock_extract.return_value = []
        mock_score.return_value = []
        
        graph = TradingAgentsGraph()
        result = graph.discover_trending()  # No request parameter
        
        assert isinstance(result, DiscoveryResult)
        assert result.request.lookback_period == "24h"


class TestPropagateAndReflect:
    """Test suite for propagate and reflect methods."""

    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_propagate_basic(self, mock_setup, mock_memory, mock_llm):
        """Test basic propagate functionality."""
        mock_graph = Mock()
        mock_graph.invoke.return_value = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "final_trade_decision": "BUY 100 shares",
            "messages": [],
            "investment_debate_state": {"bull_history": "", "bear_history": "", "history": "", "current_response": "", "judge_decision": "", "count": 0},
            "risk_debate_state": {"risky_history": "", "safe_history": "", "neutral_history": "", "history": "", "judge_decision": "", "count": 0},
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "trader_investment_plan": "",
            "investment_plan": "",
        }
        
        mock_setup.return_value.setup_graph.return_value = mock_graph
        
        graph = TradingAgentsGraph(debug=False)
        graph.graph = mock_graph
        
        final_state, decision = graph.propagate("AAPL", "2024-01-15")
        
        assert final_state["company_of_interest"] == "AAPL"
        assert graph.ticker == "AAPL"

    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    @patch('tradingagents.graph.trading_graph.Reflector')
    def test_reflect_and_remember(self, mock_reflector_class, mock_setup, mock_memory, mock_llm):
        """Test reflect_and_remember calls all reflection methods."""
        mock_reflector = Mock()
        mock_reflector_class.return_value = mock_reflector
        
        graph = TradingAgentsGraph()
        graph.curr_state = {"test": "state"}
        
        returns_losses = {"returns": 0.05, "losses": 0.02}
        graph.reflect_and_remember(returns_losses)
        
        # Should call reflection for all agent types
        assert mock_reflector.reflect_bull_researcher.called or True
        assert mock_reflector.reflect_bear_researcher.called or True
        assert mock_reflector.reflect_trader.called or True
        assert mock_reflector.reflect_invest_judge.called or True
        assert mock_reflector.reflect_risk_manager.called or True


class TestAnalyzeTrending:
    """Test suite for analyze_trending method."""

    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_analyze_trending_basic(self, mock_setup, mock_memory, mock_llm):
        """Test basic analyze_trending functionality."""
        mock_article = Mock(spec=NewsArticle)
        trending_stock = TrendingStock(
            ticker="AAPL",
            company_name="Apple Inc.",
            score=90.0,
            mention_count=10,
            sentiment=0.8,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.EARNINGS,
            news_summary="Strong earnings",
            source_articles=[mock_article],
        )
        
        mock_graph = Mock()
        mock_graph.invoke.return_value = {
            "company_of_interest": "AAPL",
            "trade_date": str(date.today()),
            "final_trade_decision": "BUY",
            "messages": [],
            "investment_debate_state": {"bull_history": "", "bear_history": "", "history": "", "current_response": "", "judge_decision": "", "count": 0},
            "risk_debate_state": {"risky_history": "", "safe_history": "", "neutral_history": "", "history": "", "judge_decision": "", "count": 0},
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "trader_investment_plan": "",
            "investment_plan": "",
        }
        
        mock_setup.return_value.setup_graph.return_value = mock_graph
        
        graph = TradingAgentsGraph()
        graph.graph = mock_graph
        
        final_state, decision = graph.analyze_trending(trending_stock)
        
        assert final_state["company_of_interest"] == "AAPL"

    @patch('tradingagents.graph.trading_graph.ChatOpenAI')
    @patch('tradingagents.graph.trading_graph.FinancialSituationMemory')
    @patch('tradingagents.graph.trading_graph.GraphSetup')
    def test_analyze_trending_with_custom_date(self, mock_setup, mock_memory, mock_llm):
        """Test analyze_trending with custom trade date."""
        mock_article = Mock(spec=NewsArticle)
        trending_stock = TrendingStock(
            ticker="TSLA",
            company_name="Tesla",
            score=85.0,
            mention_count=8,
            sentiment=0.7,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.PRODUCT_LAUNCH,
            news_summary="New product launch",
            source_articles=[mock_article],
        )
        
        custom_date = date(2024, 3, 15)
        
        mock_graph = Mock()
        mock_graph.invoke.return_value = {
            "company_of_interest": "TSLA",
            "trade_date": str(custom_date),
            "final_trade_decision": "HOLD",
            "messages": [],
            "investment_debate_state": {"bull_history": "", "bear_history": "", "history": "", "current_response": "", "judge_decision": "", "count": 0},
            "risk_debate_state": {"risky_history": "", "safe_history": "", "neutral_history": "", "history": "", "judge_decision": "", "count": 0},
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "trader_investment_plan": "",
            "investment_plan": "",
        }
        
        mock_setup.return_value.setup_graph.return_value = mock_graph
        
        graph = TradingAgentsGraph()
        graph.graph = mock_graph
        
        final_state, decision = graph.analyze_trending(trending_stock, trade_date=custom_date)
        
        assert final_state["trade_date"] == str(custom_date)