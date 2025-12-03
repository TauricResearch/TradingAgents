from unittest.mock import patch

from tradingagents.dataflows.google import (
    get_bulk_news_google,
    get_google_news,
)


class TestGetGoogleNews:
    """Test suite for get_google_news function."""

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_google_news_basic(self, mock_get_news_data):
        """Test basic Google News retrieval."""
        mock_get_news_data.return_value = []

        query = "AAPL stock"
        curr_date = "2024-01-15"
        look_back_days = 7

        result = get_google_news(query, curr_date, look_back_days)

        assert isinstance(result, str)
        mock_get_news_data.assert_called_once()

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_google_news_query_formatting(self, mock_get_news_data):
        """Test that query spaces are replaced with plus signs."""
        mock_get_news_data.return_value = []

        query = "Apple Inc stock news"
        curr_date = "2024-01-15"
        look_back_days = 7

        result = get_google_news(query, curr_date, look_back_days)

        # Query should be formatted with + instead of spaces
        call_args = mock_get_news_data.call_args[0]
        assert "+" in call_args[0] or call_args[0] == query.replace(" ", "+")

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_google_news_with_results(self, mock_get_news_data):
        """Test formatting of news results."""
        mock_news = [
            {
                "title": "Apple stock rises",
                "source": "Bloomberg",
                "snippet": "Apple Inc. shares rose 5% today...",
            },
            {
                "title": "New iPhone release",
                "source": "Reuters",
                "snippet": "Apple announces new iPhone model...",
            },
        ]

        mock_get_news_data.return_value = mock_news

        query = "AAPL"
        curr_date = "2024-01-15"
        look_back_days = 7

        result = get_google_news(query, curr_date, look_back_days)

        assert "Apple stock rises" in result
        assert "New iPhone release" in result
        assert "Bloomberg" in result
        assert "Reuters" in result

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_google_news_empty_results(self, mock_get_news_data):
        """Test handling of empty news results."""
        mock_get_news_data.return_value = []

        query = "NonexistentTicker"
        curr_date = "2024-01-15"
        look_back_days = 7

        result = get_google_news(query, curr_date, look_back_days)

        assert result == ""

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_google_news_date_calculation(self, mock_get_news_data):
        """Test that lookback date is calculated correctly."""
        mock_get_news_data.return_value = []

        query = "TSLA"
        curr_date = "2024-01-15"
        look_back_days = 30

        result = get_google_news(query, curr_date, look_back_days)

        # Verify date calculation by checking call arguments
        call_args = mock_get_news_data.call_args[0]
        before_date = call_args[1]
        end_date = call_args[2]

        assert end_date == curr_date


class TestGetBulkNewsGoogle:
    """Test suite for get_bulk_news_google function."""

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_bulk_news_google_basic(self, mock_get_news_data):
        """Test basic bulk news retrieval."""
        mock_get_news_data.return_value = []

        result = get_bulk_news_google(24)

        assert isinstance(result, list)

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_bulk_news_google_multiple_queries(self, mock_get_news_data):
        """Test that multiple search queries are executed."""
        mock_get_news_data.return_value = []

        result = get_bulk_news_google(24)

        # Should call getNewsData multiple times for different queries
        assert mock_get_news_data.call_count >= 3

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_bulk_news_google_with_articles(self, mock_get_news_data):
        """Test article parsing and deduplication."""
        mock_articles = [
            {
                "title": "Market update",
                "source": "Financial Times",
                "snippet": "Markets closed higher today...",
                "link": "https://example.com/1",
                "date": "2024-01-15",
            },
            {
                "title": "Trading news",
                "source": "WSJ",
                "snippet": "Trading volume increased...",
                "link": "https://example.com/2",
                "date": "2024-01-15",
            },
        ]

        mock_get_news_data.return_value = mock_articles

        result = get_bulk_news_google(24)

        assert len(result) > 0
        assert all("title" in article for article in result)
        assert all("source" in article for article in result)

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_bulk_news_google_deduplication(self, mock_get_news_data):
        """Test that duplicate articles are removed."""
        duplicate_article = {
            "title": "Same article",
            "source": "Source",
            "snippet": "Content",
            "link": "https://example.com",
            "date": "2024-01-15",
        }

        # Return same article multiple times
        mock_get_news_data.return_value = [duplicate_article, duplicate_article]

        result = get_bulk_news_google(24)

        # Should only appear once
        titles = [article["title"] for article in result]
        assert titles.count("Same article") <= 1

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_bulk_news_google_content_truncation(self, mock_get_news_data):
        """Test that content snippets are truncated to 500 characters."""
        long_snippet = "A" * 1000

        mock_articles = [
            {
                "title": "Article",
                "source": "Source",
                "snippet": long_snippet,
                "link": "https://example.com",
                "date": "2024-01-15",
            }
        ]

        mock_get_news_data.return_value = mock_articles

        result = get_bulk_news_google(24)

        if len(result) > 0:
            assert len(result[0]["content_snippet"]) <= 500

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_bulk_news_google_error_handling(self, mock_get_news_data):
        """Test error handling when getNewsData raises exception."""
        mock_get_news_data.side_effect = TypeError("API Error")

        result = get_bulk_news_google(24)

        assert isinstance(result, list)
        assert len(result) == 0

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_bulk_news_google_lookback_periods(self, mock_get_news_data):
        """Test with various lookback periods."""
        mock_get_news_data.return_value = []

        lookback_hours = [1, 6, 12, 24, 48, 168]

        for hours in lookback_hours:
            result = get_bulk_news_google(hours)
            assert isinstance(result, list)

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_bulk_news_google_date_formatting(self, mock_get_news_data):
        """Test that dates are formatted correctly for API."""
        mock_get_news_data.return_value = []

        result = get_bulk_news_google(24)

        # Check that dates in YYYY-MM-DD format are used
        for call in mock_get_news_data.call_args_list:
            start_date = call[0][1]
            end_date = call[0][2]

            # Both should be in YYYY-MM-DD format
            assert len(start_date) == 10
            assert len(end_date) == 10
            assert start_date.count("-") == 2
            assert end_date.count("-") == 2

    @patch("tradingagents.dataflows.google.getNewsData")
    def test_get_bulk_news_google_missing_fields(self, mock_get_news_data):
        """Test handling of articles with missing fields."""
        incomplete_articles = [
            {"title": "Title only"},
            {"source": "Source only"},
            {
                "title": "Complete",
                "source": "Source",
                "snippet": "Text",
                "link": "url",
                "date": "2024-01-15",
            },
        ]

        mock_get_news_data.return_value = incomplete_articles

        result = get_bulk_news_google(24)

        # Should handle missing fields gracefully
        assert isinstance(result, list)
