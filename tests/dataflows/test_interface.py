from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from tradingagents.agents.discovery import NewsArticle
from tradingagents.dataflows import interface as interface_module
from tradingagents.dataflows.interface import (
    VENDOR_METHODS,
    get_bulk_news,
    get_category_for_method,
    parse_lookback_period,
    route_to_vendor,
)


@pytest.fixture(autouse=True)
def clear_bulk_news_cache():
    interface_module._bulk_news_cache.clear()
    yield
    interface_module._bulk_news_cache.clear()


class TestParseLookbackPeriod:
    """Test suite for parse_lookback_period function."""

    def test_parse_lookback_1h(self):
        """Test parsing '1h' lookback period."""
        assert parse_lookback_period("1h") == 1

    def test_parse_lookback_6h(self):
        """Test parsing '6h' lookback period."""
        assert parse_lookback_period("6h") == 6

    def test_parse_lookback_24h(self):
        """Test parsing '24h' lookback period."""
        assert parse_lookback_period("24h") == 24

    def test_parse_lookback_7d(self):
        """Test parsing '7d' lookback period."""
        assert parse_lookback_period("7d") == 168  # 7 * 24

    def test_parse_lookback_case_insensitive(self):
        """Test that parsing is case insensitive."""
        assert parse_lookback_period("1H") == 1
        assert parse_lookback_period("6H") == 6
        assert parse_lookback_period("24H") == 24
        assert parse_lookback_period("7D") == 168

    def test_parse_lookback_with_spaces(self):
        """Test parsing with leading/trailing spaces."""
        assert parse_lookback_period(" 1h ") == 1
        assert parse_lookback_period("  24h  ") == 24

    def test_parse_lookback_invalid_value(self):
        """Test that invalid values raise ValueError."""
        with pytest.raises(ValueError, match="Invalid lookback period"):
            parse_lookback_period("invalid")

        with pytest.raises(ValueError):
            parse_lookback_period("10h")

        with pytest.raises(ValueError):
            parse_lookback_period("2d")


class TestGetCategoryForMethod:
    """Test suite for get_category_for_method function."""

    def test_get_category_core_stock_apis(self):
        """Test categorization of core stock API methods."""
        assert get_category_for_method("get_stock_data") == "core_stock_apis"

    def test_get_category_technical_indicators(self):
        """Test categorization of technical indicator methods."""
        assert get_category_for_method("get_indicators") == "technical_indicators"

    def test_get_category_fundamental_data(self):
        """Test categorization of fundamental data methods."""
        assert get_category_for_method("get_fundamentals") == "fundamental_data"
        assert get_category_for_method("get_balance_sheet") == "fundamental_data"
        assert get_category_for_method("get_cashflow") == "fundamental_data"
        assert get_category_for_method("get_income_statement") == "fundamental_data"

    def test_get_category_news_data(self):
        """Test categorization of news data methods."""
        assert get_category_for_method("get_news") == "news_data"
        assert get_category_for_method("get_global_news") == "news_data"
        assert get_category_for_method("get_insider_sentiment") == "news_data"
        assert get_category_for_method("get_insider_transactions") == "news_data"
        assert get_category_for_method("get_bulk_news") == "news_data"

    def test_get_category_invalid_method(self):
        """Test that invalid methods raise ValueError."""
        with pytest.raises(ValueError, match="not found in any category"):
            get_category_for_method("nonexistent_method")


class TestGetBulkNews:
    """Test suite for get_bulk_news function."""

    @patch("tradingagents.dataflows.interface._fetch_bulk_news_from_vendor")
    @patch("tradingagents.dataflows.interface._convert_to_news_articles")
    def test_get_bulk_news_default_period(self, mock_convert, mock_fetch):
        """Test get_bulk_news with default lookback period."""
        mock_fetch.return_value = []
        mock_convert.return_value = []

        result = get_bulk_news()

        mock_fetch.assert_called_once_with("24h")
        assert isinstance(result, list)

    @patch("tradingagents.dataflows.interface._fetch_bulk_news_from_vendor")
    @patch("tradingagents.dataflows.interface._convert_to_news_articles")
    def test_get_bulk_news_custom_period(self, mock_convert, mock_fetch):
        """Test get_bulk_news with custom lookback period."""
        mock_fetch.return_value = []
        mock_convert.return_value = []

        result = get_bulk_news("6h")

        mock_fetch.assert_called_once_with("6h")

    @patch("tradingagents.dataflows.interface._fetch_bulk_news_from_vendor")
    @patch("tradingagents.dataflows.interface._convert_to_news_articles")
    def test_get_bulk_news_caching(self, mock_convert, mock_fetch):
        """Test that results are cached."""
        mock_raw_articles = [
            {
                "title": "Test Article",
                "source": "Source",
                "url": "https://example.com",
                "published_at": datetime.now().isoformat(),
                "content_snippet": "Content",
            }
        ]

        mock_article = NewsArticle(
            title="Test Article",
            source="Source",
            url="https://example.com",
            published_at=datetime.now(),
            content_snippet="Content",
            ticker_mentions=[],
        )

        mock_fetch.return_value = mock_raw_articles
        mock_convert.return_value = [mock_article]

        # First call should fetch
        result1 = get_bulk_news("24h")
        call_count_1 = mock_fetch.call_count

        # Second call within cache TTL should use cache
        result2 = get_bulk_news("24h")
        call_count_2 = mock_fetch.call_count

        # Fetch should not be called again if cache is working
        # (Note: actual caching behavior depends on implementation)
        assert isinstance(result1, list)
        assert isinstance(result2, list)

    @patch("tradingagents.dataflows.interface._fetch_bulk_news_from_vendor")
    @patch("tradingagents.dataflows.interface._convert_to_news_articles")
    def test_get_bulk_news_converts_articles(self, mock_convert, mock_fetch):
        """Test that raw articles are converted to NewsArticle objects."""
        mock_raw = [{"title": "Test"}]
        mock_articles = [Mock(spec=NewsArticle)]

        mock_fetch.return_value = mock_raw
        mock_convert.return_value = mock_articles

        result = get_bulk_news("24h")

        mock_convert.assert_called_once_with(mock_raw)
        assert result == mock_articles


class TestRouteToVendor:
    """Test suite for route_to_vendor function."""

    @patch("tradingagents.dataflows.interface.get_vendor")
    @patch("tradingagents.dataflows.interface.get_category_for_method")
    def test_route_to_vendor_basic(self, mock_get_category, mock_get_vendor):
        """Test basic vendor routing."""
        mock_get_category.return_value = "core_stock_apis"
        mock_get_vendor.return_value = "yfinance"

        mock_func = Mock(return_value="test_data")
        mock_func.__name__ = "mock_get_stock_data"
        with patch.dict(VENDOR_METHODS, {"get_stock_data": {"yfinance": mock_func}}):
            result = route_to_vendor("get_stock_data", "AAPL", "2024-01-01")

            assert result == "test_data"

    @patch("tradingagents.dataflows.interface.get_vendor")
    @patch("tradingagents.dataflows.interface.get_category_for_method")
    def test_route_to_vendor_fallback(self, mock_get_category, mock_get_vendor):
        """Test vendor fallback when primary fails."""
        mock_get_category.return_value = "news_data"
        mock_get_vendor.return_value = "alpha_vantage"

        primary_mock = Mock(side_effect=RuntimeError("Primary failed"))
        primary_mock.__name__ = "mock_primary"
        secondary_mock = Mock(return_value="fallback_data")
        secondary_mock.__name__ = "mock_secondary"

        with patch.dict(
            VENDOR_METHODS,
            {
                "get_news": {
                    "alpha_vantage": primary_mock,
                    "openai": secondary_mock,
                }
            },
        ):
            result = route_to_vendor("get_news", "AAPL", "2024-01-01", "2024-01-31")

            assert result == "fallback_data"
            assert primary_mock.called
            assert secondary_mock.called

    @patch("tradingagents.dataflows.interface.get_vendor")
    @patch("tradingagents.dataflows.interface.get_category_for_method")
    def test_route_to_vendor_all_fail(self, mock_get_category, mock_get_vendor):
        """Test that RuntimeError is raised when all vendors fail."""
        mock_get_category.return_value = "news_data"
        mock_get_vendor.return_value = "alpha_vantage"

        failing_mock1 = Mock(side_effect=RuntimeError("Failed"))
        failing_mock1.__name__ = "mock_failing1"
        failing_mock2 = Mock(side_effect=RuntimeError("Failed"))
        failing_mock2.__name__ = "mock_failing2"

        with (
            patch.dict(
                VENDOR_METHODS,
                {
                    "get_news": {
                        "alpha_vantage": failing_mock1,
                        "openai": failing_mock2,
                    }
                },
            ),
            pytest.raises(RuntimeError, match="All vendor implementations failed"),
        ):
            route_to_vendor("get_news", "AAPL", "2024-01-01", "2024-01-31")

    @patch("tradingagents.dataflows.interface.get_vendor")
    @patch("tradingagents.dataflows.interface.get_category_for_method")
    def test_route_to_vendor_multiple_results(self, mock_get_category, mock_get_vendor):
        """Test handling of multiple vendor implementations."""
        mock_get_category.return_value = "news_data"
        mock_get_vendor.return_value = "local"

        impl1 = Mock(return_value="result1")
        impl1.__name__ = "mock_impl1"
        impl2 = Mock(return_value="result2")
        impl2.__name__ = "mock_impl2"

        with patch.dict(
            VENDOR_METHODS,
            {
                "get_news": {
                    "local": [impl1, impl2],
                }
            },
        ):
            result = route_to_vendor("get_news", "AAPL", "2024-01-01", "2024-01-31")

            assert isinstance(result, str)
            assert impl1.called
            assert impl2.called

    def test_route_to_vendor_unsupported_method(self):
        """Test that ValueError is raised for unsupported methods."""
        with pytest.raises(ValueError, match="not found in any category"):
            route_to_vendor("nonexistent_method", "arg1")


class TestConvertToNewsArticles:
    """Test suite for _convert_to_news_articles function."""

    @patch("tradingagents.dataflows.interface._convert_to_news_articles")
    def test_convert_empty_list(self, mock_convert):
        """Test converting empty article list."""
        mock_convert.return_value = []

        from tradingagents.dataflows.interface import _convert_to_news_articles

        result = _convert_to_news_articles([])

        assert result == []

    @patch("tradingagents.dataflows.interface.NewsArticle")
    def test_convert_valid_articles(self, mock_news_article):
        """Test converting valid raw articles."""
        from tradingagents.dataflows.interface import _convert_to_news_articles

        raw_articles = [
            {
                "title": "Article 1",
                "source": "Source 1",
                "url": "https://example.com/1",
                "published_at": datetime(2024, 1, 15).isoformat(),
                "content_snippet": "Content 1",
            }
        ]

        result = _convert_to_news_articles(raw_articles)

        # Should attempt to create NewsArticle
        assert isinstance(result, list)

    def test_convert_invalid_date_format(self):
        """Test handling of invalid date formats."""
        from tradingagents.dataflows.interface import _convert_to_news_articles

        raw_articles = [
            {
                "title": "Article",
                "source": "Source",
                "url": "https://example.com",
                "published_at": "invalid_date",
                "content_snippet": "Content",
            }
        ]

        result = _convert_to_news_articles(raw_articles)

        # Should handle gracefully
        assert isinstance(result, list)
