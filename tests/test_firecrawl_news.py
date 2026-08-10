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
from tradingagents.dataflows import firecrawl_news, interface, yfinance_news
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import NoNewsError

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


# Payload marker for a body that isn't JSON at all (an HTML error page).
_NOT_JSON = object()


class _Response:
    """Minimal stand-in for ``requests.Response``."""

    _SENTINEL = object()

    def __init__(self, payload=_SENTINEL, status_code=200, text="", headers=None):
        self._payload = {} if payload is self._SENTINEL else payload
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._payload is _NOT_JSON:
            raise ValueError("no JSON body")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def _ok(articles=_ARTICLES):
    return _Response({"success": True, "data": {"news": list(articles)}})


def _empty():
    return _Response({"success": True, "data": {"news": []}})


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
    def test_empty_result_raises_so_the_chain_continues(self):
        with mock.patch.object(
            firecrawl_news.requests, "post", return_value=_empty()
        ), self.assertRaises(NoNewsError) as ctx:
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")
        self.assertEqual(
            str(ctx.exception), "No news found for NVDA between 2026-03-01 and 2026-03-08"
        )

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
@mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
class FirecrawlRetryTests(unittest.TestCase):
    """Firecrawl documents 408/429/500/502/503/504 as transient.

    It is usually the last vendor in a chain, so a throttling burst that isn't
    ridden out costs the run its news coverage outright.
    """

    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
        # Assert on the delays instead of serving them.
        sleep = mock.patch.object(firecrawl_news.time, "sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def _post(self, *responses):
        return mock.patch.object(firecrawl_news.requests, "post", side_effect=responses)

    def test_throttled_then_served(self):
        throttled = _Response(status_code=429, text="slow down", headers={"Retry-After": "3"})
        with self._post(throttled, _ok()):
            out = firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")

        self.assertIn("### Chipmaker beats estimates", out)
        self.sleep.assert_called_once_with(3.0)  # Retry-After honoured, not the curve

    def test_transient_5xx_then_served(self):
        with self._post(_Response(status_code=503, text="down"), _ok()):
            out = firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")

        self.assertIn("### Chipmaker beats estimates", out)
        self.sleep.assert_called_once_with(firecrawl_news.BASE_RETRY_DELAY)

    def test_backoff_doubles_without_a_retry_after_header(self):
        with self._post(*[_Response(status_code=500, text="boom")] * 3), \
                self.assertRaises(requests.HTTPError):
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")

        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [2.0, 4.0])

    def test_retries_are_bounded(self):
        # MAX_RETRIES retries, then the typed error — never an unbounded loop.
        posts = [_Response(status_code=429, text="slow down")] * (firecrawl_news.MAX_RETRIES + 1)
        with self._post(*posts) as post, \
                self.assertRaises(firecrawl_news.FirecrawlRateLimitError):
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")

        self.assertEqual(post.call_count, firecrawl_news.MAX_RETRIES + 1)
        self.assertEqual(self.sleep.call_count, firecrawl_news.MAX_RETRIES)

    def test_outsized_retry_after_is_capped(self):
        # A server asking for an hour must not stall the analysis run.
        throttled = _Response(status_code=429, headers={"Retry-After": "3600"})
        with self._post(throttled, _ok()):
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")
        self.sleep.assert_called_once_with(firecrawl_news.MAX_RETRY_DELAY)

    def test_http_date_retry_after_falls_back_to_the_curve(self):
        # Retry-After's HTTP-date form isn't parsed; back off rather than guess.
        throttled = _Response(
            status_code=429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
        )
        with self._post(throttled, _ok()):
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")
        self.sleep.assert_called_once_with(firecrawl_news.BASE_RETRY_DELAY)

    def test_rejected_key_is_not_retried(self):
        # A rejected key will be rejected again; failing fast keeps the chain moving.
        with self._post(_Response(status_code=401, text="unauthorized")) as post, \
                self.assertRaises(firecrawl_news.FirecrawlNotConfiguredError):
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")

        self.assertEqual(post.call_count, 1)
        self.sleep.assert_not_called()

    def test_non_retryable_4xx_is_not_retried(self):
        with self._post(_Response(status_code=400, text="bad request")) as post, \
                self.assertRaises(requests.HTTPError):
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")

        self.assertEqual(post.call_count, 1)


@pytest.mark.unit
@mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
class FirecrawlResponseValidationTests(unittest.TestCase):
    """An unreadable body is a fault, never a quiet news window.

    The callers turn an empty result into ``NoNewsError``, so anything that
    silently degrades to "no articles" would report a client-side failure to the
    analyst as a market that had nothing to say.
    """

    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def _assert_rejects(self, payload):
        with mock.patch.object(
            firecrawl_news.requests, "post", return_value=_Response(payload)
        ), self.assertRaises(firecrawl_news.FirecrawlResponseError) as ctx:
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")
        # Specifically not NoNewsError, which would end the chain as "quiet week".
        self.assertNotIsInstance(ctx.exception, NoNewsError)

    def test_unsuccessful_body_is_rejected(self):
        self._assert_rejects({"success": False, "error": "something broke"})

    def test_missing_success_flag_is_rejected(self):
        self._assert_rejects({"data": {"news": []}})

    def test_missing_or_malformed_news_list_is_rejected(self):
        self._assert_rejects({"success": True})
        self._assert_rejects({"success": True, "data": {}})
        self._assert_rejects({"success": True, "data": {"news": None}})
        self._assert_rejects({"success": True, "data": "not-a-dict"})

    def test_non_json_body_is_rejected(self):
        with mock.patch.object(
            firecrawl_news.requests, "post",
            return_value=_Response(_NOT_JSON, text="<html>gateway</html>"),
        ), self.assertRaises(firecrawl_news.FirecrawlResponseError):
            firecrawl_news.get_news_firecrawl("NVDA", "2026-03-01", "2026-03-08")


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


@pytest.mark.unit
class FirecrawlRoutingTests(unittest.TestCase):
    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    @staticmethod
    def _yahoo_returning(articles):
        """Patch the real yfinance news path to return ``articles``."""
        stock = mock.Mock()
        stock.get_news.return_value = articles
        return mock.patch.multiple(
            yfinance_news,
            yf=mock.Mock(Ticker=mock.Mock(return_value=stock)),
            yf_retry=lambda fn: fn(),
        )

    @staticmethod
    def _yahoo_raising(exc):
        """Patch the real yfinance news path to fail the way a live outage does."""
        stock = mock.Mock()
        stock.get_news.side_effect = exc
        return mock.patch.multiple(
            yfinance_news,
            yf=mock.Mock(Ticker=mock.Mock(return_value=stock)),
            yf_retry=lambda fn: fn(),
        )

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

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_quiet_yahoo_window_reaches_firecrawl(self):
        # The documented setup, exercised through the real vendor functions and
        # the real router: Yahoo has nothing for this ticker, so Firecrawl — the
        # vendor configured precisely for that case — must get its turn. A vendor
        # that returned "No news found..." as a string would end the chain here.
        set_config({"tool_vendors": {"get_news": "yfinance,firecrawl"}})

        with self._yahoo_returning([]), mock.patch.object(
            firecrawl_news.requests, "post", return_value=_ok()
        ):
            out = interface.route_to_vendor("get_news", "AAPL", "2026-03-01", "2026-03-08")

        self.assertIn("### Chipmaker beats estimates (source: reuters.com)", out)

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_yahoo_outage_reaches_firecrawl(self):
        # A fetch failure must not read as a valid empty report either.
        set_config({"tool_vendors": {"get_news": "yfinance,firecrawl"}})

        with self._yahoo_raising(requests.ConnectionError("yahoo down")), \
                mock.patch.object(firecrawl_news.requests, "post", return_value=_ok()):
            out = interface.route_to_vendor("get_news", "AAPL", "2026-03-01", "2026-03-08")

        self.assertIn("### Chipmaker beats estimates (source: reuters.com)", out)

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_whole_chain_empty_returns_the_primary_message(self):
        # Genuinely quiet week: the analyst gets the primary's wording back, not
        # a raised exception and not the "may be invalid, delisted" market-data
        # sentinel — an empty news window says nothing about the symbol.
        set_config({"tool_vendors": {"get_news": "yfinance,firecrawl"}})

        with self._yahoo_returning([]), mock.patch.object(
            firecrawl_news.requests, "post", return_value=_empty()
        ):
            out = interface.route_to_vendor("get_news", "AAPL", "2026-03-01", "2026-03-08")

        self.assertEqual(out, "No news found for AAPL")
        self.assertNotIn("NO_DATA_AVAILABLE", out)

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_unreadable_response_fails_loudly_rather_than_reading_as_no_news(self):
        set_config({"tool_vendors": {"get_news": "firecrawl"}})

        with mock.patch.object(
            firecrawl_news.requests, "post",
            return_value=_Response({"success": False, "error": "broke"}),
        ), self.assertRaises(firecrawl_news.FirecrawlResponseError):
            interface.route_to_vendor("get_news", "AAPL", "2026-03-01", "2026-03-08")

    @mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"})
    def test_a_broken_fallback_is_logged_even_when_the_primary_had_no_news(self):
        # Established router behaviour (#989) applied to the news path: the
        # reported outcome is still "no news" — no vendor produced any — but the
        # fallback's failure must leave a trace instead of vanishing.
        set_config({"tool_vendors": {"get_news": "yfinance,firecrawl"}})

        with self._yahoo_returning([]), mock.patch.object(
            firecrawl_news.requests, "post",
            return_value=_Response({"success": False, "error": "broke"}),
        ), self.assertLogs("tradingagents.dataflows.interface", level="WARNING") as logs:
            out = interface.route_to_vendor("get_news", "AAPL", "2026-03-01", "2026-03-08")

        self.assertEqual(out, "No news found for AAPL")
        self.assertTrue(any("errored earlier" in m for m in logs.output))

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
