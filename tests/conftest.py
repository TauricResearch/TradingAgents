"""
Test configuration and shared fixtures following pragmatic TDD principles.

Provides shared fixtures for mocking I/O boundaries while using real objects
for business logic and data transformations.
"""

import shutil
import tempfile
from datetime import date, datetime
from unittest.mock import Mock

import pytest

from tradingagents.domains.news.article_scraper_client import (
    ArticleScraperClient,
    ScrapeResult,
)
from tradingagents.domains.news.google_news_client import (
    GoogleNewsArticle,
    GoogleNewsClient,
)
from tradingagents.domains.news.news_repository import (
    NewsArticle,
    NewsRepository,
)
from tradingagents.domains.news.openrouter_client import OpenRouterClient


@pytest.fixture
def mock_google_client():
    """Mock GoogleNewsClient for testing I/O boundary."""
    return Mock(spec=GoogleNewsClient)


@pytest.fixture
def mock_article_scraper():
    """Mock ArticleScraperClient for testing I/O boundary."""
    return Mock(spec=ArticleScraperClient)


@pytest.fixture
def mock_repository():
    """Mock NewsRepository for testing I/O boundary."""
    return Mock(spec=NewsRepository)


@pytest.fixture
def mock_openrouter_client():
    """Mock OpenRouterClient for testing I/O boundary."""
    return Mock(spec=OpenRouterClient)


@pytest.fixture
def temp_data_dir():
    """Temporary directory for testing real repository persistence."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    try:
        # pyrefly: ignore[deprecated]
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def real_repository(temp_data_dir):
    """Real NewsRepository instance for testing persistence logic."""
    return NewsRepository(temp_data_dir)


@pytest.fixture
def sample_news_articles():
    """Sample NewsArticle objects for testing data transformations."""
    return [
        NewsArticle(
            headline="Apple Stock Rises 5% on Strong Earnings",
            url="https://example.com/apple-earnings",
            source="CNBC",
            published_date=date(2024, 1, 15),
            summary="Apple reports strong quarterly earnings beating expectations",
            sentiment_score=0.7,
            author="John Reporter",
        ),
        NewsArticle(
            headline="Apple Faces Supply Chain Challenges",
            url="https://example.com/apple-supply-chain",
            source="Reuters",
            published_date=date(2024, 1, 16),
            summary="Apple struggles with component shortages affecting production",
            sentiment_score=-0.3,
            author="Jane Analyst",
        ),
    ]


@pytest.fixture
def sample_google_articles():
    """Sample GoogleNewsArticle objects for testing data transformations."""
    return [
        GoogleNewsArticle(
            title="Apple Stock Soars on Positive Outlook",
            link="https://example.com/apple-soars",
            published=datetime(2024, 1, 15, 10, 30),
            summary="Investors are optimistic about Apple's future",
            source="MarketWatch",
            guid="article1",
        ),
        GoogleNewsArticle(
            title="Apple Announces New Product Line",
            link="https://example.com/apple-products",
            published=datetime(2024, 1, 16, 14, 20),
            summary="Apple unveils exciting new product lineup",
            source="TechCrunch",
            guid="article2",
        ),
    ]


@pytest.fixture
def sample_scrape_results():
    """Sample ScrapeResult objects for testing data transformations."""
    return {
        "https://example.com/apple-soars": ScrapeResult(
            status="SUCCESS",
            content="Full article content about Apple's stock performance...",
            author="Market Reporter",
            title="Apple Stock Soars on Positive Outlook",
            publish_date="2024-01-15",
        ),
        "https://example.com/apple-products": ScrapeResult(
            status="SUCCESS",
            content="Detailed content about Apple's new product announcements...",
            author="Tech Writer",
            title="Apple Announces New Product Line",
            publish_date="2024-01-16",
        ),
    }
