"""AnySearch global-news vendor: live-only, look-ahead-safe.

Because AnySearch results carry no publish date, the vendor must refuse
historical (backtest) dates so the router falls back to a date-filtering
vendor, and only serve live windows. These tests pin that guardrail plus the
error-classification and formatting behavior, all with a mocked HTTP layer
(no live network).
"""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
import requests as _rq

from tradingagents.dataflows import anysearch
from tradingagents.dataflows.errors import NoMarketDataError, VendorRateLimitError


def _resp(status=200, code=0, results=None, message="success"):
    m = mock.Mock()
    m.status_code = status
    m.json.return_value = {
        "code": code,
        "message": message,
        "data": {"results": results if results is not None else []},
    }
    return m


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _old_str() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%Y-%m-%d")


_CFG = {
    "global_news_lookback_days": 7,
    "global_news_article_limit": 10,
    "global_news_queries": ["macro news", "fed policy"],
}


@pytest.mark.unit
class AnySearchGlobalNewsTests(unittest.TestCase):
    def setUp(self):
        self._cfg_patch = mock.patch.object(anysearch, "get_config", return_value=_CFG)
        self._cfg_patch.start()

    def tearDown(self):
        self._cfg_patch.stop()

    def test_historical_date_raises_no_market_data(self):
        # Look-ahead guard: a clearly historical date must be refused (no reliable
        # publish date -> would leak future news into a backtest).
        with self.assertRaises(NoMarketDataError) as ctx:
            anysearch.get_anysearch_global_news(_old_str())
        self.assertIn("live-only", str(ctx.exception).lower())

    def test_live_date_returns_formatted_news(self):
        results = [
            {"title": "Fed holds rates", "snippet": "The Fed paused.", "url": "https://x/1"},
            {"title": "Jobs report", "snippet": "NFP beat.", "url": "https://x/2"},
        ]
        with mock.patch.object(anysearch.requests, "post", return_value=_resp(results=results)):
            out = anysearch.get_anysearch_global_news(_today_str())
        self.assertIn("Fed holds rates", out)
        self.assertIn("AnySearch", out)
        self.assertIn("live snapshot", out.lower())

    def test_duplicate_urls_deduplicated(self):
        dup = [
            {"title": "A", "snippet": "s", "url": "https://x/1"},
            {"title": "A again", "snippet": "s", "url": "https://x/1"},
        ]
        with mock.patch.object(anysearch.requests, "post", return_value=_resp(results=dup)):
            out = anysearch.get_anysearch_global_news(_today_str())
        # The second (duplicate URL) item must be dropped.
        self.assertEqual(out.count("https://x/1"), 1)

    def test_429_raises_rate_limit(self):
        with mock.patch.object(anysearch.requests, "post", return_value=_resp(status=429)), \
                self.assertRaises(VendorRateLimitError):
            anysearch.get_anysearch_global_news(_today_str())

    def test_non_200_raises_no_market_data(self):
        with mock.patch.object(anysearch.requests, "post", return_value=_resp(status=503)), \
                self.assertRaises(NoMarketDataError):
            anysearch.get_anysearch_global_news(_today_str())

    def test_api_error_code_raises_no_market_data(self):
        with mock.patch.object(
            anysearch.requests, "post",
            return_value=_resp(code=-1, message="Internal server error."),
        ), self.assertRaises(NoMarketDataError):
            anysearch.get_anysearch_global_news(_today_str())

    def test_empty_results_raise_no_market_data(self):
        with mock.patch.object(anysearch.requests, "post", return_value=_resp(results=[])), \
                self.assertRaises(NoMarketDataError):
            anysearch.get_anysearch_global_news(_today_str())

    def test_network_error_raises_no_market_data(self):
        with mock.patch.object(
            anysearch.requests, "post",
            side_effect=_rq.RequestException("boom"),
        ), self.assertRaises(NoMarketDataError):
            anysearch.get_anysearch_global_news(_today_str())

    def test_api_key_sets_bearer_header(self):
        captured = {}

        def _capture(url, json, headers, timeout):
            captured["headers"] = headers
            return _resp(results=[{"title": "T", "snippet": "s", "url": "https://x/9"}])

        with mock.patch.dict("os.environ", {"ANYSEARCH_API_KEY": "as_sk_test"}), \
                mock.patch.object(anysearch.requests, "post", side_effect=_capture):
            anysearch.get_anysearch_global_news(_today_str())
        self.assertEqual(captured["headers"].get("Authorization"), "Bearer as_sk_test")

    def test_no_api_key_omits_bearer_header(self):
        captured = {}

        def _capture(url, json, headers, timeout):
            captured["headers"] = headers
            return _resp(results=[{"title": "T", "snippet": "s", "url": "https://x/9"}])

        with mock.patch.dict("os.environ", {}, clear=False), \
                mock.patch.object(anysearch.requests, "post", side_effect=_capture):
            os.environ.pop("ANYSEARCH_API_KEY", None)
            anysearch.get_anysearch_global_news(_today_str())
        self.assertNotIn("Authorization", captured["headers"])


if __name__ == "__main__":
    unittest.main()
