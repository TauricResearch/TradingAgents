"""Firecrawl news vendor: date-window pinning, response formatting, snippet
hygiene, error classification, deduplication, and router integration.

All API access is mocked, so these run without a network connection or a key.
"""
import copy
import unittest
from unittest import mock

import pytest
import requests

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import firecrawl_news, interface
from tradingagents.dataflows.config import set_config

_ARTICLES = [
    {
        "title": "Chipmaker beats estimates",
        "url": "https://www.reuters.com/markets/chip-beat",
        "snippet": "Revenue rose 12% on datacenter demand.",
        "date": "2 days ago",
    },
    {
        "title": "Analysts lift price target",
        "url": "https://seekingalpha.com/news/4612631",
        "snippet": "Two desks raised targets after the print.",
        "date": "1 day ago",
    },
]


class _Response:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def _ok(articles=_ARTICLES):
    return _Response({"success": True, "data": {"news": list(articles)}})


@pytest.mark.unit
class FirecrawlQueryTests(unittest.TestCase):
    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def test_date_range_uses_us_style_unpadded_bounds(self):
        # The engine's cdr filter wants M/D/YYYY; zero-padding is not accepted
        # and the strftime directive for it is platform-specific.
        self.assertEqual(
            firecrawl_news._date_range_tbs("2026-01-05", "2026-11-30"),
            "cdr:1,cd_min:1/5/2026,cd_max:11/30/2026",
        )

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_window_is_pinned_server_side(self):
        # Look-ahead safety: the requested window is sent as the search filter,
        # so the API cannot return an article published after end_date.
        with mock.patch.object(firecrawl_news.requests, "post", return_value=_ok()) as post:
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["tbs"], "cdr:1,cd_min:3/1/2026,cd_max:3/8/2026")
        self.assertEqual(payload["sources"], [{"type": "news"}])
        self.assertIn("NVDA", payload["query"])
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key"
        )

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_article_limit_comes_from_config(self):
        set_config({"news_article_limit": 3})
        with mock.patch.object(firecrawl_news.requests, "post", return_value=_ok()) as post:
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")
        self.assertEqual(post.call_args.kwargs["json"]["limit"], 3)


@pytest.mark.unit
class FirecrawlFormattingTests(unittest.TestCase):
    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_report_matches_the_other_news_vendors(self):
        with mock.patch.object(firecrawl_news.requests, "post", return_value=_ok()):
            out = firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")

        self.assertTrue(out.startswith("## NVDA News, from 2026-03-01 to 2026-03-08\n"))
        self.assertIn("### Chipmaker beats estimates (source: reuters.com)", out)
        self.assertIn("Revenue rose 12% on datacenter demand.", out)
        self.assertIn("Link: https://www.reuters.com/markets/chip-beat", out)

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_article_age_is_not_rendered(self):
        # Recent results carry an age relative to *now*, not to the analysis
        # date, so rendering it would misdate every article in a historical run.
        with mock.patch.object(firecrawl_news.requests, "post", return_value=_ok()):
            out = firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")
        self.assertNotIn("days ago", out)

    def test_snippet_images_are_dropped_and_length_capped(self):
        cleaned = firecrawl_news._clean_snippet(
            "Before ![alt](data:image/gif;base64,R0lGODlh) after\n\nmore   text"
        )
        self.assertEqual(cleaned, "Before after more text")

        long_snippet = "word " * 400
        capped = firecrawl_news._clean_snippet(long_snippet)
        self.assertLessEqual(len(capped), firecrawl_news.MAX_SNIPPET_CHARS + 3)
        self.assertTrue(capped.endswith("..."))

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_empty_result_says_so_instead_of_an_empty_body(self):
        with mock.patch.object(
            firecrawl_news.requests, "post", return_value=_Response({"data": {"news": []}})
        ):
            out = firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")
        self.assertEqual(out, "No news found for NVDA between 2026-03-01 and 2026-03-08")

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_global_news_dedupes_across_queries(self):
        # The macro queries overlap; the same story must not be listed twice.
        set_config({
            "global_news_queries": ["fed rates", "inflation outlook"],
            "global_news_article_limit": 10,
        })
        with mock.patch.object(firecrawl_news.requests, "post", return_value=_ok()):
            out = firecrawl_news.get_global_news_firecrawl("2026-03-08")

        self.assertEqual(out.count("### Chipmaker beats estimates"), 1)
        self.assertIn("## Global Market News, from 2026-03-01 to 2026-03-08", out)


@pytest.mark.unit
class FirecrawlErrorTests(unittest.TestCase):
    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": ""})
    def test_missing_key_raises_not_configured(self):
        with self.assertRaises(firecrawl_news.FirecrawlNotConfiguredError):
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_rate_limit_is_classified(self):
        with mock.patch.object(
            firecrawl_news.requests, "post",
            return_value=_Response(status_code=429, text="too many requests"),
        ), self.assertRaises(firecrawl_news.FirecrawlRateLimitError):
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_rejected_key_is_not_confused_with_an_outage(self):
        # A bad key must read as "vendor unavailable" (skip to the next vendor);
        # a 5xx must stay a hard error so a broken primary is loud.
        with mock.patch.object(
            firecrawl_news.requests, "post",
            return_value=_Response(status_code=401, text="unauthorized"),
        ), self.assertRaises(firecrawl_news.FirecrawlNotConfiguredError):
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")

        with mock.patch.object(
            firecrawl_news.requests, "post",
            return_value=_Response(status_code=503, text="upstream down"),
        ), self.assertRaises(requests.HTTPError):
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")


@pytest.mark.unit
class FirecrawlRoutingTests(unittest.TestCase):
    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def test_registered_for_both_news_methods(self):
        self.assertIn("firecrawl", interface.VENDOR_LIST)
        self.assertIs(
            interface.VENDOR_METHODS["get_news"]["firecrawl"],
            firecrawl_news.get_news_firecrawl,
        )
        self.assertIs(
            interface.VENDOR_METHODS["get_global_news"]["firecrawl"],
            firecrawl_news.get_global_news_firecrawl,
        )

    def test_chained_behind_yfinance_it_serves_the_fallback(self):
        # The documented setup: Firecrawl picks up tickers the default covers thinly.
        set_config({"tool_vendors": {"get_news": "yfinance,firecrawl"}})

        def _no_news(*a, **k):
            raise requests.ConnectionError("yahoo down")

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_news": {
                "yfinance": _no_news,
                "firecrawl": lambda *a, **k: "FIRECRAWL_NEWS",
            }},
            clear=False,
        ):
            out = interface.route_to_vendor("get_news", "AAPL", "2026-03-01", "2026-03-08")
        self.assertEqual(out, "FIRECRAWL_NEWS")

    def test_missing_key_falls_through_to_the_next_vendor(self):
        set_config({"tool_vendors": {"get_news": "firecrawl,yfinance"}})

        def _unconfigured(*a, **k):
            raise firecrawl_news.FirecrawlNotConfiguredError("FIRECRAWL_API_KEY not set")

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_news": {
                "firecrawl": _unconfigured,
                "yfinance": lambda *a, **k: "YF_NEWS",
            }},
            clear=False,
        ):
            out = interface.route_to_vendor("get_news", "AAPL", "2026-03-01", "2026-03-08")
        self.assertEqual(out, "YF_NEWS")


if __name__ == "__main__":
    unittest.main()
