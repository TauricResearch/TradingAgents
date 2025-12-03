import pytest
import math
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from tradingagents.agents.discovery import (
    TrendingStock,
    NewsArticle,
    DiscoveryRequest,
    DiscoveryResult,
    DiscoveryStatus,
    Sector,
    EventCategory,
    DiscoveryTimeoutError,
    NewsUnavailableError,
)
from tradingagents.agents.discovery.entity_extractor import EntityMention


class TestEndToEndDiscoveryFlow:
    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    @patch("tradingagents.graph.trading_graph.extract_entities")
    @patch("tradingagents.graph.trading_graph.calculate_trending_scores")
    def test_full_discovery_flow_from_news_to_results(
        self, mock_scores, mock_extract, mock_bulk_news
    ):
        now = datetime.now()
        mock_articles = [
            NewsArticle(
                title="Apple announces record earnings",
                source="Reuters",
                url="https://reuters.com/apple-earnings",
                published_at=now - timedelta(hours=2),
                content_snippet="Apple Inc reported record quarterly earnings...",
                ticker_mentions=["AAPL"],
            ),
            NewsArticle(
                title="Apple stock surges on AI news",
                source="Bloomberg",
                url="https://bloomberg.com/apple-ai",
                published_at=now - timedelta(hours=1),
                content_snippet="Shares of Apple jumped after AI announcement...",
                ticker_mentions=["AAPL"],
            ),
        ]
        mock_bulk_news.return_value = mock_articles

        mock_mentions = [
            EntityMention(
                company_name="Apple Inc",
                confidence=0.95,
                context_snippet="Apple Inc reported record quarterly earnings",
                article_id="article_0",
                event_type=EventCategory.EARNINGS,
                sentiment=0.8,
            ),
            EntityMention(
                company_name="Apple",
                confidence=0.92,
                context_snippet="Shares of Apple jumped",
                article_id="article_1",
                event_type=EventCategory.PRODUCT_LAUNCH,
                sentiment=0.7,
            ),
        ]
        mock_extract.return_value = mock_mentions

        mock_trending = [
            TrendingStock(
                ticker="AAPL",
                company_name="Apple Inc.",
                score=8.5,
                mention_count=2,
                sentiment=0.75,
                sector=Sector.TECHNOLOGY,
                event_type=EventCategory.EARNINGS,
                news_summary="Apple reported record earnings and AI progress.",
                source_articles=mock_articles,
            ),
        ]
        mock_scores.return_value = mock_trending

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", lambda self, **kwargs: None):
            graph = TradingAgentsGraph()
            graph.config = {
                "discovery_timeout": 60,
                "discovery_hard_timeout": 120,
                "discovery_cache_ttl": 300,
                "discovery_max_results": 20,
                "discovery_min_mentions": 2,
            }

            request = DiscoveryRequest(lookback_period="24h")
            result = graph.discover_trending(request)

            assert isinstance(result, DiscoveryResult)
            assert result.status == DiscoveryStatus.COMPLETED
            assert len(result.trending_stocks) == 1
            assert result.trending_stocks[0].ticker == "AAPL"
            assert result.trending_stocks[0].mention_count >= 2

            mock_bulk_news.assert_called_once_with("24h")
            mock_extract.assert_called_once()
            mock_scores.assert_called_once()


class TestEntityExtractionToScoringPipeline:
    def test_pipeline_from_extraction_to_scoring(self):
        from tradingagents.agents.discovery.scorer import calculate_trending_scores

        now = datetime.now()
        articles = [
            NewsArticle(
                title="Microsoft cloud revenue grows",
                source="WSJ",
                url="https://wsj.com/article1",
                published_at=now - timedelta(hours=2),
                content_snippet="Microsoft Corporation reported strong cloud growth.",
                ticker_mentions=["MSFT"],
            ),
            NewsArticle(
                title="Microsoft earnings beat estimates",
                source="CNBC",
                url="https://cnbc.com/article2",
                published_at=now - timedelta(hours=3),
                content_snippet="Microsoft earnings exceeded analyst expectations.",
                ticker_mentions=["MSFT"],
            ),
            NewsArticle(
                title="Tech stocks rally",
                source="Bloomberg",
                url="https://bloomberg.com/article3",
                published_at=now - timedelta(hours=1),
                content_snippet="Technology companies led market gains.",
                ticker_mentions=[],
            ),
        ]

        mentions = [
            EntityMention(
                company_name="Microsoft Corporation",
                confidence=0.95,
                context_snippet="Microsoft Corporation reported strong cloud growth",
                article_id="article_0",
                event_type=EventCategory.EARNINGS,
                sentiment=0.7,
            ),
            EntityMention(
                company_name="Microsoft",
                confidence=0.92,
                context_snippet="Microsoft earnings exceeded analyst expectations",
                article_id="article_1",
                event_type=EventCategory.EARNINGS,
                sentiment=0.8,
            ),
        ]

        with patch("tradingagents.agents.discovery.scorer.resolve_ticker") as mock_resolve:
            mock_resolve.return_value = "MSFT"

            with patch("tradingagents.agents.discovery.scorer.classify_sector") as mock_sector:
                mock_sector.return_value = "technology"

                result = calculate_trending_scores(mentions, articles, min_mentions=2)

                assert len(result) == 1
                assert result[0].ticker == "MSFT"
                assert result[0].mention_count == 2
                assert result[0].sentiment > 0


class TestNewsVendorFailureGracefulDegradation:
    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    def test_news_vendor_failure_with_graceful_degradation(self, mock_bulk_news):
        mock_bulk_news.side_effect = NewsUnavailableError("All news vendors failed")

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", lambda self, **kwargs: None):
            graph = TradingAgentsGraph()
            graph.config = {
                "discovery_timeout": 60,
                "discovery_hard_timeout": 120,
                "discovery_cache_ttl": 300,
                "discovery_max_results": 20,
                "discovery_min_mentions": 2,
            }

            result = graph.discover_trending()

            assert result.status == DiscoveryStatus.FAILED
            assert result.error_message is not None
            assert "news" in result.error_message.lower() or "vendor" in result.error_message.lower()


class TestTimeoutHandlingWithPartialResults:
    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    def test_timeout_handling_returns_error(self, mock_bulk_news):
        def slow_fetch(*args, **kwargs):
            import time
            time.sleep(0.3)
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


class TestNoTrendingStocksFound:
    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    @patch("tradingagents.graph.trading_graph.extract_entities")
    @patch("tradingagents.graph.trading_graph.calculate_trending_scores")
    def test_no_trending_stocks_found_returns_empty_list(
        self, mock_scores, mock_extract, mock_bulk_news
    ):
        mock_bulk_news.return_value = [
            NewsArticle(
                title="General market update",
                source="Reuters",
                url="https://reuters.com/general",
                published_at=datetime.now(),
                content_snippet="Markets were quiet today with no major news.",
                ticker_mentions=[],
            ),
        ]
        mock_extract.return_value = []
        mock_scores.return_value = []

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", lambda self, **kwargs: None):
            graph = TradingAgentsGraph()
            graph.config = {
                "discovery_timeout": 60,
                "discovery_hard_timeout": 120,
                "discovery_cache_ttl": 300,
                "discovery_max_results": 20,
                "discovery_min_mentions": 2,
            }

            result = graph.discover_trending()

            assert result.status == DiscoveryStatus.COMPLETED
            assert len(result.trending_stocks) == 0


class TestAllStocksFilteredOutBySectorFilter:
    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    @patch("tradingagents.graph.trading_graph.extract_entities")
    @patch("tradingagents.graph.trading_graph.calculate_trending_scores")
    def test_all_stocks_filtered_out_by_sector_filter(
        self, mock_scores, mock_extract, mock_bulk_news
    ):
        mock_bulk_news.return_value = []
        mock_extract.return_value = []
        mock_scores.return_value = [
            TrendingStock(
                ticker="AAPL",
                company_name="Apple Inc.",
                score=10.0,
                mention_count=5,
                sentiment=0.5,
                sector=Sector.TECHNOLOGY,
                event_type=EventCategory.EARNINGS,
                news_summary="Apple earnings",
                source_articles=[],
            ),
            TrendingStock(
                ticker="MSFT",
                company_name="Microsoft",
                score=9.0,
                mention_count=4,
                sentiment=0.4,
                sector=Sector.TECHNOLOGY,
                event_type=EventCategory.PRODUCT_LAUNCH,
                news_summary="Microsoft product",
                source_articles=[],
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
            }

            request = DiscoveryRequest(
                lookback_period="24h",
                sector_filter=[Sector.HEALTHCARE],
            )
            result = graph.discover_trending(request)

            assert result.status == DiscoveryStatus.COMPLETED
            assert len(result.trending_stocks) == 0


class TestAllStocksFilteredOutByEventFilter:
    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    @patch("tradingagents.graph.trading_graph.extract_entities")
    @patch("tradingagents.graph.trading_graph.calculate_trending_scores")
    def test_all_stocks_filtered_out_by_event_filter(
        self, mock_scores, mock_extract, mock_bulk_news
    ):
        mock_bulk_news.return_value = []
        mock_extract.return_value = []
        mock_scores.return_value = [
            TrendingStock(
                ticker="AAPL",
                company_name="Apple Inc.",
                score=10.0,
                mention_count=5,
                sentiment=0.5,
                sector=Sector.TECHNOLOGY,
                event_type=EventCategory.EARNINGS,
                news_summary="Apple earnings",
                source_articles=[],
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
            }

            request = DiscoveryRequest(
                lookback_period="24h",
                event_filter=[EventCategory.MERGER_ACQUISITION],
            )
            result = graph.discover_trending(request)

            assert result.status == DiscoveryStatus.COMPLETED
            assert len(result.trending_stocks) == 0


class TestMultipleSectorsAndEventsFiltering:
    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    @patch("tradingagents.graph.trading_graph.extract_entities")
    @patch("tradingagents.graph.trading_graph.calculate_trending_scores")
    def test_combined_sector_and_event_filtering(
        self, mock_scores, mock_extract, mock_bulk_news
    ):
        mock_bulk_news.return_value = []
        mock_extract.return_value = []
        mock_scores.return_value = [
            TrendingStock(
                ticker="AAPL",
                company_name="Apple Inc.",
                score=10.0,
                mention_count=5,
                sentiment=0.5,
                sector=Sector.TECHNOLOGY,
                event_type=EventCategory.EARNINGS,
                news_summary="Apple earnings",
                source_articles=[],
            ),
            TrendingStock(
                ticker="JPM",
                company_name="JPMorgan Chase",
                score=9.0,
                mention_count=4,
                sentiment=0.4,
                sector=Sector.FINANCE,
                event_type=EventCategory.EARNINGS,
                news_summary="JPM earnings",
                source_articles=[],
            ),
            TrendingStock(
                ticker="XOM",
                company_name="Exxon Mobil",
                score=8.0,
                mention_count=3,
                sentiment=0.3,
                sector=Sector.ENERGY,
                event_type=EventCategory.REGULATORY,
                news_summary="XOM regulatory news",
                source_articles=[],
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
            }

            request = DiscoveryRequest(
                lookback_period="24h",
                sector_filter=[Sector.TECHNOLOGY, Sector.FINANCE],
                event_filter=[EventCategory.EARNINGS],
            )
            result = graph.discover_trending(request)

            assert result.status == DiscoveryStatus.COMPLETED
            assert len(result.trending_stocks) == 2
            tickers = [s.ticker for s in result.trending_stocks]
            assert "AAPL" in tickers
            assert "JPM" in tickers
            assert "XOM" not in tickers


class TestDiscoveryResultPersistenceIntegration:
    def test_discovery_result_can_be_serialized_and_saved(self):
        from tradingagents.agents.discovery.persistence import (
            save_discovery_result,
            generate_markdown_summary,
        )
        import tempfile
        import shutil
        from pathlib import Path

        article = NewsArticle(
            title="Test article",
            source="Test",
            url="https://test.com",
            published_at=datetime.now(),
            content_snippet="Test content",
            ticker_mentions=["TEST"],
        )

        stock = TrendingStock(
            ticker="TEST",
            company_name="Test Company",
            score=5.0,
            mention_count=2,
            sentiment=0.5,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.OTHER,
            news_summary="Test news summary",
            source_articles=[article],
        )

        request = DiscoveryRequest(
            lookback_period="24h",
            created_at=datetime.now(),
        )

        result = DiscoveryResult(
            request=request,
            trending_stocks=[stock],
            status=DiscoveryStatus.COMPLETED,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )

        temp_dir = tempfile.mkdtemp()
        try:
            path = save_discovery_result(result, base_path=Path(temp_dir))
            assert path.exists()
            assert (path / "discovery_result.json").exists()
            assert (path / "discovery_summary.md").exists()

            markdown = generate_markdown_summary(result)
            assert "TEST" in markdown
            assert "Test Company" in markdown
        finally:
            shutil.rmtree(temp_dir)
