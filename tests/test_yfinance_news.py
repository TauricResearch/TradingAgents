"""Tests for tradingagents.dataflows.yfinance_news."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows.yfinance_news import (
    _extract_article_data,
    get_global_news_yfinance,
    get_news_yfinance,
)


def _mock_config(**overrides):
    base = {
        "news_article_limit": 20,
        "global_news_article_limit": 10,
        "global_news_lookback_days": 7,
        "global_news_queries": ["stock market", "economy"],
    }
    base.update(overrides)
    return base


def _nested_article(
    title="Test Article",
    summary="Test summary",
    publisher="Test Publisher",
    url="https://example.com/article",
    pub_date="2025-06-15T10:00:00Z",
):
    return {
        "content": {
            "title": title,
            "summary": summary,
            "provider": {"displayName": publisher},
            "canonicalUrl": {"url": url},
            "pubDate": pub_date,
        }
    }


def _flat_article(
    title="Flat Article",
    summary="Flat summary",
    publisher="Flat Publisher",
    link="https://example.com/flat",
):
    return {
        "title": title,
        "summary": summary,
        "publisher": publisher,
        "link": link,
    }


@pytest.mark.unit
class ExtractArticleDataTests(unittest.TestCase):
    def test_extract_nested_content_structure(self):
        article = _nested_article()
        result = _extract_article_data(article)
        self.assertEqual(result["title"], "Test Article")
        self.assertEqual(result["summary"], "Test summary")
        self.assertEqual(result["publisher"], "Test Publisher")
        self.assertEqual(result["link"], "https://example.com/article")
        self.assertIsNotNone(result["pub_date"])
        self.assertIsInstance(result["pub_date"], datetime)

    def test_extract_nested_no_title_fallback(self):
        article = {"content": {"summary": "no title"}}
        result = _extract_article_data(article)
        self.assertEqual(result["title"], "No title")
        self.assertEqual(result["summary"], "no title")
        self.assertEqual(result["publisher"], "Unknown")
        self.assertEqual(result["link"], "")

    def test_extract_nested_no_pub_date(self):
        article = {"content": {"title": "No Date"}}
        result = _extract_article_data(article)
        self.assertIsNone(result["pub_date"])

    def test_extract_nested_invalid_pub_date_suppresses_error(self):
        article = {"content": {"title": "Bad Date", "pubDate": "not-a-date"}}
        result = _extract_article_data(article)
        self.assertIsNone(result["pub_date"])

    def test_extract_uses_click_through_url_fallback(self):
        article = {
            "content": {
                "title": "Click",
                "clickThroughUrl": {"url": "https://example.com/click"},
            }
        }
        result = _extract_article_data(article)
        self.assertEqual(result["link"], "https://example.com/click")

    def test_extract_flat_structure(self):
        article = _flat_article()
        result = _extract_article_data(article)
        self.assertEqual(result["title"], "Flat Article")
        self.assertEqual(result["summary"], "Flat summary")
        self.assertEqual(result["publisher"], "Flat Publisher")
        self.assertEqual(result["link"], "https://example.com/flat")
        self.assertIsNone(result["pub_date"])

    def test_extract_flat_structure_missing_fields(self):
        article = {}
        result = _extract_article_data(article)
        self.assertEqual(result["title"], "No title")
        self.assertEqual(result["summary"], "")
        self.assertEqual(result["publisher"], "Unknown")
        self.assertEqual(result["link"], "")
        self.assertIsNone(result["pub_date"])


@pytest.mark.unit
class GetNewsYFinanceTests(unittest.TestCase):
    def setUp(self):
        self.ticker = "AAPL"
        self.start = "2025-06-01"
        self.end = "2025-06-30"
        self.article_limit = 20

    def test_returns_formatted_news(self):
        mock_news = [
            _nested_article(title="Apple News 1", pub_date="2025-06-10T12:00:00Z"),
            _nested_article(title="Apple News 2", pub_date="2025-06-15T12:00:00Z"),
        ]
        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            mock_ticker = MagicMock()
            mock_ticker.get_news.return_value = mock_news
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Ticker",
                return_value=mock_ticker,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_news_yfinance(self.ticker, self.start, self.end)

        self.assertIn("AAPL News, from 2025-06-01 to 2025-06-30", result)
        self.assertIn("Apple News 1", result)
        self.assertIn("Apple News 2", result)
        self.assertIn("Test Publisher", result)

    def test_no_news_returns_message(self):
        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            mock_ticker = MagicMock()
            mock_ticker.get_news.return_value = []
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Ticker",
                return_value=mock_ticker,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_news_yfinance(self.ticker, self.start, self.end)

        self.assertEqual(result, "No news found for AAPL")

    def test_none_news_returns_message(self):
        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            mock_ticker = MagicMock()
            mock_ticker.get_news.return_value = None
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Ticker",
                return_value=mock_ticker,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_news_yfinance(self.ticker, self.start, self.end)

        self.assertEqual(result, "No news found for AAPL")

    def test_filters_articles_outside_date_range(self):
        mock_news = [
            _nested_article(title="Outside Range", pub_date="2025-05-01T12:00:00Z"),
            _nested_article(title="Inside Range", pub_date="2025-06-10T12:00:00Z"),
        ]
        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            mock_ticker = MagicMock()
            mock_ticker.get_news.return_value = mock_news
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Ticker",
                return_value=mock_ticker,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_news_yfinance(self.ticker, self.start, self.end)

        self.assertNotIn("Outside Range", result)
        self.assertIn("Inside Range", result)

    def test_articles_without_date_are_included(self):
        mock_news = [
            _nested_article(title="No Date", pub_date=""),
            {"content": {"title": "No PubDate Field"}},
        ]
        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            mock_ticker = MagicMock()
            mock_ticker.get_news.return_value = mock_news
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Ticker",
                return_value=mock_ticker,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_news_yfinance(self.ticker, self.start, self.end)

        self.assertIn("No Date", result)
        self.assertIn("No PubDate Field", result)

    def test_all_articles_filtered_out_returns_message(self):
        mock_news = [
            _nested_article(title="Old News", pub_date="2025-05-01T12:00:00Z"),
        ]
        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            mock_ticker = MagicMock()
            mock_ticker.get_news.return_value = mock_news
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Ticker",
                return_value=mock_ticker,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_news_yfinance(self.ticker, self.start, self.end)

        self.assertEqual(
            result,
            "No news found for AAPL between 2025-06-01 and 2025-06-30",
        )

    def test_includes_summary_and_link_in_output(self):
        mock_news = [
            _nested_article(
                title="Full Article",
                summary="Detailed content here",
                url="https://example.com/full",
                pub_date="2025-06-10T12:00:00Z",
            ),
        ]
        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            mock_ticker = MagicMock()
            mock_ticker.get_news.return_value = mock_news
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Ticker",
                return_value=mock_ticker,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_news_yfinance(self.ticker, self.start, self.end)

        self.assertIn("Detailed content here", result)
        self.assertIn("https://example.com/full", result)

    def test_exception_returns_error_string(self):
        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            mock_ticker = MagicMock()
            mock_ticker.get_news.side_effect = ConnectionError("network failure")
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Ticker",
                return_value=mock_ticker,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_news_yfinance(self.ticker, self.start, self.end)

        self.assertIn("Error fetching news for AAPL", result)
        self.assertIn("network failure", result)

    def test_passes_article_limit_from_config(self):
        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(news_article_limit=5),
        ):
            mock_ticker = MagicMock()
            mock_ticker.get_news.return_value = []
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Ticker",
                return_value=mock_ticker,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    get_news_yfinance(self.ticker, self.start, self.end)

        mock_ticker.get_news.assert_called_once_with(count=5)

    def test_uses_yf_retry_wrapper(self):
        mock_news = [_nested_article(pub_date="2025-06-10T12:00:00Z")]
        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            mock_ticker = MagicMock()
            mock_ticker.get_news.return_value = mock_news
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Ticker",
                return_value=mock_ticker,
            ):
                retry_mock = MagicMock(side_effect=lambda f: f())
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    retry_mock,
                ):
                    get_news_yfinance(self.ticker, self.start, self.end)

        retry_mock.assert_called_once()
        call_arg = retry_mock.call_args[1].get("count", None)
        if call_arg is None:
            args, _ = retry_mock.call_args
            self.assertTrue(callable(args[0]) if args else False)

    def test_handles_flat_article_structure(self):
        mock_news = [
            _flat_article(
                title="Flat News",
                summary="Flat summary",
                link="https://flat.example.com",
            ),
        ]
        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            mock_ticker = MagicMock()
            mock_ticker.get_news.return_value = mock_news
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Ticker",
                return_value=mock_ticker,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_news_yfinance(self.ticker, self.start, self.end)

        self.assertIn("Flat News", result)
        self.assertIn("Flat summary", result)
        self.assertIn("https://flat.example.com", result)


@pytest.mark.unit
class GetGlobalNewsYFinanceTests(unittest.TestCase):
    def setUp(self):
        self.curr_date = "2025-06-20"

    def test_returns_formatted_global_news(self):
        mock_search_news = [
            _nested_article(
                title="Global News 1",
                summary="Global summary 1",
                publisher="Reuters",
                url="https://reuters.com/article1",
                pub_date="2025-06-18T12:00:00Z",
            ),
        ]
        mock_search = MagicMock()
        mock_search.news = mock_search_news

        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Search",
                return_value=mock_search,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_global_news_yfinance(self.curr_date)

        self.assertIn("Global Market News", result)
        self.assertIn("Global News 1", result)
        self.assertIn("Reuters", result)
        self.assertIn("https://reuters.com/article1", result)

    def test_deduplicates_by_title(self):
        mock_search_news = [
            _nested_article(title="Duplicate Title", pub_date="2025-06-18T12:00:00Z"),
            _nested_article(title="Duplicate Title", pub_date="2025-06-18T12:00:00Z"),
            _nested_article(title="Unique Title", pub_date="2025-06-18T12:00:00Z"),
        ]
        mock_search = MagicMock()
        mock_search.news = mock_search_news

        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Search",
                return_value=mock_search,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_global_news_yfinance(self.curr_date)

        self.assertIn("Duplicate Title", result)
        self.assertIn("Unique Title", result)
        self.assertEqual(result.count("Duplicate Title"), 1)

    def test_skips_articles_without_title(self):
        mock_search_news = [
            {"title": "", "summary": "empty title"},
            _nested_article(title="Real Article", pub_date="2025-06-18T12:00:00Z"),
        ]
        mock_search = MagicMock()
        mock_search.news = mock_search_news

        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Search",
                return_value=mock_search,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_global_news_yfinance(self.curr_date)

        self.assertNotIn("empty title", result)
        self.assertIn("Real Article", result)

    def test_look_ahead_guard_skips_future_articles(self):
        mock_search_news = [
            _nested_article(
                title="Future Article",
                pub_date="2025-06-25T12:00:00Z",
            ),
            _nested_article(
                title="Past Article",
                pub_date="2025-06-15T12:00:00Z",
            ),
        ]
        mock_search = MagicMock()
        mock_search.news = mock_search_news

        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Search",
                return_value=mock_search,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_global_news_yfinance(self.curr_date)

        self.assertNotIn("Future Article", result)
        self.assertIn("Past Article", result)

    def test_handles_flat_article_structure_in_global_news(self):
        mock_search_news = [
            _flat_article(
                title="Flat Global",
                publisher="Bloomberg",
                link="https://bloomberg.com/article",
            ),
        ]
        mock_search = MagicMock()
        mock_search.news = mock_search_news

        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Search",
                return_value=mock_search,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_global_news_yfinance(self.curr_date)

        self.assertIn("Flat Global", result)
        self.assertIn("Bloomberg", result)

    def test_no_news_returns_message(self):
        mock_search = MagicMock()
        mock_search.news = []

        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Search",
                return_value=mock_search,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_global_news_yfinance(self.curr_date)

        self.assertEqual(result, "No global news found for 2025-06-20")

    def test_stops_early_when_limit_reached(self):
        mock_search_news = [
            _nested_article(
                title=f"Article {i}",
                pub_date="2025-06-18T12:00:00Z",
            )
            for i in range(5)
        ]
        mock_search = MagicMock()
        mock_search.news = mock_search_news

        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(global_news_article_limit=3),
        ):
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Search",
                return_value=mock_search,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_global_news_yfinance(self.curr_date)

        self.assertIn("Article 0", result)
        self.assertIn("Article 1", result)
        self.assertIn("Article 2", result)
        self.assertNotIn("Article 3", result)
        self.assertNotIn("Article 4", result)

    def test_exception_returns_error_string(self):
        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Search",
                side_effect=RuntimeError("search failed"),
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_global_news_yfinance(self.curr_date)

        self.assertIn("Error fetching global news", result)
        self.assertIn("search failed", result)

    def test_respects_explicit_limit_and_lookback(self):
        mock_search_news = [
            _nested_article(
                title="Article",
                pub_date="2025-06-18T12:00:00Z",
            ),
        ]
        mock_search = MagicMock()
        mock_search.news = mock_search_news

        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Search",
                return_value=mock_search,
            ):
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    result = get_global_news_yfinance(
                        self.curr_date,
                        look_back_days=30,
                        limit=5,
                    )

        self.assertIn("Global Market News", result)
        self.assertIn("from 2025-05-21 to 2025-06-20", result)

    def test_queries_all_search_queries(self):
        mock_search_news = [
            _nested_article(
                title="Query Result",
                pub_date="2025-06-18T12:00:00Z",
            ),
        ]
        mock_search_obj = MagicMock()
        mock_search_obj.news = mock_search_news

        with patch(
            "tradingagents.dataflows.yfinance_news.get_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tradingagents.dataflows.yfinance_news.yf.Search",
                return_value=mock_search_obj,
            ) as mock_search_patch:
                with patch(
                    "tradingagents.dataflows.yfinance_news.yf_retry",
                    side_effect=lambda f: f(),
                ):
                    get_global_news_yfinance(self.curr_date)

        self.assertEqual(mock_search_patch.call_count, 2)
