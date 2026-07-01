"""Exa search vendor: configuration errors, output formatting, and router
integration.

All API access is mocked, so these run without a network connection or a key.
"""
import copy
import unittest
from unittest import mock

import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import exa_search, interface
from tradingagents.dataflows.config import set_config

_RESULTS = [
    {
        "title": "Company Beats Earnings Expectations",
        "author": "Reuters",
        "publishedDate": "2026-06-15T12:00:00.000Z",
        "summary": "The company reported strong quarterly results.",
        "url": "https://example.com/article1",
    },
    {
        "title": "Analysts Raise Price Target",
        "url": "https://finance.example.com/article2",
        "text": "Several analysts increased their price targets.",
    },
]


@pytest.mark.unit
class ExaConfigTests(unittest.TestCase):
    def test_missing_key_raises_not_configured(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
                self.assertRaises(exa_search.ExaNotConfiguredError):
            exa_search.get_api_key()

    def test_not_configured_is_a_value_error(self):
        # Routing relies on this subclassing for "vendor unavailable" handling.
        self.assertTrue(issubclass(exa_search.ExaNotConfiguredError, ValueError))


@pytest.mark.unit
class ExaFormattingTests(unittest.TestCase):
    def test_get_news_formats_results(self):
        with mock.patch.object(exa_search, "_search", return_value=_RESULTS):
            out = exa_search.get_news_exa("AAPL", "2026-06-01", "2026-06-15")
        self.assertIn("## AAPL News, from 2026-06-01 to 2026-06-15", out)
        self.assertIn("Company Beats Earnings Expectations", out)
        self.assertIn("source: Reuters", out)
        self.assertIn("Link: https://example.com/article1", out)
        # falls back to the URL's host when no author is present
        self.assertIn("source: finance.example.com", out)
        self.assertIn("Several analysts increased their price targets.", out)

    def test_get_news_no_results(self):
        with mock.patch.object(exa_search, "_search", return_value=[]):
            out = exa_search.get_news_exa("AAPL", "2026-06-01", "2026-06-15")
        self.assertIn("No news found for AAPL", out)

    def test_get_global_news_formats_results(self):
        with mock.patch.object(exa_search, "_search", return_value=_RESULTS):
            out = exa_search.get_global_news_exa("2026-06-15", 7, 10)
        self.assertIn("## Global Market News, from 2026-06-08 to 2026-06-15", out)
        self.assertIn("Company Beats Earnings Expectations", out)

    def test_get_global_news_no_results(self):
        with mock.patch.object(exa_search, "_search", return_value=[]):
            out = exa_search.get_global_news_exa("2026-06-15")
        self.assertIn("No global news found", out)

    def test_get_global_news_respects_limit(self):
        many_results = _RESULTS * 5  # 10 results
        with mock.patch.object(exa_search, "_search", return_value=many_results):
            out = exa_search.get_global_news_exa("2026-06-15", 7, 1)
        self.assertEqual(out.count("### "), 1)


@pytest.mark.unit
class ExaRoutingTests(unittest.TestCase):
    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def test_news_data_category_routes_to_exa(self):
        self.assertEqual(interface.get_category_for_method("get_news"), "news_data")
        set_config({"data_vendors": {"news_data": "exa"}})
        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_news": {"exa": lambda *a, **k: "NEWS_OK"}},
            clear=False,
        ):
            out = interface.route_to_vendor("get_news", "AAPL", "2026-06-01", "2026-06-15")
        self.assertEqual(out, "NEWS_OK")

    def test_not_configured_falls_back_to_next_vendor(self):
        set_config({"data_vendors": {"news_data": "exa,yfinance"}})

        def _unconfigured(*a, **k):
            raise exa_search.ExaNotConfiguredError("EXA_API_KEY not set")

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_news": {"exa": _unconfigured, "yfinance": lambda *a, **k: "FALLBACK_OK"}},
            clear=False,
        ):
            out = interface.route_to_vendor("get_news", "AAPL", "2026-06-01", "2026-06-15")
        self.assertEqual(out, "FALLBACK_OK")


if __name__ == "__main__":
    unittest.main()
