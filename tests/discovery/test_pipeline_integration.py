from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


class TestDiscoverTrendingIntegration:
    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    @patch("tradingagents.graph.trading_graph.extract_entities")
    @patch("tradingagents.graph.trading_graph.calculate_trending_scores")
    @patch("tradingagents.graph.trading_graph.enhance_with_quantitative_scores")
    def test_discover_trending_calls_quantitative_enhancement(
        self, mock_enhance, mock_scores, mock_extract, mock_bulk_news
    ):
        from tradingagents.agents.discovery.models import (
            EventCategory,
            Sector,
            TrendingStock,
        )
        from tradingagents.dataflows.models import NewsArticle
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        mock_bulk_news.return_value = [
            NewsArticle(
                title="Test Article",
                source="Test",
                url="http://test.com",
                published_at=datetime.now(),
                content_snippet="Test content",
                ticker_mentions=["AAPL"],
            )
        ]
        mock_extract.return_value = []

        mock_stock = TrendingStock(
            ticker="AAPL",
            company_name="Apple Inc",
            score=85.0,
            mention_count=10,
            sentiment=0.7,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.EARNINGS,
            news_summary="Test",
            source_articles=[],
        )
        mock_scores.return_value = [mock_stock]
        mock_enhance.return_value = [mock_stock]

        config = {
            "llm_provider": "openai",
            "quick_think_llm": "gpt-4o-mini",
            "deep_think_llm": "gpt-4o",
            "backend_url": "https://api.openai.com/v1",
            "project_dir": "/tmp/test",
            "database_enabled": False,
            "enable_quantitative_filtering": True,
        }

        with (
            patch("tradingagents.graph.trading_graph.ChatOpenAI"),
            patch("tradingagents.graph.trading_graph.FinancialSituationMemory"),
            patch("tradingagents.graph.trading_graph.GraphSetup"),
        ):
            graph = TradingAgentsGraph(config=config)
            result = graph.discover_trending()

        mock_enhance.assert_called_once()

    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    @patch("tradingagents.graph.trading_graph.extract_entities")
    @patch("tradingagents.graph.trading_graph.calculate_trending_scores")
    @patch("tradingagents.graph.trading_graph.enhance_with_quantitative_scores")
    def test_discover_trending_skips_quantitative_when_disabled(
        self, mock_enhance, mock_scores, mock_extract, mock_bulk_news
    ):
        from tradingagents.agents.discovery.models import (
            EventCategory,
            Sector,
            TrendingStock,
        )
        from tradingagents.dataflows.models import NewsArticle
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        mock_bulk_news.return_value = [
            NewsArticle(
                title="Test Article",
                source="Test",
                url="http://test.com",
                published_at=datetime.now(),
                content_snippet="Test content",
                ticker_mentions=["AAPL"],
            )
        ]
        mock_extract.return_value = []

        mock_stock = TrendingStock(
            ticker="AAPL",
            company_name="Apple Inc",
            score=85.0,
            mention_count=10,
            sentiment=0.7,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.EARNINGS,
            news_summary="Test",
            source_articles=[],
        )
        mock_scores.return_value = [mock_stock]

        config = {
            "llm_provider": "openai",
            "quick_think_llm": "gpt-4o-mini",
            "deep_think_llm": "gpt-4o",
            "backend_url": "https://api.openai.com/v1",
            "project_dir": "/tmp/test",
            "database_enabled": False,
            "enable_quantitative_filtering": False,
        }

        with (
            patch("tradingagents.graph.trading_graph.ChatOpenAI"),
            patch("tradingagents.graph.trading_graph.FinancialSituationMemory"),
            patch("tradingagents.graph.trading_graph.GraphSetup"),
        ):
            graph = TradingAgentsGraph(config=config)
            result = graph.discover_trending()

        mock_enhance.assert_not_called()

    @patch("tradingagents.graph.trading_graph.get_bulk_news")
    @patch("tradingagents.graph.trading_graph.extract_entities")
    @patch("tradingagents.graph.trading_graph.calculate_trending_scores")
    @patch("tradingagents.graph.trading_graph.enhance_with_quantitative_scores")
    def test_discover_trending_uses_config_max_stocks(
        self, mock_enhance, mock_scores, mock_extract, mock_bulk_news
    ):
        from tradingagents.agents.discovery.models import (
            EventCategory,
            Sector,
            TrendingStock,
        )
        from tradingagents.dataflows.models import NewsArticle
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        mock_bulk_news.return_value = [
            NewsArticle(
                title="Test Article",
                source="Test",
                url="http://test.com",
                published_at=datetime.now(),
                content_snippet="Test content",
                ticker_mentions=["AAPL"],
            )
        ]
        mock_extract.return_value = []

        mock_stocks = [
            TrendingStock(
                ticker=f"TICK{i}",
                company_name=f"Company {i}",
                score=100.0 - i,
                mention_count=10,
                sentiment=0.5,
                sector=Sector.TECHNOLOGY,
                event_type=EventCategory.OTHER,
                news_summary="Test",
                source_articles=[],
            )
            for i in range(30)
        ]
        mock_scores.return_value = mock_stocks
        mock_enhance.return_value = mock_stocks

        config = {
            "llm_provider": "openai",
            "quick_think_llm": "gpt-4o-mini",
            "deep_think_llm": "gpt-4o",
            "backend_url": "https://api.openai.com/v1",
            "project_dir": "/tmp/test",
            "database_enabled": False,
            "enable_quantitative_filtering": True,
            "quantitative_max_stocks": 25,
        }

        with (
            patch("tradingagents.graph.trading_graph.ChatOpenAI"),
            patch("tradingagents.graph.trading_graph.FinancialSituationMemory"),
            patch("tradingagents.graph.trading_graph.GraphSetup"),
        ):
            graph = TradingAgentsGraph(config=config)
            result = graph.discover_trending()

        call_args = mock_enhance.call_args
        assert call_args[1].get("max_stocks", 50) == 25


class TestScorerConvictionSupport:
    def test_calculate_trending_scores_preserves_original_score(self):
        from tradingagents.agents.discovery.entity_extractor import EntityMention
        from tradingagents.agents.discovery.models import (
            EventCategory,
            NewsArticle,
        )
        from tradingagents.agents.discovery.scorer import calculate_trending_scores

        mentions = [
            EntityMention(
                company_name="Apple",
                confidence=0.9,
                sentiment=0.7,
                event_type=EventCategory.EARNINGS,
                context_snippet="Apple reports strong earnings",
                article_id="article_0",
            ),
            EntityMention(
                company_name="Apple",
                confidence=0.85,
                sentiment=0.6,
                event_type=EventCategory.EARNINGS,
                context_snippet="Apple stock rises",
                article_id="article_1",
            ),
        ]

        articles = [
            NewsArticle(
                title="Article 1",
                source="Test",
                url="http://test.com/1",
                published_at=datetime.now(),
                content_snippet="Test content 1",
                ticker_mentions=["AAPL"],
            ),
            NewsArticle(
                title="Article 2",
                source="Test",
                url="http://test.com/2",
                published_at=datetime.now(),
                content_snippet="Test content 2",
                ticker_mentions=["AAPL"],
            ),
        ]

        with patch(
            "tradingagents.agents.discovery.scorer.resolve_ticker"
        ) as mock_resolve:
            mock_resolve.return_value = "AAPL"
            result = calculate_trending_scores(mentions, articles)

        assert len(result) == 1
        assert result[0].ticker == "AAPL"
        assert result[0].score > 0
        assert result[0].conviction_score is None

    def test_trending_stock_supports_conviction_score(self):
        from tradingagents.agents.discovery.models import (
            EventCategory,
            Sector,
            TrendingStock,
        )
        from tradingagents.agents.discovery.quantitative_models import (
            QuantitativeMetrics,
        )

        stock = TrendingStock(
            ticker="AAPL",
            company_name="Apple Inc",
            score=85.0,
            mention_count=10,
            sentiment=0.7,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.EARNINGS,
            news_summary="Test",
            source_articles=[],
        )

        assert stock.conviction_score is None

        stock.conviction_score = 0.85
        assert stock.conviction_score == 0.85

        metrics = QuantitativeMetrics(
            momentum_score=0.7,
            volume_score=0.6,
            relative_strength_score=0.65,
            risk_reward_score=0.7,
            quantitative_score=0.66,
        )
        stock.quantitative_metrics = metrics
        assert stock.quantitative_metrics.quantitative_score == 0.66


class TestBackwardCompatibility:
    def test_trending_stock_without_quantitative_fields(self):
        from tradingagents.agents.discovery.models import (
            EventCategory,
            Sector,
            TrendingStock,
        )

        stock = TrendingStock(
            ticker="AAPL",
            company_name="Apple Inc",
            score=85.0,
            mention_count=10,
            sentiment=0.7,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.EARNINGS,
            news_summary="Test",
            source_articles=[],
        )

        assert stock.quantitative_metrics is None
        assert stock.conviction_score is None

        stock_dict = stock.to_dict()
        assert (
            "quantitative_metrics" not in stock_dict
            or stock_dict.get("quantitative_metrics") is None
        )
        assert (
            "conviction_score" not in stock_dict
            or stock_dict.get("conviction_score") is None
        )

    def test_trending_stock_from_dict_without_quantitative_fields(self):
        from tradingagents.agents.discovery.models import TrendingStock

        data = {
            "ticker": "AAPL",
            "company_name": "Apple Inc",
            "score": 85.0,
            "mention_count": 10,
            "sentiment": 0.7,
            "sector": "technology",
            "event_type": "earnings",
            "news_summary": "Test",
            "source_articles": [],
        }

        stock = TrendingStock.from_dict(data)

        assert stock.ticker == "AAPL"
        assert stock.quantitative_metrics is None
        assert stock.conviction_score is None
