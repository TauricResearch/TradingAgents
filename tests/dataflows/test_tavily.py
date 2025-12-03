import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from tradingagents.dataflows.tavily import (
    get_api_key,
    get_bulk_news_tavily,
    _search_with_retry,
    DEFAULT_TIMEOUT,
    MAX_RETRIES,
)


class TestGetApiKey:

    def test_get_api_key_success(self):
        with patch.dict('os.environ', {'TAVILY_API_KEY': 'test_key_123'}):
            result = get_api_key()
            assert result == 'test_key_123'

    def test_get_api_key_missing(self):
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="TAVILY_API_KEY environment variable is not set"):
                get_api_key()


class TestSearchWithRetry:

    def test_successful_search(self):
        mock_client = Mock()
        mock_client.search.return_value = {"results": []}

        result = _search_with_retry(
            client=mock_client,
            query="test query",
            search_depth="advanced",
            topic="news",
            time_range="day",
            max_results=10,
        )

        assert result == {"results": []}
        mock_client.search.assert_called_once()

    @patch('tradingagents.dataflows.tavily.time.sleep')
    def test_retry_on_rate_limit(self, mock_sleep):
        mock_client = Mock()
        mock_client.search.side_effect = [
            Exception("Rate limit exceeded"),
            {"results": []},
        ]

        result = _search_with_retry(
            client=mock_client,
            query="test query",
            search_depth="advanced",
            topic="news",
            time_range="day",
            max_results=10,
        )

        assert result == {"results": []}
        assert mock_client.search.call_count == 2
        assert mock_sleep.call_count == 1

    @patch('tradingagents.dataflows.tavily.time.sleep')
    def test_retry_on_timeout(self, mock_sleep):
        mock_client = Mock()
        mock_client.search.side_effect = [
            Exception("Request timed out"),
            {"results": []},
        ]

        result = _search_with_retry(
            client=mock_client,
            query="test query",
            search_depth="advanced",
            topic="news",
            time_range="day",
            max_results=10,
        )

        assert result == {"results": []}
        assert mock_client.search.call_count == 2

    @patch('tradingagents.dataflows.tavily.time.sleep')
    def test_retry_on_connection_error(self, mock_sleep):
        mock_client = Mock()
        mock_client.search.side_effect = [
            Exception("Connection error occurred"),
            {"results": []},
        ]

        result = _search_with_retry(
            client=mock_client,
            query="test query",
            search_depth="advanced",
            topic="news",
            time_range="day",
            max_results=10,
        )

        assert result == {"results": []}
        assert mock_client.search.call_count == 2

    @patch('tradingagents.dataflows.tavily.time.sleep')
    def test_max_retries_exceeded(self, mock_sleep):
        mock_client = Mock()
        mock_client.search.side_effect = Exception("Rate limit 429")

        with pytest.raises(Exception, match="Rate limit 429"):
            _search_with_retry(
                client=mock_client,
                query="test query",
                search_depth="advanced",
                topic="news",
                time_range="day",
                max_results=10,
                max_retries=3,
            )

        assert mock_client.search.call_count == 3

    def test_non_retryable_error(self):
        mock_client = Mock()
        mock_client.search.side_effect = Exception("Invalid API key")

        with pytest.raises(Exception, match="Invalid API key"):
            _search_with_retry(
                client=mock_client,
                query="test query",
                search_depth="advanced",
                topic="news",
                time_range="day",
                max_results=10,
            )

        assert mock_client.search.call_count == 1


class TestGetBulkNewsTavily:

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', False)
    def test_returns_empty_when_library_not_installed(self):
        result = get_bulk_news_tavily(24)
        assert result == []

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    def test_returns_empty_when_no_api_key(self, mock_get_api_key, mock_client_class):
        mock_get_api_key.side_effect = ValueError("TAVILY_API_KEY not set")

        result = get_bulk_news_tavily(24)

        assert result == []

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    @patch('tradingagents.dataflows.tavily._search_with_retry')
    def test_basic_call(self, mock_search, mock_get_api_key, mock_client_class):
        mock_get_api_key.return_value = "test_key"
        mock_search.return_value = {"results": []}

        result = get_bulk_news_tavily(24)

        assert isinstance(result, list)
        assert mock_search.call_count == 5

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    @patch('tradingagents.dataflows.tavily._search_with_retry')
    def test_parses_articles(self, mock_search, mock_get_api_key, mock_client_class):
        mock_get_api_key.return_value = "test_key"

        mock_article = {
            "title": "Test Stock News",
            "url": "https://reuters.com/article1",
            "published_date": "2024-01-15T10:30:00Z",
            "content": "This is a test article about stocks.",
        }

        mock_search.return_value = {"results": [mock_article]}

        result = get_bulk_news_tavily(24)

        assert len(result) >= 1
        article = result[0]
        assert article["title"] == "Test Stock News"
        assert article["source"] == "Tavily"
        assert article["url"] == "https://reuters.com/article1"
        assert "published_at" in article
        assert article["content_snippet"] == "This is a test article about stocks."

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    @patch('tradingagents.dataflows.tavily._search_with_retry')
    def test_deduplicates_by_url(self, mock_search, mock_get_api_key, mock_client_class):
        mock_get_api_key.return_value = "test_key"

        duplicate_article = {
            "title": "Duplicate Article",
            "url": "https://news.com/same-url",
            "published_date": "2024-01-15T10:30:00Z",
            "content": "Duplicate content.",
        }

        mock_search.return_value = {"results": [duplicate_article, duplicate_article]}

        result = get_bulk_news_tavily(24)

        urls = [a["url"] for a in result]
        assert len(urls) == len(set(urls))

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    @patch('tradingagents.dataflows.tavily._search_with_retry')
    def test_truncates_long_content(self, mock_search, mock_get_api_key, mock_client_class):
        mock_get_api_key.return_value = "test_key"

        long_content = "A" * 1000

        mock_article = {
            "title": "Long Article",
            "url": "https://news.com/article",
            "published_date": "2024-01-15T10:30:00Z",
            "content": long_content,
        }

        mock_search.return_value = {"results": [mock_article]}

        result = get_bulk_news_tavily(24)

        assert len(result[0]["content_snippet"]) == 500

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    @patch('tradingagents.dataflows.tavily._search_with_retry')
    def test_time_range_day(self, mock_search, mock_get_api_key, mock_client_class):
        mock_get_api_key.return_value = "test_key"
        mock_search.return_value = {"results": []}

        get_bulk_news_tavily(24)

        call_kwargs = mock_search.call_args_list[0][1]
        assert call_kwargs["time_range"] == "day"

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    @patch('tradingagents.dataflows.tavily._search_with_retry')
    def test_time_range_week(self, mock_search, mock_get_api_key, mock_client_class):
        mock_get_api_key.return_value = "test_key"
        mock_search.return_value = {"results": []}

        get_bulk_news_tavily(168)

        call_kwargs = mock_search.call_args_list[0][1]
        assert call_kwargs["time_range"] == "week"

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    @patch('tradingagents.dataflows.tavily._search_with_retry')
    def test_time_range_month(self, mock_search, mock_get_api_key, mock_client_class):
        mock_get_api_key.return_value = "test_key"
        mock_search.return_value = {"results": []}

        get_bulk_news_tavily(720)

        call_kwargs = mock_search.call_args_list[0][1]
        assert call_kwargs["time_range"] == "month"

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    @patch('tradingagents.dataflows.tavily._search_with_retry')
    def test_handles_missing_published_date(self, mock_search, mock_get_api_key, mock_client_class):
        mock_get_api_key.return_value = "test_key"

        mock_article = {
            "title": "Article Without Date",
            "url": "https://news.com/article",
            "content": "Content",
        }

        mock_search.return_value = {"results": [mock_article]}

        result = get_bulk_news_tavily(24)

        assert len(result) == 1
        assert "published_at" in result[0]

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    @patch('tradingagents.dataflows.tavily._search_with_retry')
    def test_handles_invalid_date_format(self, mock_search, mock_get_api_key, mock_client_class):
        mock_get_api_key.return_value = "test_key"

        mock_article = {
            "title": "Article With Bad Date",
            "url": "https://news.com/article",
            "published_date": "invalid_date_format",
            "content": "Content",
        }

        mock_search.return_value = {"results": [mock_article]}

        result = get_bulk_news_tavily(24)

        assert len(result) == 1
        assert "published_at" in result[0]

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    @patch('tradingagents.dataflows.tavily._search_with_retry')
    def test_continues_on_query_failure(self, mock_search, mock_get_api_key, mock_client_class):
        mock_get_api_key.return_value = "test_key"

        mock_search.side_effect = [
            Exception("Query failed"),
            {"results": [{"title": "Article", "url": "https://test.com", "content": "test"}]},
            {"results": []},
            {"results": []},
            {"results": []},
        ]

        result = get_bulk_news_tavily(24)

        assert len(result) > 0

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    @patch('tradingagents.dataflows.tavily._search_with_retry')
    def test_skips_articles_without_url(self, mock_search, mock_get_api_key, mock_client_class):
        mock_get_api_key.return_value = "test_key"

        mock_articles = [
            {"title": "No URL Article", "content": "test"},
            {"title": "Has URL", "url": "https://test.com", "content": "test"},
        ]

        mock_search.return_value = {"results": mock_articles}

        result = get_bulk_news_tavily(24)

        urls = [a["url"] for a in result if a.get("url")]
        assert all(url for url in urls)

    @patch('tradingagents.dataflows.tavily.TAVILY_AVAILABLE', True)
    @patch('tradingagents.dataflows.tavily.TavilyClient')
    @patch('tradingagents.dataflows.tavily.get_api_key')
    @patch('tradingagents.dataflows.tavily._search_with_retry')
    def test_uses_correct_search_parameters(self, mock_search, mock_get_api_key, mock_client_class):
        mock_get_api_key.return_value = "test_key"
        mock_search.return_value = {"results": []}

        get_bulk_news_tavily(24)

        call_kwargs = mock_search.call_args_list[0][1]
        assert call_kwargs["search_depth"] == "advanced"
        assert call_kwargs["topic"] == "news"
        assert call_kwargs["max_results"] == 10
