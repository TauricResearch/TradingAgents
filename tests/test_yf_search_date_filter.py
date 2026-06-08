"""Regression tests for yfinance flat-format article date filtering.

yf.Search() currently returns articles exclusively in flat format, where
the publish timestamp is stored as a Unix integer in ``providerPublishTime``.
The previous code returned ``pub_date=None`` for flat articles, causing
get_global_news_yfinance() to bypass all date filtering and inject
future-dated news into historical backtest runs.

These tests verify:
1. _extract_article_data() correctly parses providerPublishTime for flat articles.
2. get_global_news_yfinance() filters out articles outside the date window,
   regardless of whether the article is nested or flat format.
"""

import pytest
from datetime import datetime, timezone
from unittest import mock

from tradingagents.dataflows.yfinance_news import (
    _extract_article_data,
    get_global_news_yfinance,
)
from tradingagents.dataflows.config import set_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flat_article(title: str, pub_ts: int) -> dict:
    """Minimal flat-format article as returned by yf.Search()."""
    return {
        "title": title,
        "publisher": "Test Publisher",
        "link": "https://example.com/article",
        "providerPublishTime": pub_ts,
        "type": "STORY",
    }


def _nested_article(title: str, pub_iso: str) -> dict:
    """Minimal nested-format article (older yfinance versions)."""
    return {
        "content": {
            "title": title,
            "summary": "Summary text.",
            "provider": {"displayName": "Test Publisher"},
            "canonicalUrl": {"url": "https://example.com/article"},
            "pubDate": pub_iso,
        }
    }


def _ts(dt: datetime) -> int:
    """Convert a naive UTC datetime to a Unix timestamp integer."""
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


# ---------------------------------------------------------------------------
# Unit tests — no network required
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExtractArticleData:
    def test_flat_article_pub_date_parsed(self):
        """Flat articles expose pub_date when providerPublishTime is present."""
        ts = _ts(datetime(2026, 4, 10, 15, 33, 30))
        article = _flat_article("Test headline", ts)
        data = _extract_article_data(article)

        assert data["pub_date"] is not None
        assert data["pub_date"].year == 2026
        assert data["pub_date"].month == 4
        assert data["pub_date"].day == 10
        assert data["title"] == "Test headline"

    def test_flat_article_missing_timestamp_returns_none(self):
        """Flat articles without providerPublishTime return pub_date=None."""
        article = {"title": "No timestamp", "publisher": "X", "link": ""}
        data = _extract_article_data(article)
        assert data["pub_date"] is None

    def test_nested_article_pub_date_parsed(self):
        """Nested articles continue to have pub_date parsed from pubDate."""
        article = _nested_article("Nested headline", "2026-04-10T15:33:30Z")
        data = _extract_article_data(article)
        assert data["pub_date"] is not None
        assert data["pub_date"].year == 2026

    def test_nested_article_missing_pub_date_returns_none(self):
        """Nested articles without pubDate return pub_date=None."""
        article = {"content": {"title": "No date", "provider": {}}}
        data = _extract_article_data(article)
        assert data["pub_date"] is None


# ---------------------------------------------------------------------------
# Integration-style tests using mocked yf.Search — no real network calls
# ---------------------------------------------------------------------------

def _make_search_mock(articles: list):
    """Return a mock that makes yf.Search(...).news return ``articles``."""
    search_instance = mock.MagicMock()
    search_instance.news = articles

    search_cls = mock.MagicMock(return_value=search_instance)
    return search_cls


@pytest.mark.unit
class TestGlobalNewsDateFilter:
    """get_global_news_yfinance must filter articles by date regardless of format."""

    def setup_method(self):
        # Use a minimal config so get_config() doesn't fail.
        set_config({
            "global_news_lookback_days": 7,
            "global_news_article_limit": 10,
            "global_news_queries": ["test query"],
        })

    def test_flat_future_article_filtered_for_historical_date(self):
        """A flat article dated 2026 must not appear when curr_date=2022-01-19."""
        future_ts = _ts(datetime(2026, 4, 10, 15, 0, 0))
        articles = [_flat_article("Future news headline", future_ts)]

        with mock.patch(
            "tradingagents.dataflows.yfinance_news.yf.Search",
            _make_search_mock(articles),
        ):
            result = get_global_news_yfinance("2022-01-19")

        assert "Future news headline" not in result

    def test_flat_article_within_window_passes_for_today(self):
        """A flat article from today's window must appear when curr_date matches."""
        # Use a timestamp squarely inside the 7-day window of 2026-06-08
        in_window_ts = _ts(datetime(2026, 6, 5, 10, 0, 0))
        articles = [_flat_article("Recent market news", in_window_ts)]

        with mock.patch(
            "tradingagents.dataflows.yfinance_news.yf.Search",
            _make_search_mock(articles),
        ):
            result = get_global_news_yfinance("2026-06-08")

        assert "Recent market news" in result

    def test_nested_future_article_filtered_for_historical_date(self):
        """A nested article dated 2026 must not appear when curr_date=2022-01-19."""
        articles = [_nested_article("Nested future news", "2026-04-10T15:00:00Z")]

        with mock.patch(
            "tradingagents.dataflows.yfinance_news.yf.Search",
            _make_search_mock(articles),
        ):
            result = get_global_news_yfinance("2022-01-19")

        assert "Nested future news" not in result

    def test_flat_article_too_old_filtered(self):
        """A flat article older than the lookback window must be excluded."""
        # 30 days before curr_date, well outside the 7-day window
        old_ts = _ts(datetime(2026, 5, 9, 10, 0, 0))
        articles = [_flat_article("Old news headline", old_ts)]

        with mock.patch(
            "tradingagents.dataflows.yfinance_news.yf.Search",
            _make_search_mock(articles),
        ):
            result = get_global_news_yfinance("2026-06-08")

        assert "Old news headline" not in result

    def test_all_filtered_returns_no_news_message(self):
        """When all articles are outside the date window the function says so."""
        future_ts = _ts(datetime(2026, 4, 10, 15, 0, 0))
        articles = [_flat_article("Future article", future_ts)]

        with mock.patch(
            "tradingagents.dataflows.yfinance_news.yf.Search",
            _make_search_mock(articles),
        ):
            result = get_global_news_yfinance("2022-01-19")

        # Should return the header line but no article sections
        assert "###" not in result
