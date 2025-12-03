from datetime import datetime

from tradingagents.agents.discovery import (
    DiscoveryRequest,
    DiscoveryResult,
    EventCategory,
    NewsArticle,
    Sector,
    TrendingStock,
)
from tradingagents.agents.discovery.models import DiscoveryStatus


class TestTrendingStock:
    def test_trending_stock_creation_and_validation(self):
        article = NewsArticle(
            title="Apple announces new iPhone",
            source="Reuters",
            url="https://reuters.com/article1",
            published_at=datetime(2024, 1, 15, 10, 30, 0),
            content_snippet="Apple Inc announced its latest iPhone model today...",
            ticker_mentions=["AAPL"],
        )

        stock = TrendingStock(
            ticker="AAPL",
            company_name="Apple Inc.",
            score=85.5,
            mention_count=10,
            sentiment=0.75,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.PRODUCT_LAUNCH,
            news_summary="Apple announced new iPhone with advanced AI features.",
            source_articles=[article],
        )

        assert stock.ticker == "AAPL"
        assert stock.company_name == "Apple Inc."
        assert stock.score == 85.5
        assert stock.mention_count == 10
        assert stock.sentiment == 0.75
        assert stock.sector == Sector.TECHNOLOGY
        assert stock.event_type == EventCategory.PRODUCT_LAUNCH
        assert len(stock.source_articles) == 1


class TestNewsArticle:
    def test_news_article_with_required_fields(self):
        published = datetime(2024, 1, 15, 14, 0, 0)

        article = NewsArticle(
            title="Tesla Q4 Earnings Beat Expectations",
            source="Bloomberg",
            url="https://bloomberg.com/news/tsla-earnings",
            published_at=published,
            content_snippet="Tesla Inc. reported fourth quarter earnings that exceeded analyst expectations...",
            ticker_mentions=["TSLA", "F"],
        )

        assert article.title == "Tesla Q4 Earnings Beat Expectations"
        assert article.source == "Bloomberg"
        assert article.url == "https://bloomberg.com/news/tsla-earnings"
        assert article.published_at == published
        assert article.content_snippet.startswith("Tesla Inc.")
        assert "TSLA" in article.ticker_mentions
        assert "F" in article.ticker_mentions


class TestDiscoveryRequest:
    def test_discovery_request_with_lookback_period_validation(self):
        created = datetime(2024, 1, 15, 12, 0, 0)

        request = DiscoveryRequest(
            lookback_period="24h",
            sector_filter=[Sector.TECHNOLOGY, Sector.HEALTHCARE],
            event_filter=[EventCategory.EARNINGS],
            max_results=20,
            created_at=created,
        )

        assert request.lookback_period == "24h"
        assert Sector.TECHNOLOGY in request.sector_filter
        assert Sector.HEALTHCARE in request.sector_filter
        assert EventCategory.EARNINGS in request.event_filter
        assert request.max_results == 20
        assert request.created_at == created

    def test_discovery_request_with_defaults(self):
        request = DiscoveryRequest(
            lookback_period="1h",
        )

        assert request.lookback_period == "1h"
        assert request.sector_filter is None
        assert request.event_filter is None
        assert request.max_results == 20
        assert request.created_at is not None


class TestDiscoveryResult:
    def test_discovery_result_state_transitions(self):
        request = DiscoveryRequest(lookback_period="6h")
        started = datetime(2024, 1, 15, 12, 0, 0)

        result = DiscoveryResult(
            request=request,
            trending_stocks=[],
            status=DiscoveryStatus.CREATED,
            started_at=started,
        )

        assert result.status == DiscoveryStatus.CREATED

        result.status = DiscoveryStatus.PROCESSING
        assert result.status == DiscoveryStatus.PROCESSING

        result.status = DiscoveryStatus.COMPLETED
        result.completed_at = datetime(2024, 1, 15, 12, 1, 0)
        assert result.status == DiscoveryStatus.COMPLETED
        assert result.completed_at is not None

    def test_discovery_result_failed_state(self):
        request = DiscoveryRequest(lookback_period="7d")

        result = DiscoveryResult(
            request=request,
            trending_stocks=[],
            status=DiscoveryStatus.FAILED,
            started_at=datetime(2024, 1, 15, 12, 0, 0),
            error_message="News API rate limit exceeded",
        )

        assert result.status == DiscoveryStatus.FAILED
        assert result.error_message == "News API rate limit exceeded"


class TestSerializationRoundtrip:
    def test_to_dict_and_from_dict_serialization_roundtrip(self):
        article = NewsArticle(
            title="Microsoft acquires AI startup",
            source="WSJ",
            url="https://wsj.com/msft-acquisition",
            published_at=datetime(2024, 1, 15, 9, 0, 0),
            content_snippet="Microsoft Corp announced the acquisition of an AI startup...",
            ticker_mentions=["MSFT"],
        )

        stock = TrendingStock(
            ticker="MSFT",
            company_name="Microsoft Corporation",
            score=92.3,
            mention_count=15,
            sentiment=0.65,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.MERGER_ACQUISITION,
            news_summary="Microsoft announces major AI acquisition.",
            source_articles=[article],
        )

        request = DiscoveryRequest(
            lookback_period="24h",
            sector_filter=[Sector.TECHNOLOGY],
            event_filter=[EventCategory.MERGER_ACQUISITION],
            max_results=10,
            created_at=datetime(2024, 1, 15, 8, 0, 0),
        )

        result = DiscoveryResult(
            request=request,
            trending_stocks=[stock],
            status=DiscoveryStatus.COMPLETED,
            started_at=datetime(2024, 1, 15, 8, 0, 0),
            completed_at=datetime(2024, 1, 15, 8, 1, 30),
        )

        result_dict = result.to_dict()
        restored_result = DiscoveryResult.from_dict(result_dict)

        assert restored_result.status == result.status
        assert restored_result.request.lookback_period == request.lookback_period
        assert len(restored_result.trending_stocks) == 1

        restored_stock = restored_result.trending_stocks[0]
        assert restored_stock.ticker == stock.ticker
        assert restored_stock.company_name == stock.company_name
        assert restored_stock.score == stock.score
        assert restored_stock.mention_count == stock.mention_count
        assert restored_stock.sentiment == stock.sentiment
        assert restored_stock.sector == stock.sector
        assert restored_stock.event_type == stock.event_type

        assert len(restored_stock.source_articles) == 1
        restored_article = restored_stock.source_articles[0]
        assert restored_article.title == article.title
        assert restored_article.source == article.source
        assert restored_article.url == article.url
