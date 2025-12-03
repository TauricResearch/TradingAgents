from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
import requests

from tradingagents.dataflows.brave import (
    _make_request_with_retry,
    _parse_brave_age,
    get_api_key,
    get_bulk_news_brave,
)


class TestGetApiKey:
    def test_get_api_key_success(self):
        from tradingagents import config as main_config

        main_config._settings = None
        with patch.dict(
            "os.environ", {"TRADINGAGENTS_BRAVE_API_KEY": "test_key_123"}, clear=False
        ):
            result = get_api_key()
            assert result == "test_key_123"

    def test_get_api_key_missing(self):
        with patch("tradingagents.config.get_settings") as mock_get_settings:
            mock_settings = Mock()
            mock_settings.require_api_key.side_effect = ValueError(
                "brave API key not configured"
            )
            mock_get_settings.return_value = mock_settings
            with pytest.raises(ValueError, match="brave API key not configured"):
                get_api_key()


class TestParseBraveAge:
    def test_parse_hours_ago(self):
        result = _parse_brave_age("2 hours ago")
        expected = datetime.now() - timedelta(hours=2)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_single_hour(self):
        result = _parse_brave_age("1 hour ago")
        expected = datetime.now() - timedelta(hours=1)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_days_ago(self):
        result = _parse_brave_age("3 days ago")
        expected = datetime.now() - timedelta(days=3)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_weeks_ago(self):
        result = _parse_brave_age("2 weeks ago")
        expected = datetime.now() - timedelta(weeks=2)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_minutes_ago(self):
        result = _parse_brave_age("30 minutes ago")
        expected = datetime.now() - timedelta(minutes=30)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_empty_string(self):
        result = _parse_brave_age("")
        expected = datetime.now()
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_invalid_format(self):
        result = _parse_brave_age("invalid format")
        expected = datetime.now()
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_uppercase(self):
        result = _parse_brave_age("5 HOURS AGO")
        expected = datetime.now() - timedelta(hours=5)
        assert abs((result - expected).total_seconds()) < 2


class TestMakeRequestWithRetry:
    @patch("tradingagents.dataflows.brave.requests.get")
    def test_successful_request(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = _make_request_with_retry("http://test.com", {}, {})

        assert result == mock_response
        mock_get.assert_called_once()

    @patch("tradingagents.dataflows.brave.requests.get")
    @patch("tradingagents.dataflows.brave.time.sleep")
    def test_retry_on_timeout(self, mock_sleep, mock_get):
        mock_get.side_effect = [
            requests.exceptions.Timeout(),
            requests.exceptions.Timeout(),
            Mock(status_code=200, raise_for_status=Mock()),
        ]

        result = _make_request_with_retry("http://test.com", {}, {})

        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("tradingagents.dataflows.brave.requests.get")
    @patch("tradingagents.dataflows.brave.time.sleep")
    def test_retry_on_connection_error(self, mock_sleep, mock_get):
        mock_get.side_effect = [
            requests.exceptions.ConnectionError(),
            Mock(status_code=200, raise_for_status=Mock()),
        ]

        result = _make_request_with_retry("http://test.com", {}, {})

        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("tradingagents.dataflows.brave.requests.get")
    @patch("tradingagents.dataflows.brave.time.sleep")
    def test_retry_on_rate_limit(self, mock_sleep, mock_get):
        rate_limited_response = Mock()
        rate_limited_response.status_code = 429
        rate_limited_response.headers = {"Retry-After": "1"}

        success_response = Mock()
        success_response.status_code = 200
        success_response.raise_for_status = Mock()

        mock_get.side_effect = [rate_limited_response, success_response]

        result = _make_request_with_retry("http://test.com", {}, {})

        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("tradingagents.dataflows.brave.requests.get")
    @patch("tradingagents.dataflows.brave.time.sleep")
    def test_max_retries_exceeded(self, mock_sleep, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout()

        with pytest.raises(requests.exceptions.Timeout):
            _make_request_with_retry("http://test.com", {}, {}, max_retries=3)

        assert mock_get.call_count == 3

    @patch("tradingagents.dataflows.brave.requests.get")
    def test_non_retryable_http_error(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        mock_get.return_value = mock_response

        with pytest.raises(requests.exceptions.HTTPError):
            _make_request_with_retry("http://test.com", {}, {})

        assert mock_get.call_count == 1


class TestGetBulkNewsBrave:
    @patch("tradingagents.dataflows.brave.get_api_key")
    def test_returns_empty_when_no_api_key(self, mock_get_api_key):
        mock_get_api_key.side_effect = ValueError("BRAVE_API_KEY not set")

        result = get_bulk_news_brave(24)

        assert result == []

    @patch("tradingagents.dataflows.brave._make_request_with_retry")
    @patch("tradingagents.dataflows.brave.get_api_key")
    def test_basic_call(self, mock_get_api_key, mock_request):
        mock_get_api_key.return_value = "test_key"
        mock_response = Mock()
        mock_response.json.return_value = {"results": []}
        mock_request.return_value = mock_response

        result = get_bulk_news_brave(24)

        assert isinstance(result, list)
        assert mock_request.call_count == 5

    @patch("tradingagents.dataflows.brave._make_request_with_retry")
    @patch("tradingagents.dataflows.brave.get_api_key")
    def test_parses_articles(self, mock_get_api_key, mock_request):
        mock_get_api_key.return_value = "test_key"

        mock_article = {
            "title": "Test Stock News",
            "meta_url": {"netloc": "reuters.com"},
            "url": "https://reuters.com/article1",
            "age": "2 hours ago",
            "description": "This is a test article about stocks.",
        }

        mock_response = Mock()
        mock_response.json.return_value = {"results": [mock_article]}
        mock_request.return_value = mock_response

        result = get_bulk_news_brave(24)

        assert len(result) >= 1
        article = result[0]
        assert article["title"] == "Test Stock News"
        assert article["source"] == "reuters.com"
        assert article["url"] == "https://reuters.com/article1"
        assert "published_at" in article
        assert article["content_snippet"] == "This is a test article about stocks."

    @patch("tradingagents.dataflows.brave._make_request_with_retry")
    @patch("tradingagents.dataflows.brave.get_api_key")
    def test_deduplicates_by_url(self, mock_get_api_key, mock_request):
        mock_get_api_key.return_value = "test_key"

        duplicate_article = {
            "title": "Duplicate Article",
            "meta_url": {"netloc": "news.com"},
            "url": "https://news.com/same-url",
            "age": "1 hour ago",
            "description": "Duplicate content.",
        }

        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [duplicate_article, duplicate_article]
        }
        mock_request.return_value = mock_response

        result = get_bulk_news_brave(24)

        urls = [a["url"] for a in result]
        assert len(urls) == len(set(urls))

    @patch("tradingagents.dataflows.brave._make_request_with_retry")
    @patch("tradingagents.dataflows.brave.get_api_key")
    def test_truncates_long_descriptions(self, mock_get_api_key, mock_request):
        mock_get_api_key.return_value = "test_key"

        long_description = "A" * 1000

        mock_article = {
            "title": "Long Article",
            "meta_url": {"netloc": "news.com"},
            "url": "https://news.com/article",
            "age": "1 hour ago",
            "description": long_description,
        }

        mock_response = Mock()
        mock_response.json.return_value = {"results": [mock_article]}
        mock_request.return_value = mock_response

        result = get_bulk_news_brave(24)

        assert len(result[0]["content_snippet"]) == 500

    @patch("tradingagents.dataflows.brave._make_request_with_retry")
    @patch("tradingagents.dataflows.brave.get_api_key")
    def test_freshness_parameter_24h(self, mock_get_api_key, mock_request):
        mock_get_api_key.return_value = "test_key"
        mock_response = Mock()
        mock_response.json.return_value = {"results": []}
        mock_request.return_value = mock_response

        get_bulk_news_brave(24)

        call_args = mock_request.call_args_list[0]
        params = call_args[0][2]
        assert params["freshness"] == "pd"

    @patch("tradingagents.dataflows.brave._make_request_with_retry")
    @patch("tradingagents.dataflows.brave.get_api_key")
    def test_freshness_parameter_7d(self, mock_get_api_key, mock_request):
        mock_get_api_key.return_value = "test_key"
        mock_response = Mock()
        mock_response.json.return_value = {"results": []}
        mock_request.return_value = mock_response

        get_bulk_news_brave(168)

        call_args = mock_request.call_args_list[0]
        params = call_args[0][2]
        assert params["freshness"] == "pw"

    @patch("tradingagents.dataflows.brave._make_request_with_retry")
    @patch("tradingagents.dataflows.brave.get_api_key")
    def test_freshness_parameter_month(self, mock_get_api_key, mock_request):
        mock_get_api_key.return_value = "test_key"
        mock_response = Mock()
        mock_response.json.return_value = {"results": []}
        mock_request.return_value = mock_response

        get_bulk_news_brave(720)

        call_args = mock_request.call_args_list[0]
        params = call_args[0][2]
        assert params["freshness"] == "pm"

    @patch("tradingagents.dataflows.brave._make_request_with_retry")
    @patch("tradingagents.dataflows.brave.get_api_key")
    def test_handles_missing_meta_url(self, mock_get_api_key, mock_request):
        mock_get_api_key.return_value = "test_key"

        mock_article = {
            "title": "Article Without Meta URL",
            "url": "https://news.com/article",
            "age": "1 hour ago",
            "description": "Content",
        }

        mock_response = Mock()
        mock_response.json.return_value = {"results": [mock_article]}
        mock_request.return_value = mock_response

        result = get_bulk_news_brave(24)

        assert result[0]["source"] == "Brave News"

    @patch("tradingagents.dataflows.brave._make_request_with_retry")
    @patch("tradingagents.dataflows.brave.get_api_key")
    def test_continues_on_query_failure(self, mock_get_api_key, mock_request):
        mock_get_api_key.return_value = "test_key"

        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Article",
                    "url": "https://test.com",
                    "age": "1h",
                    "description": "test",
                }
            ]
        }

        mock_request.side_effect = [
            requests.exceptions.HTTPError("Error"),
            mock_response,
            mock_response,
            mock_response,
            mock_response,
        ]

        result = get_bulk_news_brave(24)

        assert len(result) > 0

    @patch("tradingagents.dataflows.brave._make_request_with_retry")
    @patch("tradingagents.dataflows.brave.get_api_key")
    def test_skips_articles_without_url(self, mock_get_api_key, mock_request):
        mock_get_api_key.return_value = "test_key"

        mock_articles = [
            {"title": "No URL Article", "age": "1h", "description": "test"},
            {
                "title": "Has URL",
                "url": "https://test.com",
                "age": "1h",
                "description": "test",
            },
        ]

        mock_response = Mock()
        mock_response.json.return_value = {"results": mock_articles}
        mock_request.return_value = mock_response

        result = get_bulk_news_brave(24)

        urls = [a["url"] for a in result if a.get("url")]
        assert all(url for url in urls)
