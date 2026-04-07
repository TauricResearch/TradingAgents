import unittest
from unittest.mock import patch

from tradingagents.dataflows.yfinance_news import get_social_sentiment_yfinance


class SocialSentimentTests(unittest.TestCase):
    @patch("tradingagents.dataflows.yfinance_news.fetch_company_news_yfinance", return_value=([], None, None))
    def test_social_sentiment_reports_news_derived_fallback_when_empty(self, _mock_fetch):
        result = get_social_sentiment_yfinance("AAPL", "2026-04-01", "2026-04-02")
        self.assertIn("Dedicated social provider unavailable", result)
        self.assertIn("news-derived sentiment", result)


if __name__ == "__main__":
    unittest.main()
