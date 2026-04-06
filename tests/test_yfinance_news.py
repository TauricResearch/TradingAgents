import unittest
from unittest.mock import patch

from tradingagents.dataflows.yfinance_news import get_news_yfinance


def _article(date_value: str, title: str, link: str) -> dict:
    return {
        "content": {
            "title": title,
            "summary": f"Summary for {title}",
            "provider": {"displayName": "Unit Test"},
            "canonicalUrl": {"url": link},
            "pubDate": f"{date_value}T12:00:00Z",
        }
    }


class _FakeTicker:
    def __init__(self, full_news: list[dict]):
        self.full_news = list(full_news)

    def get_news(self, count=20):
        return self.full_news[:count]


class YFinanceNewsTests(unittest.TestCase):
    def test_get_news_yfinance_expands_feed_depth_to_cover_requested_window(self):
        recent_articles = [
            _article(f"2026-04-{day:02d}", f"Recent article {day}", f"https://example.com/recent-{day}")
            for day in range(6, 2, -1)
            for _ in range(15)
        ]
        older_articles = [
            _article("2026-04-02", "Alphabet April 2 article", "https://example.com/apr2"),
            _article("2026-04-01", "Alphabet April 1 article", "https://example.com/apr1"),
        ]
        fake_ticker = _FakeTicker(recent_articles + older_articles)

        with (
            patch("tradingagents.dataflows.yfinance_news.yf.Ticker", return_value=fake_ticker),
            patch("tradingagents.dataflows.yfinance_news.yf_retry", side_effect=lambda fn: fn()),
        ):
            result = get_news_yfinance("GOOGL", "2026-03-26", "2026-04-02")

        self.assertIn("Alphabet April 2 article", result)
        self.assertIn("[2026-04-02]", result)

    def test_get_news_yfinance_reports_feed_coverage_when_window_is_unavailable(self):
        fake_ticker = _FakeTicker(
            [
                _article("2026-04-06", "Fresh article", "https://example.com/fresh"),
                _article("2026-04-05", "Fresh article 2", "https://example.com/fresh-2"),
            ]
        )

        with (
            patch("tradingagents.dataflows.yfinance_news.yf.Ticker", return_value=fake_ticker),
            patch("tradingagents.dataflows.yfinance_news.yf_retry", side_effect=lambda fn: fn()),
        ):
            result = get_news_yfinance("GOOGL", "2026-03-26", "2026-04-02")

        self.assertIn("No news found for GOOGL between 2026-03-26 and 2026-04-02", result)
        self.assertIn("2026-04-05 to 2026-04-06", result)


if __name__ == "__main__":
    unittest.main()
