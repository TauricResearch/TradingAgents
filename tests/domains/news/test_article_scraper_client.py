"""
Tests for ArticleScraperClient using pytest-vcr for HTTP interactions.
"""

from unittest.mock import patch

import pytest

from tradingagents.domains.news.article_scraper_client import (
    ArticleScraperClient,
    ScrapeResult,
)

# VCR configuration
vcr = pytest.mark.vcr(
    cassette_library_dir="tests/fixtures/vcr_cassettes/news",
    record_mode="once",  # Record once, then replay
    match_on=["uri", "method"],
    filter_headers=["authorization", "cookie", "user-agent"],
)


@pytest.fixture
def scraper():
    """ArticleScraperClient instance for testing."""
    # Mock NLTK downloads to avoid external HTTP requests during tests
    with patch("nltk.download"):
        return ArticleScraperClient(user_agent="Test-Agent/1.0", delay=0.1)


class TestArticleScraperClient:
    """Test ArticleScraperClient functionality."""

    def test_initialization(self):
        """Test scraper initializes with correct configuration."""
        scraper = ArticleScraperClient("Custom-Agent/1.0", delay=2.0)
        assert scraper.user_agent == "Custom-Agent/1.0"
        assert scraper.delay == 2.0

        scraper_default = ArticleScraperClient(None)
        assert "Chrome" in scraper_default.user_agent
        assert scraper_default.delay == 1.0

    def test_is_valid_url(self, scraper):
        """Test URL validation logic."""
        # Valid URLs
        assert scraper._is_valid_url("https://example.com/article") is True
        assert scraper._is_valid_url("http://example.com/article") is True

        # Invalid URLs
        assert scraper._is_valid_url("") is False
        assert scraper._is_valid_url("not-a-url") is False
        assert scraper._is_valid_url("ftp://example.com") is False

    def test_scrape_article_invalid_url(self, scraper):
        """Test scraping with invalid URLs returns NOT_FOUND."""
        invalid_urls = ["", "not-a-url", "ftp://example.com"]

        for url in invalid_urls:
            result = scraper.scrape_article(url)
            assert result.status == "NOT_FOUND"
            assert result.final_url == url

    def test_scrape_result_dataclass(self):
        """Test ScrapeResult dataclass."""
        result = ScrapeResult(status="SUCCESS", content="Test content")

        assert result.status == "SUCCESS"
        assert result.content == "Test content"
        assert result.author == ""  # Default
        assert result.final_url == ""  # Default
        assert result.is_paywall is False  # Default
        assert result.keywords is None  # Default
        assert result.summary == ""  # Default

    def test_paywall_detection_logic(self, scraper):
        """Test paywall detection logic without mocking."""
        # Test clear paywall indicators
        assert (
            scraper._detect_paywall(
                "Please subscribe to continue reading", "News Title"
            )
            is True
        )
        assert (
            scraper._detect_paywall("This article is for subscribers only", "Title")
            is True
        )
        assert scraper._detect_paywall("", "Subscribe now for premium content") is True

        # Test no paywall
        assert (
            scraper._detect_paywall(
                "Regular article content without any restrictions", "Normal Title"
            )
            is False
        )

        # Test short content with subscription words
        assert scraper._detect_paywall("Short article. Subscribe now.", "Title") is True

        # Test content ending with subscription prompt
        long_content = (
            "A" * 300 + " To continue reading, please subscribe to our premium service."
        )
        assert scraper._detect_paywall(long_content, "Title") is True

    @vcr
    def test_scrape_article_cnbc(self, scraper):
        """Test scraping CNBC article - commonly appears in Google News (recorded)."""
        # Using a generic CNBC tech page URL
        url = "https://www.cnbc.com/technology/"

        result = scraper.scrape_article(url)

        assert isinstance(result, ScrapeResult)
        assert result.final_url == url
        assert result.status in ["SUCCESS", "SCRAPE_FAILED"]

    @vcr
    def test_scrape_article_yahoo_finance(self, scraper):
        """Test scraping Yahoo Finance - frequently in Google News results (recorded)."""
        # Yahoo Finance main page
        url = "https://finance.yahoo.com/"

        result = scraper.scrape_article(url)

        assert isinstance(result, ScrapeResult)
        assert result.final_url == url
        assert result.status in ["SUCCESS", "SCRAPE_FAILED"]

    @vcr
    def test_scrape_article_seeking_alpha(self, scraper):
        """Test scraping Seeking Alpha - common financial news source (recorded)."""
        url = "https://seekingalpha.com/"

        result = scraper.scrape_article(url)

        assert isinstance(result, ScrapeResult)
        assert result.final_url == url
        # Seeking Alpha often has paywalls
        assert result.status in ["SUCCESS", "PAYWALL_DETECTED", "SCRAPE_FAILED"]

    @vcr
    def test_scrape_article_tip_ranks(self, scraper):
        """Test scraping TipRanks - appears in financial news (recorded)."""
        url = "https://www.tipranks.com/"

        result = scraper.scrape_article(url)

        assert isinstance(result, ScrapeResult)
        assert result.final_url == url
        assert result.status in ["SUCCESS", "SCRAPE_FAILED", "PAYWALL_DETECTED"]

    @vcr
    def test_scrape_article_barchart(self, scraper):
        """Test scraping Barchart - financial analysis site (recorded)."""
        url = "https://www.barchart.com/"

        result = scraper.scrape_article(url)

        assert isinstance(result, ScrapeResult)
        assert result.final_url == url
        assert result.status in ["SUCCESS", "SCRAPE_FAILED"]

    @vcr
    def test_scrape_multiple_financial_sites(self, scraper):
        """Test scraping multiple financial news sites (recorded)."""
        # Common financial news sources that appear in Google News
        urls = [
            "https://www.cnbc.com/",
            "https://finance.yahoo.com/",
            "https://www.barchart.com/",
        ]

        results = scraper.scrape_multiple_articles(urls)

        assert isinstance(results, dict)
        assert len(results) == len(urls)

        for url in urls:
            assert url in results
            assert isinstance(results[url], ScrapeResult)
            assert results[url].final_url == url
            assert results[url].status in [
                "SUCCESS",
                "SCRAPE_FAILED",
                "NOT_FOUND",
                "PAYWALL_DETECTED",
            ]

    @vcr
    def test_scrape_article_with_404(self, scraper):
        """Test handling of 404 pages (recorded)."""
        # A URL that should return 404
        url = "https://www.cnbc.com/this-page-does-not-exist-404-error"

        result = scraper.scrape_article(url)

        assert isinstance(result, ScrapeResult)
        assert result.final_url == url
        # Should handle 404 gracefully
        assert result.status in ["SCRAPE_FAILED", "NOT_FOUND"]

    @vcr
    def test_scrape_article_marketwatch(self, scraper):
        """Test scraping MarketWatch - common in financial news (recorded)."""
        url = "https://www.marketwatch.com/"

        result = scraper.scrape_article(url)

        assert isinstance(result, ScrapeResult)
        assert result.final_url == url

        # MarketWatch sometimes has access restrictions
        assert result.status in ["SUCCESS", "SCRAPE_FAILED", "PAYWALL_DETECTED"]

    @vcr
    def test_scrape_article_reuters(self, scraper):
        """Test scraping Reuters - major news source (recorded)."""
        url = "https://www.reuters.com/"

        result = scraper.scrape_article(url)

        assert isinstance(result, ScrapeResult)
        assert result.final_url == url

        # Reuters is generally accessible
        assert result.status in ["SUCCESS", "SCRAPE_FAILED"]

    @vcr
    def test_scrape_article_bloomberg(self, scraper):
        """Test scraping Bloomberg - often has paywall (recorded)."""
        url = "https://www.bloomberg.com/"

        result = scraper.scrape_article(url)

        assert isinstance(result, ScrapeResult)
        assert result.final_url == url

        # Bloomberg frequently has paywalls
        if result.status == "PAYWALL_DETECTED":
            assert result.is_paywall is True

    @vcr
    def test_scrape_article_wsj(self, scraper):
        """Test scraping WSJ - typically paywalled (recorded)."""
        url = "https://www.wsj.com/"

        result = scraper.scrape_article(url)

        assert isinstance(result, ScrapeResult)
        assert result.final_url == url

        # WSJ usually has strong paywalls
        assert result.status in ["SUCCESS", "PAYWALL_DETECTED", "SCRAPE_FAILED"]

        if result.status == "PAYWALL_DETECTED":
            assert result.is_paywall is True

    @vcr
    def test_scrape_article_forbes(self, scraper):
        """Test scraping Forbes - business news (recorded)."""
        url = "https://www.forbes.com/"

        result = scraper.scrape_article(url)

        assert isinstance(result, ScrapeResult)
        assert result.final_url == url
        assert result.status in ["SUCCESS", "SCRAPE_FAILED"]

    @vcr
    def test_scrape_article_business_insider(self, scraper):
        """Test scraping Business Insider (recorded)."""
        url = "https://www.businessinsider.com/"

        result = scraper.scrape_article(url)

        assert isinstance(result, ScrapeResult)
        assert result.final_url == url

        # Business Insider sometimes has paywalls
        assert result.status in ["SUCCESS", "PAYWALL_DETECTED", "SCRAPE_FAILED"]
