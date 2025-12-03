import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from tradingagents.dataflows.alpha_vantage_news import (
    get_news,
    get_insider_transactions,
    get_bulk_news_alpha_vantage,
)


class TestGetNews:
    """Test suite for get_news function."""

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_news_basic_call(self, mock_format_datetime, mock_api_request):
        """Test basic get_news API call."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        mock_api_request.return_value = {"feed": []}
        
        ticker = "AAPL"
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)
        
        result = get_news(ticker, start_date, end_date)
        
        mock_api_request.assert_called_once()
        call_args = mock_api_request.call_args[0]
        assert call_args[0] == "NEWS_SENTIMENT"

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_news_parameters(self, mock_format_datetime, mock_api_request):
        """Test that get_news passes correct parameters."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        mock_api_request.return_value = {"feed": []}
        
        ticker = "TSLA"
        start_date = datetime(2024, 2, 1)
        end_date = datetime(2024, 2, 15)
        
        result = get_news(ticker, start_date, end_date)
        
        params = mock_api_request.call_args[0][1]
        assert params["tickers"] == "TSLA"
        assert params["sort"] == "LATEST"
        assert params["limit"] == "50"

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_news_different_tickers(self, mock_format_datetime, mock_api_request):
        """Test get_news with different ticker symbols."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        mock_api_request.return_value = {"feed": []}
        
        tickers = ["AAPL", "GOOGL", "MSFT", "AMZN"]
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)
        
        for ticker in tickers:
            result = get_news(ticker, start_date, end_date)
            params = mock_api_request.call_args[0][1]
            assert params["tickers"] == ticker


class TestGetInsiderTransactions:
    """Test suite for get_insider_transactions function."""

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    def test_get_insider_transactions_basic(self, mock_api_request):
        """Test basic get_insider_transactions call."""
        mock_api_request.return_value = {"transactions": []}
        
        symbol = "AAPL"
        result = get_insider_transactions(symbol)
        
        mock_api_request.assert_called_once()
        call_args = mock_api_request.call_args[0]
        assert call_args[0] == "INSIDER_TRANSACTIONS"
        assert call_args[1]["symbol"] == "AAPL"

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    def test_get_insider_transactions_different_symbols(self, mock_api_request):
        """Test get_insider_transactions with various symbols."""
        mock_api_request.return_value = {}
        
        symbols = ["AAPL", "TSLA", "NVDA", "META"]
        
        for symbol in symbols:
            result = get_insider_transactions(symbol)
            params = mock_api_request.call_args[0][1]
            assert params["symbol"] == symbol


class TestGetBulkNewsAlphaVantage:
    """Test suite for get_bulk_news_alpha_vantage function."""

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_bulk_news_basic(self, mock_format_datetime, mock_api_request):
        """Test basic bulk news retrieval."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        mock_api_request.return_value = {"feed": []}
        
        result = get_bulk_news_alpha_vantage(24)
        
        assert isinstance(result, list)
        mock_api_request.assert_called_once()

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_bulk_news_lookback_hours(self, mock_format_datetime, mock_api_request):
        """Test that lookback period is calculated correctly."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        mock_api_request.return_value = {"feed": []}
        
        lookback_hours = 6
        result = get_bulk_news_alpha_vantage(lookback_hours)
        
        # Verify time_from and time_to are set correctly
        params = mock_api_request.call_args[0][1]
        assert "time_from" in params
        assert "time_to" in params

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_bulk_news_parameters(self, mock_format_datetime, mock_api_request):
        """Test that bulk news uses correct parameters."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        mock_api_request.return_value = {"feed": []}
        
        result = get_bulk_news_alpha_vantage(24)
        
        params = mock_api_request.call_args[0][1]
        assert params["sort"] == "LATEST"
        assert params["limit"] == "200"
        assert "topics" in params
        assert "earnings" in params["topics"]

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_bulk_news_with_articles(self, mock_format_datetime, mock_api_request):
        """Test parsing of article feed data."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        
        mock_feed = {
            "feed": [
                {
                    "title": "Apple announces new product",
                    "source": "Reuters",
                    "url": "https://example.com/article1",
                    "time_published": "20240115T103000",
                    "summary": "Apple Inc. has announced a groundbreaking new product.",
                },
                {
                    "title": "Tech stocks rally",
                    "source": "Bloomberg",
                    "url": "https://example.com/article2",
                    "time_published": "20240115T140000",
                    "summary": "Technology stocks surged in afternoon trading.",
                },
            ]
        }
        
        mock_api_request.return_value = mock_feed
        
        result = get_bulk_news_alpha_vantage(24)
        
        assert len(result) == 2
        assert result[0]["title"] == "Apple announces new product"
        assert result[0]["source"] == "Reuters"
        assert result[1]["title"] == "Tech stocks rally"

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_bulk_news_content_truncation(self, mock_format_datetime, mock_api_request):
        """Test that content snippets are truncated to 500 characters."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        
        long_summary = "A" * 1000  # 1000 character string
        
        mock_feed = {
            "feed": [
                {
                    "title": "Long article",
                    "source": "Source",
                    "url": "https://example.com",
                    "time_published": "20240115T120000",
                    "summary": long_summary,
                }
            ]
        }
        
        mock_api_request.return_value = mock_feed
        
        result = get_bulk_news_alpha_vantage(24)
        
        assert len(result[0]["content_snippet"]) == 500

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_bulk_news_invalid_time_format(self, mock_format_datetime, mock_api_request):
        """Test handling of invalid time_published format."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        
        mock_feed = {
            "feed": [
                {
                    "title": "Article with bad time",
                    "source": "Source",
                    "url": "https://example.com",
                    "time_published": "invalid_format",
                    "summary": "Summary",
                }
            ]
        }
        
        mock_api_request.return_value = mock_feed
        
        result = get_bulk_news_alpha_vantage(24)
        
        # Should fallback to current time
        assert len(result) == 1
        assert "published_at" in result[0]

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_bulk_news_string_response(self, mock_format_datetime, mock_api_request):
        """Test handling when API returns string instead of dict."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        
        # Return a JSON string
        mock_api_request.return_value = '{"feed": [{"title": "Test"}]}'
        
        result = get_bulk_news_alpha_vantage(24)
        
        # Should handle gracefully and return empty list or parsed data
        assert isinstance(result, list)

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_bulk_news_malformed_articles(self, mock_format_datetime, mock_api_request):
        """Test handling of malformed article data."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        
        mock_feed = {
            "feed": [
                {"title": "Good article", "source": "Source", "url": "https://example.com", "time_published": "20240115T120000", "summary": "Good"},
                {"title": "Missing fields"},  # Malformed
                {"source": "No title"},  # Malformed
            ]
        }
        
        mock_api_request.return_value = mock_feed
        
        result = get_bulk_news_alpha_vantage(24)
        
        # Should skip malformed articles
        assert len(result) >= 1  # At least the good one

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_bulk_news_empty_feed(self, mock_format_datetime, mock_api_request):
        """Test handling of empty feed."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        mock_api_request.return_value = {"feed": []}
        
        result = get_bulk_news_alpha_vantage(24)
        
        assert result == []

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_bulk_news_no_feed_key(self, mock_format_datetime, mock_api_request):
        """Test handling when response doesn't have 'feed' key."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        mock_api_request.return_value = {"data": []}  # Wrong key
        
        result = get_bulk_news_alpha_vantage(24)
        
        assert result == []

    @patch('tradingagents.dataflows.alpha_vantage_news._make_api_request')
    @patch('tradingagents.dataflows.alpha_vantage_news.format_datetime_for_api')
    def test_get_bulk_news_various_lookback_periods(self, mock_format_datetime, mock_api_request):
        """Test bulk news with various lookback periods."""
        mock_format_datetime.side_effect = lambda x: x.strftime("%Y%m%dT%H%M%S")
        mock_api_request.return_value = {"feed": []}
        
        lookback_periods = [1, 6, 12, 24, 48, 168]  # hours
        
        for hours in lookback_periods:
            result = get_bulk_news_alpha_vantage(hours)
            assert isinstance(result, list)