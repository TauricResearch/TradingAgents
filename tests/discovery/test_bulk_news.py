from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.agents.discovery import NewsArticle
from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError


class TestGetBulkNewsReturnsNewsArticles:
    def test_get_bulk_news_returns_list_of_news_article_objects(self):
        mock_raw_news = [
            {
                "title": "Market Update: Tech stocks rally",
                "source": "Reuters",
                "url": "https://reuters.com/market-update",
                "published_at": datetime.now().isoformat(),
                "content_snippet": "Technology stocks led gains in early trading...",
            },
            {
                "title": "Fed signals rate decision",
                "source": "Bloomberg",
                "url": "https://bloomberg.com/fed-rates",
                "published_at": datetime.now().isoformat(),
                "content_snippet": "Federal Reserve officials indicated...",
            },
        ]

        from tradingagents.dataflows.interface import (
            _bulk_news_cache,
            get_bulk_news,
        )

        _bulk_news_cache.clear()

        with patch(
            "tradingagents.dataflows.interface._fetch_bulk_news_from_vendor"
        ) as mock_fetch:
            mock_fetch.return_value = mock_raw_news

            result = get_bulk_news(lookback_period="24h")

            assert isinstance(result, list)
            assert len(result) == 2
            for article in result:
                assert isinstance(article, NewsArticle)
                assert article.title is not None
                assert article.source is not None
                assert article.url is not None


class TestLookbackPeriodParsing:
    @pytest.mark.parametrize(
        "lookback,expected_hours",
        [
            ("1h", 1),
            ("6h", 6),
            ("24h", 24),
            ("7d", 168),
        ],
    )
    def test_lookback_period_parsing(self, lookback, expected_hours):
        from tradingagents.dataflows.interface import parse_lookback_period

        hours = parse_lookback_period(lookback)
        assert hours == expected_hours

    def test_invalid_lookback_period_raises_error(self):
        from tradingagents.dataflows.interface import parse_lookback_period

        with pytest.raises(ValueError):
            parse_lookback_period("invalid")


class TestVendorFallback:
    def test_vendor_fallback_when_primary_rate_limited(self):
        mock_openai_news = [
            {
                "title": "Fallback news from OpenAI",
                "source": "Web Search",
                "url": "https://example.com/fallback",
                "published_at": datetime.now().isoformat(),
                "content_snippet": "This is fallback content...",
            },
        ]

        from tradingagents.dataflows.interface import (
            _bulk_news_cache,
        )

        _bulk_news_cache.clear()

        with patch(
            "tradingagents.dataflows.interface.VENDOR_METHODS",
            {
                "get_bulk_news": {
                    "alpha_vantage": MagicMock(
                        side_effect=AlphaVantageRateLimitError("Rate limit")
                    ),
                    "openai": MagicMock(return_value=mock_openai_news),
                    "google": MagicMock(return_value=[]),
                }
            },
        ):
            from tradingagents.dataflows.interface import _fetch_bulk_news_from_vendor

            result = _fetch_bulk_news_from_vendor("24h")

            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["title"] == "Fallback news from OpenAI"


class TestBulkNewsCache:
    def test_cache_returns_same_results_within_ttl(self):
        from tradingagents.dataflows.interface import (
            _bulk_news_cache,
            _get_cached_bulk_news,
            _set_cached_bulk_news,
        )

        _bulk_news_cache.clear()

        test_articles = [
            NewsArticle(
                title="Cached article",
                source="Test Source",
                url="https://test.com/cached",
                published_at=datetime.now(),
                content_snippet="Cached content...",
                ticker_mentions=[],
            )
        ]

        _set_cached_bulk_news("24h", test_articles)

        cached_result = _get_cached_bulk_news("24h")
        assert cached_result is not None
        assert len(cached_result) == 1
        assert cached_result[0].title == "Cached article"

        cached_result_again = _get_cached_bulk_news("24h")
        assert cached_result_again is not None
        assert cached_result_again[0].title == cached_result[0].title


class TestEmptyResultHandling:
    def test_empty_result_handling(self):
        from tradingagents.dataflows.interface import (
            _bulk_news_cache,
            get_bulk_news,
        )

        _bulk_news_cache.clear()

        with patch(
            "tradingagents.dataflows.interface._fetch_bulk_news_from_vendor"
        ) as mock_fetch:
            mock_fetch.return_value = []

            result = get_bulk_news(lookback_period="1h")

            assert isinstance(result, list)
            assert len(result) == 0
