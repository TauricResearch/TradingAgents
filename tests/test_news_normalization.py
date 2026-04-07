import unittest

from tradingagents.dataflows.alpha_vantage_news import normalize_alpha_vantage_article
from tradingagents.dataflows.yfinance_news import normalize_yfinance_article


class NewsNormalizationTests(unittest.TestCase):
    def test_yfinance_article_normalizes_to_news_item(self):
        article = {
            "content": {
                "title": "Samsung wins order",
                "summary": "Large customer order announced.",
                "provider": {"displayName": "Unit Test"},
                "canonicalUrl": {"url": "https://example.com/article"},
                "pubDate": "2026-04-08T09:00:00Z",
                "relatedTickers": ["005930.KS"],
            }
        }

        item = normalize_yfinance_article(article, fallback_symbol="005930.KS")

        self.assertEqual(item.raw_vendor, "yfinance")
        self.assertEqual(item.title, "Samsung wins order")
        self.assertIn("005930.KS", item.symbols)

    def test_alpha_vantage_article_normalizes_to_news_item(self):
        article = {
            "title": "Apple demand improves",
            "summary": "Demand commentary improved after launch.",
            "source": "Alpha Source",
            "url": "https://example.com/alpha",
            "time_published": "20260408T090000",
            "ticker_sentiment": [{"ticker": "AAPL"}],
            "topics": [{"topic": "earnings"}],
            "overall_sentiment_score": "0.25",
        }

        item = normalize_alpha_vantage_article(article, fallback_symbol="AAPL")

        self.assertEqual(item.raw_vendor, "alpha_vantage")
        self.assertEqual(item.title, "Apple demand improves")
        self.assertEqual(item.sentiment, 0.25)
        self.assertIn("AAPL", item.symbols)


if __name__ == "__main__":
    unittest.main()
