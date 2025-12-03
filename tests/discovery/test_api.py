from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from tradingagents.agents.discovery import (
    DiscoveryRequest,
    DiscoveryResult,
    DiscoveryStatus,
    DiscoveryTimeoutError,
    EventCategory,
    NewsArticle,
    Sector,
    TrendingStock,
)


def create_mock_trending_stock(
    ticker: str = "AAPL",
    company_name: str = "Apple Inc.",
    score: float = 10.0,
    sector: Sector = Sector.TECHNOLOGY,
    event_type: EventCategory = EventCategory.EARNINGS,
) -> TrendingStock:
    return TrendingStock(
        ticker=ticker,
        company_name=company_name,
        score=score,
        mention_count=5,
        sentiment=0.5,
        sector=sector,
        event_type=event_type,
        news_summary="Test news summary",
        source_articles=[],
    )


def create_mock_news_article() -> NewsArticle:
    return NewsArticle(
        title="Test Article",
        source="Test Source",
        url="https://example.com/article",
        published_at=datetime.now(),
        content_snippet="Test content about Apple stock",
        ticker_mentions=["AAPL"],
    )


class TestDiscoverTrendingReturnsDiscoveryResult:
    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    @patch("tradingagents.graph.trading_graph.extract_entities")
    @patch("tradingagents.graph.trading_graph.calculate_trending_scores")
    def test_discover_trending_returns_discovery_result(
        self, mock_scores, mock_extract, mock_bulk_news
    ):
        mock_bulk_news.return_value = [create_mock_news_article()]
        mock_extract.return_value = []
        mock_scores.return_value = [create_mock_trending_stock()]

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", lambda self, **kwargs: None):
            graph = TradingAgentsGraph()
            graph.config = {
                "discovery_timeout": 60,
                "discovery_hard_timeout": 120,
                "discovery_cache_ttl": 300,
                "discovery_max_results": 20,
                "discovery_min_mentions": 2,
                "enable_quantitative_filtering": False,
            }
            graph.db_enabled = False

            result = graph.discover_trending()

            assert isinstance(result, DiscoveryResult)
            assert result.status == DiscoveryStatus.COMPLETED
            assert len(result.trending_stocks) > 0


class TestAnalyzeTrendingCallsPropagate:
    def test_analyze_trending_calls_propagate(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", lambda self, **kwargs: None):
            graph = TradingAgentsGraph()
            graph.propagate = Mock(return_value=({"final_state": "test"}, "BUY"))

            trending_stock = create_mock_trending_stock()

            result = graph.analyze_trending(trending_stock)

            graph.propagate.assert_called_once()
            call_args = graph.propagate.call_args
            assert call_args[0][0] == "AAPL"


class TestSectorFilterParameter:
    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    @patch("tradingagents.graph.trading_graph.extract_entities")
    @patch("tradingagents.graph.trading_graph.calculate_trending_scores")
    def test_sector_filter_filters_results(
        self, mock_scores, mock_extract, mock_bulk_news
    ):
        mock_bulk_news.return_value = [create_mock_news_article()]
        mock_extract.return_value = []
        mock_scores.return_value = [
            create_mock_trending_stock(ticker="AAPL", sector=Sector.TECHNOLOGY),
            create_mock_trending_stock(ticker="JPM", sector=Sector.FINANCE),
            create_mock_trending_stock(ticker="XOM", sector=Sector.ENERGY),
        ]

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", lambda self, **kwargs: None):
            graph = TradingAgentsGraph()
            graph.config = {
                "discovery_timeout": 60,
                "discovery_hard_timeout": 120,
                "discovery_cache_ttl": 300,
                "discovery_max_results": 20,
                "discovery_min_mentions": 2,
                "enable_quantitative_filtering": False,
            }
            graph.db_enabled = False

            request = DiscoveryRequest(
                lookback_period="24h",
                sector_filter=[Sector.TECHNOLOGY],
            )
            result = graph.discover_trending(request)

            assert all(
                stock.sector == Sector.TECHNOLOGY for stock in result.trending_stocks
            )


class TestEventFilterParameter:
    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    @patch("tradingagents.graph.trading_graph.extract_entities")
    @patch("tradingagents.graph.trading_graph.calculate_trending_scores")
    def test_event_filter_filters_results(
        self, mock_scores, mock_extract, mock_bulk_news
    ):
        mock_bulk_news.return_value = [create_mock_news_article()]
        mock_extract.return_value = []
        mock_scores.return_value = [
            create_mock_trending_stock(
                ticker="AAPL", event_type=EventCategory.EARNINGS
            ),
            create_mock_trending_stock(
                ticker="MSFT", event_type=EventCategory.PRODUCT_LAUNCH
            ),
            create_mock_trending_stock(
                ticker="GOOGL", event_type=EventCategory.MERGER_ACQUISITION
            ),
        ]

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", lambda self, **kwargs: None):
            graph = TradingAgentsGraph()
            graph.config = {
                "discovery_timeout": 60,
                "discovery_hard_timeout": 120,
                "discovery_cache_ttl": 300,
                "discovery_max_results": 20,
                "discovery_min_mentions": 2,
                "enable_quantitative_filtering": False,
            }
            graph.db_enabled = False

            request = DiscoveryRequest(
                lookback_period="24h",
                event_filter=[EventCategory.EARNINGS],
            )
            result = graph.discover_trending(request)

            assert all(
                stock.event_type == EventCategory.EARNINGS
                for stock in result.trending_stocks
            )


class TestTimeoutHandling:
    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    def test_timeout_raises_discovery_timeout_error(self, mock_bulk_news):
        def slow_fetch(*args, **kwargs):
            import time

            time.sleep(0.5)
            return []

        mock_bulk_news.side_effect = slow_fetch

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", lambda self, **kwargs: None):
            graph = TradingAgentsGraph()
            graph.config = {
                "discovery_timeout": 60,
                "discovery_hard_timeout": 0.1,
                "discovery_cache_ttl": 300,
                "discovery_max_results": 20,
                "discovery_min_mentions": 2,
            }

            with pytest.raises(DiscoveryTimeoutError):
                graph.discover_trending()
