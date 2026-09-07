"""Keenable web-search news vendor: request contract (keyless vs keyed),
look-ahead-safe windowing, output formatting, rate-limit / transport handling,
and router integration.

All HTTP access is mocked, so these run without a network connection or a key.
"""
import copy
import unittest
from unittest import mock

import pytest
import requests

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import interface, keenable_news
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import VendorRateLimitError


def _result(title, url, *, published_at=None, acquired_at=None, snippet="", description=""):
    return {
        "title": title,
        "url": url,
        "description": description,
        "snippet": snippet,
        "published_at": published_at,
        "acquired_at": acquired_at,
    }


# A historical window with one in-window article, one syndicated duplicate, one
# dated after the window (must not leak), and one undated (unprovable in a backtest).
_WINDOW = ("2025-05-01", "2025-05-09")
_SEARCH = {
    "query": "NVDA stock news",
    "results": [
        _result(
            "Nvidia beats on data center",
            "https://www.example.com/nvda-beats",
            published_at="2025-05-05T13:00:00Z",
            acquired_at="2025-05-06T01:00:00Z",
            snippet="Nvidia   reported record\n data-center revenue.",
        ),
        _result(  # same story, different host: deduplicated by title
            "Nvidia beats on data center",
            "https://mirror.example.net/amp/nvda-beats",
            published_at="2025-05-05T13:00:00Z",
            snippet="Nvidia reported record data-center revenue.",
        ),
        _result(
            "FUTURE: Nvidia splits stock",
            "https://example.com/future",
            published_at="2025-06-01T09:00:00Z",
            snippet="Should never reach a 2025-05 backtest.",
        ),
        _result(
            "UNDATED page",
            "https://example.com/undated",
            snippet="No timestamps at all.",
        ),
    ],
}


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}
        self.text = text
        self.ok = status_code < 400

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.mark.unit
class KeenableRequestContractTests(unittest.TestCase):
    """The HTTP request itself: endpoint, headers, and window bounds."""

    def test_keyless_by_default_hits_public_endpoint_with_app_title(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
                mock.patch.object(
                    keenable_news.requests, "post", return_value=_FakeResponse(payload=_SEARCH)
                ) as post:
            keenable_news.get_news_keenable("NVDA", *_WINDOW)

        post.assert_called_once()
        url = post.call_args.args[0]
        kwargs = post.call_args.kwargs
        self.assertEqual(url, keenable_news.PUBLIC_SEARCH_URL)
        self.assertEqual(kwargs["headers"]["X-Keenable-Title"], "tradingagents")
        self.assertNotIn("X-API-Key", kwargs["headers"])
        self.assertEqual(kwargs["timeout"], keenable_news.REQUEST_TIMEOUT)

    def test_api_key_switches_to_keyed_endpoint(self):
        with mock.patch.dict("os.environ", {"KEENABLE_API_KEY": "k-123"}, clear=True), \
                mock.patch.object(
                    keenable_news.requests, "post", return_value=_FakeResponse(payload=_SEARCH)
                ) as post:
            keenable_news.get_news_keenable("NVDA", *_WINDOW)

        self.assertEqual(post.call_args.args[0], keenable_news.KEYED_SEARCH_URL)
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["X-API-Key"], "k-123")
        self.assertEqual(headers["X-Keenable-Title"], "tradingagents")  # still sent

    def test_payload_bounds_the_window_and_respects_article_limit(self):
        # Server-side bounds mirror date_window's half-open [start, end + 1 day).
        set_config({"news_article_limit": 7})
        with mock.patch.object(
            keenable_news.requests, "post", return_value=_FakeResponse(payload=_SEARCH)
        ) as post:
            keenable_news.get_news_keenable("NVDA", "2025-05-01", "2025-05-09")

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["query"], "NVDA stock news")
        self.assertEqual(payload["published_after"], "2025-05-01")
        self.assertEqual(payload["published_before"], "2025-05-10")
        self.assertEqual(payload["max_results"], 7)
        self.assertEqual(payload["snippet_max_length"], keenable_news.SNIPPET_MAX_LENGTH)

    def test_article_limit_is_clamped_to_service_cap(self):
        set_config({"news_article_limit": 500})
        with mock.patch.object(
            keenable_news.requests, "post", return_value=_FakeResponse(payload=_SEARCH)
        ) as post:
            keenable_news.get_news_keenable("NVDA", *_WINDOW)
        self.assertEqual(post.call_args.kwargs["json"]["max_results"], keenable_news.MAX_RESULTS)

    def test_crypto_pair_searches_by_base_asset(self):
        self.assertEqual(keenable_news._build_query("BTC-USD"), "BTC crypto news")
        self.assertEqual(keenable_news._build_query("aapl"), "AAPL stock news")


@pytest.mark.unit
class KeenableWindowTests(unittest.TestCase):
    def test_future_and_undated_results_are_excluded_in_backtest(self):
        with mock.patch.object(keenable_news, "_request", return_value=_SEARCH):
            out = keenable_news.get_news_keenable("NVDA", *_WINDOW)
        self.assertIn("Nvidia beats on data center", out)
        self.assertNotIn("FUTURE", out)     # look-ahead blocked
        self.assertNotIn("UNDATED", out)    # unprovable in a historical window

    def test_acquired_at_is_used_when_published_at_missing(self):
        # First-seen time is an upper bound on publication, so it is safe to
        # window on when the service has no publication timestamp.
        data = {
            "results": [
                _result("Seen in window", "https://x.example/a",
                        acquired_at="2025-05-03T00:00:00Z", snippet="s"),
                _result("Seen after window", "https://x.example/b",
                        acquired_at="2025-05-20T00:00:00Z", snippet="s"),
            ]
        }
        with mock.patch.object(keenable_news, "_request", return_value=data):
            out = keenable_news.get_news_keenable("NVDA", *_WINDOW)
        self.assertIn("Seen in window", out)
        self.assertNotIn("Seen after window", out)

    def test_all_filtered_reports_no_news_not_blank_body(self):
        only_future = {"results": [_SEARCH["results"][2]]}
        with mock.patch.object(keenable_news, "_request", return_value=only_future):
            out = keenable_news.get_news_keenable("NVDA", *_WINDOW)
        self.assertEqual(out, "No news found for NVDA between 2025-05-01 and 2025-05-09")

    def test_empty_results_reports_no_news(self):
        with mock.patch.object(keenable_news, "_request", return_value={"results": []}):
            out = keenable_news.get_news_keenable("NVDA", *_WINDOW)
        self.assertIn("No news found for NVDA", out)


@pytest.mark.unit
class KeenableFormattingTests(unittest.TestCase):
    def test_report_matches_yfinance_news_shape(self):
        with mock.patch.object(keenable_news, "_request", return_value=_SEARCH):
            out = keenable_news.get_news_keenable("NVDA", *_WINDOW)
        self.assertTrue(out.startswith("## NVDA News, from 2025-05-01 to 2025-05-09:\n\n"))
        self.assertIn("### Nvidia beats on data center (source: example.com)\n", out)
        self.assertIn("Published: 2025-05-05\n", out)
        # whitespace collapsed
        self.assertIn("Nvidia reported record data-center revenue.\n", out)
        self.assertIn("Link: https://www.example.com/nvda-beats\n", out)

    def test_syndicated_duplicate_kept_once(self):
        with mock.patch.object(keenable_news, "_request", return_value=_SEARCH):
            out = keenable_news.get_news_keenable("NVDA", *_WINDOW)
        self.assertEqual(out.count("### Nvidia beats on data center"), 1)
        self.assertNotIn("mirror.example.net", out)

    def test_snippet_preferred_over_description_with_fallback(self):
        both = _result("t", "https://x.example/1", snippet="PAGE TEXT", description="META")
        only_desc = _result("t", "https://x.example/2", description="META ONLY")
        self.assertEqual(keenable_news._clean_snippet(both), "PAGE TEXT")
        self.assertEqual(keenable_news._clean_snippet(only_desc), "META ONLY")
        self.assertEqual(keenable_news._clean_snippet(_result("t", "u")), "")

    def test_long_snippet_is_capped(self):
        long = _result("t", "u", snippet="x" * (keenable_news.SNIPPET_MAX_LENGTH + 500))
        cleaned = keenable_news._clean_snippet(long)
        self.assertEqual(len(cleaned), keenable_news.SNIPPET_MAX_LENGTH + 1)  # + ellipsis
        self.assertTrue(cleaned.endswith("…"))

    def test_source_is_host_without_www(self):
        self.assertEqual(keenable_news._source("https://www.reuters.com/a/b"), "reuters.com")
        self.assertEqual(keenable_news._source("https://finance.yahoo.com/x"), "finance.yahoo.com")
        self.assertEqual(keenable_news._source(""), "unknown")


@pytest.mark.unit
class KeenableGlobalNewsTests(unittest.TestCase):
    def test_runs_configured_queries_in_window_and_stops_at_limit(self):
        set_config({
            "global_news_queries": ["Fed rates", "oil supply", "never reached"],
            "global_news_lookback_days": 7,
            "global_news_article_limit": 2,
        })
        calls = []

        def _fake(payload):
            calls.append(payload)
            n = len(calls)
            return {"results": [
                _result(f"Macro story {n}", f"https://m.example/{n}",
                        published_at="2025-05-07T08:00:00Z", snippet="macro"),
            ]}

        with mock.patch.object(keenable_news, "_request", side_effect=_fake):
            out = keenable_news.get_global_news_keenable("2025-05-09")

        self.assertEqual([c["query"] for c in calls], ["Fed rates", "oil supply"])
        for c in calls:
            self.assertEqual(c["published_after"], "2025-05-02")   # 7 days back
            self.assertEqual(c["published_before"], "2025-05-10")  # exclusive bound
            self.assertEqual(c["max_results"], 2)
        self.assertTrue(out.startswith("## Global Market News, from 2025-05-02 to 2025-05-09:"))
        self.assertIn("Macro story 1", out)
        self.assertIn("Macro story 2", out)

    def test_explicit_args_override_config(self):
        set_config({"global_news_queries": ["q"]})
        with mock.patch.object(keenable_news, "_request", return_value={"results": []}) as req:
            out = keenable_news.get_global_news_keenable("2025-05-09", look_back_days=3, limit=4)
        payload = req.call_args.args[0]
        self.assertEqual(payload["published_after"], "2025-05-06")
        self.assertEqual(payload["max_results"], 4)
        self.assertEqual(out, "No global news found between 2025-05-06 and 2025-05-09")

    def test_future_article_excluded_from_global_news(self):
        set_config({"global_news_queries": ["q"]})
        with mock.patch.object(keenable_news, "_request", return_value=_SEARCH):
            out = keenable_news.get_global_news_keenable("2025-05-09", look_back_days=8)
        self.assertIn("Nvidia beats on data center", out)
        self.assertNotIn("FUTURE", out)


@pytest.mark.unit
class KeenableResilienceTests(unittest.TestCase):
    def test_429_raises_rate_limit_error_not_empty_success(self):
        throttled = _FakeResponse(
            status_code=429,
            payload={"error": "Rate limit exceeded", "retryAfter": 12},
            headers={"Retry-After": "12"},
        )
        with mock.patch.object(keenable_news.requests, "post", return_value=throttled), \
                self.assertRaises(keenable_news.KeenableRateLimitError) as ctx:
            keenable_news.get_news_keenable("NVDA", *_WINDOW)
        self.assertIn("12", str(ctx.exception))
        # Routing relies on this subclassing to skip to the next vendor.
        self.assertTrue(issubclass(keenable_news.KeenableRateLimitError, VendorRateLimitError))

    def test_http_error_surfaces_service_message(self):
        bad = _FakeResponse(
            status_code=400,
            payload={"error": "Bad request", "message": "Missing X-Keenable-Title header"},
        )
        with mock.patch.object(keenable_news.requests, "post", return_value=bad):
            out = keenable_news.get_news_keenable("NVDA", *_WINDOW)
        self.assertIn("Error fetching news for NVDA", out)
        self.assertIn("400", out)
        self.assertIn("Missing X-Keenable-Title header", out)

    def test_network_error_degrades_to_explicit_message(self):
        with mock.patch.object(
            keenable_news.requests, "post", side_effect=requests.ConnectionError("boom")
        ):
            out = keenable_news.get_news_keenable("NVDA", *_WINDOW)
        self.assertIn("Error fetching news for NVDA", out)
        self.assertIn("boom", out)


@pytest.mark.unit
class KeenableRoutingTests(unittest.TestCase):
    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def test_registered_for_both_news_tools(self):
        self.assertIn("keenable", interface.VENDOR_LIST)
        self.assertIs(interface.VENDOR_METHODS["get_news"]["keenable"], keenable_news.get_news_keenable)
        self.assertIs(
            interface.VENDOR_METHODS["get_global_news"]["keenable"],
            keenable_news.get_global_news_keenable,
        )
        # Web search cannot serve insider transactions; that tool keeps its vendors.
        self.assertNotIn("keenable", interface.VENDOR_METHODS["get_insider_transactions"])

    def test_tool_vendor_override_routes_get_news_to_keenable(self):
        set_config({"tool_vendors": {"get_news": "keenable"}})
        with mock.patch.object(keenable_news, "_request", return_value=_SEARCH) as req:
            out = interface.route_to_vendor("get_news", "NVDA", *_WINDOW)
        req.assert_called_once()
        self.assertIn("## NVDA News", out)

    def test_rate_limit_falls_through_to_next_vendor_in_chain(self):
        set_config({"tool_vendors": {"get_news": "keenable,yfinance"}})
        yf = mock.Mock(return_value="YF_NEWS")
        with mock.patch.dict(
            interface.VENDOR_METHODS["get_news"], {"yfinance": yf}, clear=False
        ), mock.patch.object(
            keenable_news, "_request", side_effect=keenable_news.KeenableRateLimitError("429")
        ):
            out = interface.route_to_vendor("get_news", "NVDA", *_WINDOW)
        self.assertEqual(out, "YF_NEWS")
        yf.assert_called_once()

    def test_category_chain_routes_insider_transactions_to_next_vendor(self):
        # The documented category-level form "keenable,yfinance": tools keenable
        # does not implement route to the next vendor in the chain, unchanged.
        set_config({"data_vendors": {"news_data": "keenable,yfinance"}})
        yf = mock.Mock(return_value="YF_INSIDER")
        with mock.patch.dict(
            interface.VENDOR_METHODS["get_insider_transactions"], {"yfinance": yf}, clear=False
        ):
            out = interface.route_to_vendor("get_insider_transactions", "NVDA")
        self.assertEqual(out, "YF_INSIDER")

    def test_category_level_keenable_alone_is_rejected_for_insider_data(self):
        # And selecting keenable alone for the category fails loudly on the tool
        # it cannot serve, rather than silently using an unchosen vendor.
        set_config({"data_vendors": {"news_data": "keenable"}})
        with self.assertRaises(ValueError) as ctx:
            interface.route_to_vendor("get_insider_transactions", "NVDA")
        self.assertIn("keenable", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
