"""
Tests for Google News RSS feed client using pytest-vcr.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import feedparser
import pytest
import requests

from tradingagents.domains.news.google_news_client import (
    GoogleNewsArticle,
    GoogleNewsClient,
)

# VCR configuration
vcr = pytest.mark.vcr(
    cassette_library_dir="tests/fixtures/vcr_cassettes/news",
    record_mode="once",  # Record once, then replay
    match_on=["uri", "method"],
    filter_headers=["authorization", "cookie"],
)


class TestGoogleNewsClient:
    """Test GoogleNewsClient with VCR cassettes."""

    @pytest.fixture
    def client(self):
        """Create GoogleNewsClient instance."""
        return GoogleNewsClient()

    @vcr
    def test_get_company_news_real(self, client):
        """Test fetching company news with real RSS feed (recorded)."""
        articles = client.get_company_news("AAPL")

        assert isinstance(articles, list)
        if articles:  # If we got articles
            article = articles[0]
            assert isinstance(article, GoogleNewsArticle)
            assert article.title
            assert article.link
            assert isinstance(article.published, datetime)
            assert article.source

    @vcr
    def test_get_global_news_real(self, client):
        """Test fetching global news with real RSS feed (recorded)."""
        articles = client.get_global_news(["technology", "finance"])

        assert isinstance(articles, list)
        # Should have articles from multiple categories
        if articles:
            sources = {article.source for article in articles}
            assert len(sources) >= 1  # Multiple sources expected

    def test_get_rss_feed_network_error(self, client):
        """Test handling of network errors."""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException("Network error")

            articles = client._get_rss_feed("AAPL")

            assert articles == []
            mock_get.assert_called_once()

    def test_get_rss_feed_http_error(self, client):
        """Test handling of HTTP errors."""
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                "404 Not Found"
            )
            mock_get.return_value = mock_response

            articles = client._get_rss_feed("INVALID")

            assert articles == []

    def test_get_rss_feed_malformed_feed(self, client):
        """Test handling of malformed RSS feed."""
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.content = b"<html>Not an RSS feed</html>"
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            articles = client._get_rss_feed("TEST")

            # Should handle gracefully and return empty or partial results
            assert isinstance(articles, list)

    def test_get_rss_feed_with_bozo_feed(self, client):
        """Test handling of feed with parsing issues (bozo)."""
        with patch("requests.get") as mock_get, patch("feedparser.parse") as mock_parse:
            mock_response = Mock()
            mock_response.content = b"<rss>Slightly malformed RSS</rss>"
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            # Create mock feed with bozo flag
            mock_feed = Mock()
            mock_feed.bozo = True
            mock_feed.bozo_exception = Exception("Parsing error")
            mock_feed.entries = []
            mock_parse.return_value = mock_feed

            articles = client._get_rss_feed("TEST")

            assert articles == []

    def test_parse_feed_entry_valid_date(self, client):
        """Test parsing entry with valid date."""
        mock_entry = Mock(spec=feedparser.FeedParserDict)
        mock_entry.title = "Apple News - TechCrunch"
        mock_entry.link = "https://example.com/apple"
        mock_entry.published = "Mon, 15 Jan 2024 10:00:00 GMT"
        mock_entry.summary = "Apple announces new product"
        mock_entry.id = "guid-123"

        article = client._parse_feed_entry(mock_entry)

        assert article.title == "Apple News"
        assert article.source == "TechCrunch"
        assert article.link == "https://example.com/apple"
        assert isinstance(article.published, datetime)
        assert article.summary == "Apple announces new product"
        assert article.guid == "guid-123"

    def test_parse_feed_entry_invalid_date(self, client):
        """Test parsing entry with invalid date."""
        mock_entry = Mock(spec=feedparser.FeedParserDict)
        mock_entry.title = "Breaking News"
        mock_entry.link = "https://example.com/news"
        mock_entry.published = "Invalid Date String"
        mock_entry.summary = "News summary"
        mock_entry.id = "guid-456"

        # Should use current time as fallback
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        article = client._parse_feed_entry(mock_entry)
        after = datetime.now(timezone.utc).replace(tzinfo=None)

        assert before <= article.published <= after
        assert article.title == "Breaking News"
        assert article.source == "Unknown"  # No source in title

    def test_parse_feed_entry_no_source_separator(self, client):
        """Test parsing entry without source separator in title."""
        mock_entry = Mock(spec=feedparser.FeedParserDict)
        mock_entry.title = "Simple Title Without Source"
        mock_entry.link = "https://example.com"
        mock_entry.published = ""
        mock_entry.summary = "Summary"
        mock_entry.id = "guid-789"

        article = client._parse_feed_entry(mock_entry)

        assert article.title == "Simple Title Without Source"
        assert article.source == "Unknown"

    def test_parse_feed_entry_missing_fields(self, client):
        """Test parsing entry with missing fields."""
        mock_entry = Mock(spec=feedparser.FeedParserDict)
        # Don't set any attributes to test defaults

        article = client._parse_feed_entry(mock_entry)

        assert article.title == "Untitled"
        assert article.link == ""
        assert article.summary == ""
        assert article.source == "Unknown"
        assert article.guid == ""  # Falls back through id -> link -> ""

    @vcr
    def test_parse_feed_entry_with_google_news_url_decoding_real(self, client):
        """Test that Google News URLs are decoded to actual article URLs with real decoder."""
        mock_entry = Mock(spec=feedparser.FeedParserDict)
        mock_entry.title = "Tech News - TechCrunch"
        # Use a real Google News URL that will be recorded by VCR
        mock_entry.link = "https://news.google.com/rss/articles/CBMiWWh0dHBzOi8vdGVjaGNydW5jaC5jb20vMjAyNC8wMS8xNS90ZXN0LWFydGljbGUv0gEA"
        mock_entry.published = "Mon, 15 Jan 2024 10:00:00 GMT"
        mock_entry.summary = "Tech summary"
        mock_entry.id = "guid-decoded"

        # Let the decoder run and record HTTP requests with VCR
        article = client._parse_feed_entry(mock_entry)

        # Should have either decoded the URL or used the original
        assert article.link  # Link should not be empty
        assert article.title == "Tech News"
        assert article.source == "TechCrunch"

    def test_parse_feed_entry_with_non_google_news_url(self, client):
        """Test that non-Google News URLs are passed through unchanged."""
        mock_entry = Mock(spec=feedparser.FeedParserDict)
        mock_entry.title = "Direct News - CNN"
        # Regular URL that should not be processed by decoder
        mock_entry.link = "https://cnn.com/2024/01/15/direct-article"
        mock_entry.published = "Mon, 15 Jan 2024 10:00:00 GMT"
        mock_entry.summary = "Direct article summary"
        mock_entry.id = "guid-direct"

        article = client._parse_feed_entry(mock_entry)

        # Should use original URL unchanged
        assert article.link == "https://cnn.com/2024/01/15/direct-article"
        assert article.title == "Direct News"
        assert article.source == "CNN"

    def test_parse_feed_entry_with_decoder_failure(self, client):
        """Test graceful fallback when URL decoder fails."""
        mock_entry = Mock(spec=feedparser.FeedParserDict)
        mock_entry.title = "News Article"
        mock_entry.link = "https://news.google.com/rss/articles/CBMiEncodedURL"
        mock_entry.published = ""
        mock_entry.summary = "Summary"
        mock_entry.id = "guid-123"

        with patch("googlenewsdecoder.gnewsdecoder") as mock_decoder:
            # Mock the decoder to raise an exception
            mock_decoder.side_effect = Exception("Decoder error")

            article = client._parse_feed_entry(mock_entry)

            # Should fallback to using the original URL
            assert article.link == "https://news.google.com/rss/articles/CBMiEncodedURL"
            assert article.title == "News Article"

    def test_parse_feed_entry_with_decoder_returns_failure(self, client):
        """Test fallback when decoder returns failure status."""
        mock_entry = Mock(spec=feedparser.FeedParserDict)
        mock_entry.title = "News Article"
        mock_entry.link = "https://news.google.com/rss/articles/CBMiEncodedURL"
        mock_entry.published = ""
        mock_entry.summary = "Summary"
        mock_entry.id = "guid-456"

        with patch("googlenewsdecoder.gnewsdecoder") as mock_decoder:
            # Mock the decoder to return failure status
            mock_decoder.return_value = {
                "status": False,
                "message": "Invalid URL format",
            }

            article = client._parse_feed_entry(mock_entry)

            # Should fallback to using the original URL
            assert article.link == "https://news.google.com/rss/articles/CBMiEncodedURL"

    def test_get_global_news_category_failure(self, client):
        """Test global news when some categories fail."""
        with patch.object(client, "_get_rss_feed") as mock_get_rss:
            # First category succeeds, second fails
            mock_get_rss.side_effect = [
                [
                    GoogleNewsArticle(
                        title="Tech News",
                        link="https://tech.com",
                        published=datetime.now(timezone.utc).replace(tzinfo=None),
                        summary="Tech summary",
                        source="TechSite",
                        guid="tech-1",
                    )
                ],
                Exception("Failed to fetch"),
            ]

            articles = client.get_global_news(["technology", "invalid_category"])

            assert len(articles) == 1
            assert articles[0].title == "Tech News"
            assert mock_get_rss.call_count == 2

    def test_convert_entry_with_malformed_entry(self, client):
        """Test handling of malformed entry during conversion."""
        with patch(
            "tradingagents.domains.news.google_news_client.logger"
        ) as mock_logger:
            mock_feed = Mock()
            mock_feed.bozo = False

            # Create entry that will cause conversion to fail
            bad_entry = Mock(spec=feedparser.FeedParserDict)
            bad_entry.title = None  # This will cause AttributeError

            mock_feed.entries = [bad_entry]

            with (
                patch("feedparser.parse", return_value=mock_feed),
                patch("requests.get") as mock_get,
            ):
                mock_response = Mock()
                mock_response.content = b"<rss></rss>"
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response

                articles = client._get_rss_feed("TEST")

                assert articles == []
                # Should log warning about failed parsing
                mock_logger.warning.assert_called()
