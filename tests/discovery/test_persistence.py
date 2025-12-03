import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from tradingagents.agents.discovery import (
    DiscoveryRequest,
    DiscoveryResult,
    DiscoveryStatus,
    EventCategory,
    NewsArticle,
    Sector,
    TrendingStock,
)
from tradingagents.agents.discovery.persistence import (
    generate_markdown_summary,
    save_discovery_result,
)


@pytest.fixture
def sample_discovery_result():
    articles = [
        NewsArticle(
            title="Apple announces new iPhone with AI features",
            source="Reuters",
            url="https://reuters.com/apple-iphone-ai",
            published_at=datetime(2024, 1, 15, 10, 30, 0),
            content_snippet="Apple Inc announced its latest iPhone model with advanced AI...",
            ticker_mentions=["AAPL"],
        ),
        NewsArticle(
            title="Apple stock surges on earnings beat",
            source="Bloomberg",
            url="https://bloomberg.com/apple-earnings",
            published_at=datetime(2024, 1, 15, 11, 0, 0),
            content_snippet="Shares of Apple Inc surged after the company reported...",
            ticker_mentions=["AAPL"],
        ),
        NewsArticle(
            title="Microsoft cloud revenue grows 25%",
            source="WSJ",
            url="https://wsj.com/msft-cloud",
            published_at=datetime(2024, 1, 15, 9, 0, 0),
            content_snippet="Microsoft Corp reported strong cloud revenue growth...",
            ticker_mentions=["MSFT"],
        ),
    ]

    stocks = [
        TrendingStock(
            ticker="AAPL",
            company_name="Apple Inc.",
            score=8.54,
            mention_count=12,
            sentiment=0.72,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.EARNINGS,
            news_summary="Apple reported strong earnings and announced new AI features.",
            source_articles=[articles[0], articles[1]],
        ),
        TrendingStock(
            ticker="MSFT",
            company_name="Microsoft Corporation",
            score=7.23,
            mention_count=9,
            sentiment=0.65,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.PRODUCT_LAUNCH,
            news_summary="Microsoft cloud business continues strong growth.",
            source_articles=[articles[2]],
        ),
        TrendingStock(
            ticker="GOOGL",
            company_name="Alphabet Inc.",
            score=6.15,
            mention_count=7,
            sentiment=0.58,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.REGULATORY,
            news_summary="Google faces regulatory scrutiny in multiple markets.",
            source_articles=[],
        ),
    ]

    request = DiscoveryRequest(
        lookback_period="24h",
        sector_filter=[Sector.TECHNOLOGY],
        event_filter=[EventCategory.EARNINGS],
        max_results=20,
        created_at=datetime(2024, 1, 15, 14, 30, 45),
    )

    return DiscoveryResult(
        request=request,
        trending_stocks=stocks,
        status=DiscoveryStatus.COMPLETED,
        started_at=datetime(2024, 1, 15, 14, 30, 45),
        completed_at=datetime(2024, 1, 15, 14, 31, 30),
    )


@pytest.fixture
def temp_results_dir():
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


class TestDirectoryStructureCreation:
    def test_creates_correct_directory_structure(
        self, sample_discovery_result, temp_results_dir
    ):
        result_path = save_discovery_result(
            sample_discovery_result, base_path=temp_results_dir
        )

        assert result_path.exists()
        assert result_path.is_dir()

        path_parts = result_path.parts
        assert "discovery" in path_parts

        date_part = path_parts[-2]
        time_part = path_parts[-1]

        assert len(date_part.split("-")) == 3
        assert len(time_part.split("-")) == 3


class TestDiscoveryResultJson:
    def test_discovery_result_json_contains_all_fields(
        self, sample_discovery_result, temp_results_dir
    ):
        result_path = save_discovery_result(
            sample_discovery_result, base_path=temp_results_dir
        )

        json_path = result_path / "discovery_result.json"
        assert json_path.exists()

        with open(json_path) as f:
            saved_data = json.load(f)

        assert "request" in saved_data
        assert "trending_stocks" in saved_data
        assert "status" in saved_data
        assert "started_at" in saved_data
        assert "completed_at" in saved_data

        assert saved_data["request"]["lookback_period"] == "24h"
        assert saved_data["status"] == "completed"
        assert len(saved_data["trending_stocks"]) == 3

        first_stock = saved_data["trending_stocks"][0]
        assert first_stock["ticker"] == "AAPL"
        assert first_stock["company_name"] == "Apple Inc."
        assert first_stock["score"] == 8.54
        assert first_stock["mention_count"] == 12
        assert first_stock["sentiment"] == 0.72
        assert first_stock["sector"] == "technology"
        assert first_stock["event_type"] == "earnings"
        assert "news_summary" in first_stock
        assert "source_articles" in first_stock


class TestDiscoverySummaryMarkdown:
    def test_discovery_summary_md_is_human_readable(
        self, sample_discovery_result, temp_results_dir
    ):
        result_path = save_discovery_result(
            sample_discovery_result, base_path=temp_results_dir
        )

        md_path = result_path / "discovery_summary.md"
        assert md_path.exists()

        with open(md_path) as f:
            markdown_content = f.read()

        assert "# Discovery Results" in markdown_content
        assert "Timestamp:" in markdown_content
        assert "Lookback Period:" in markdown_content
        assert "24h" in markdown_content
        assert "Total Stocks Found:" in markdown_content

        assert "## Trending Stocks" in markdown_content
        assert "| Rank |" in markdown_content
        assert "| Ticker |" in markdown_content
        assert "| Company |" in markdown_content
        assert "| Score |" in markdown_content
        assert "| Mentions |" in markdown_content
        assert "| Event |" in markdown_content

        assert "AAPL" in markdown_content
        assert "Apple Inc." in markdown_content
        assert "8.54" in markdown_content
        assert "12" in markdown_content
        assert "earnings" in markdown_content

        assert "MSFT" in markdown_content
        assert "Microsoft Corporation" in markdown_content

        assert "## Top 3 Detailed Analysis" in markdown_content
        assert "### 1. AAPL - Apple Inc." in markdown_content
        assert "**Score:**" in markdown_content
        assert "**Sentiment:**" in markdown_content
        assert "**Sector:**" in markdown_content
        assert "**Event Type:**" in markdown_content
        assert "**Mentions:**" in markdown_content
        assert "**News Summary:**" in markdown_content


class TestMarkdownGeneration:
    def test_generate_markdown_with_filters(self, sample_discovery_result):
        markdown = generate_markdown_summary(sample_discovery_result)

        assert "sector=technology" in markdown.lower()
        assert "event=earnings" in markdown.lower()

    def test_generate_markdown_without_filters(self):
        request = DiscoveryRequest(
            lookback_period="6h",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
        )

        result = DiscoveryResult(
            request=request,
            trending_stocks=[],
            status=DiscoveryStatus.COMPLETED,
            started_at=datetime(2024, 1, 15, 10, 0, 0),
            completed_at=datetime(2024, 1, 15, 10, 1, 0),
        )

        markdown = generate_markdown_summary(result)

        assert "Filters:" in markdown
        assert "None" in markdown
