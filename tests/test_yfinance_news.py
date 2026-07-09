import copy
from datetime import datetime, timezone
from types import SimpleNamespace

import tradingagents.default_config as default_config
from tradingagents.dataflows import yfinance_news
from tradingagents.dataflows.config import set_config

# Epoch (UTC) inside the test's [2026-01-24, 2026-02-01] lookback window, so
# flat-structured fake articles survive the look-ahead-safe date filter (#1007).
_PUB_TS = int(datetime(2026, 1, 28, 12, tzinfo=timezone.utc).timestamp())


def test_get_news_yfinance_uses_default_article_limit(monkeypatch):
    captured = {}

    class FakeTicker:
        def __init__(self, ticker):
            captured["ticker"] = ticker

        def get_news(self, count):
            captured["count"] = count
            return [
                {
                    "content": {
                        "title": "Apple earnings preview",
                        "summary": "Analysts are watching revenue guidance.",
                        "provider": {"displayName": "Yahoo Finance"},
                        "canonicalUrl": {"url": "https://example.com/aapl"},
                        "pubDate": "2026-01-15T12:00:00Z",
                    }
                }
            ]

    set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))
    monkeypatch.setattr(yfinance_news.yf, "Ticker", FakeTicker)

    result = yfinance_news.get_news_yfinance("AAPL", "2026-01-01", "2026-01-31")

    assert captured["ticker"] == "AAPL"
    assert captured["count"] == default_config.DEFAULT_CONFIG["news_article_limit"]
    assert "Apple earnings preview" in result
    assert "Yahoo Finance" in result


def test_get_global_news_yfinance_uses_default_queries_and_limits(monkeypatch):
    captured = []

    def fake_search(query, news_count, enable_fuzzy_query):
        captured.append(
            {
                "query": query,
                "news_count": news_count,
                "enable_fuzzy_query": enable_fuzzy_query,
            }
        )
        return SimpleNamespace(
            news=[
                {
                    "title": f"{query} update",
                    "publisher": "Yahoo Finance",
                    "link": f"https://example.com/{len(captured)}",
                    "providerPublishTime": _PUB_TS,
                }
            ]
        )

    set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))
    monkeypatch.setattr(yfinance_news.yf, "Search", fake_search)

    result = yfinance_news.get_global_news_yfinance("2026-01-31")

    assert captured
    assert captured[0]["query"] == default_config.DEFAULT_CONFIG["global_news_queries"][0]
    assert captured[0]["news_count"] == default_config.DEFAULT_CONFIG["global_news_article_limit"]
    assert captured[0]["enable_fuzzy_query"] is True
    assert "Global Market News" in result
    assert "Yahoo Finance" in result
