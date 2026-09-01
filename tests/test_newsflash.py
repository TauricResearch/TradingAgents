"""Newsflash deduplicated news-event vendor: confidence/corroboration
formatting, look-ahead-safe date windows, tier-window disclosure, keyless auth,
rate-limit typing, and router integration.

All API access is mocked, so these run without a network connection.
"""
import os
import unittest
from unittest import mock

import pytest

from tradingagents.dataflows import interface, newsflash
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import VendorRateLimitError
from tradingagents.dataflows.newsflash import NewsflashRateLimitError


def _event(title, *, confidence, corroboration, sources, last_seen="2026-07-23T16:00:00.000Z"):
    return {
        "id": 1,
        "canonical_title": title,
        "summary": f"Summary of {title}",
        "category": "tradfi",
        "first_seen_at": "2026-07-23T08:00:00.000Z",
        "last_seen_at": last_seen,
        "sources": sources,
        "corroboration": corroboration,
        "confidence": confidence,
    }


# One corroborated event (2 outlets -> confidence 0.67) and one single-source
# event (confidence 0.33) — the pair the confidence gate exists to distinguish.
_PAYLOAD = {
    "count": 2,
    "events": [
        _event("Fed signals rate cut", confidence=0.6667, corroboration=2,
               sources=["reuters", "cnbc-finance"]),
        _event("Unverified merger rumor", confidence=0.3333, corroboration=1,
               sources=["some-blog"]),
    ],
}

# A response whose history window was clamped by the tier gate (keyless test
# tier: 24 hours). The note must reach the analyst so an empty backtest window
# reads "clamped", not "no news".
_CLAMPED_EMPTY = {
    "count": 0,
    "events": [],
    "window": {
        "from": "2026-07-22T00:00:00.000Z",
        "note": "the test tier can query the last 24 hours",
    },
}


@pytest.mark.unit
class NewsflashFormatTests(unittest.TestCase):
    def test_confidence_corroboration_and_sources_render(self):
        with mock.patch.object(newsflash, "_request", return_value=_PAYLOAD):
            out = newsflash.get_news("AAPL", "2026-07-16", "2026-07-23")
        self.assertIn("Fed signals rate cut", out)
        self.assertIn("confidence 0.67", out)
        self.assertIn("2 sources: reuters, cnbc-finance", out)
        self.assertIn("Date: 2026-07-23", out)

    def test_corroborated_vs_single_source_labeling(self):
        # The fake-news gate: >= 2 outlets reads "confirmed", 1 outlet is
        # explicitly "unconfirmed" so the analyst can't take a rumor as fact.
        with mock.patch.object(newsflash, "_request", return_value=_PAYLOAD):
            out = newsflash.get_news("AAPL", "2026-07-16", "2026-07-23")
        confirmed_line = next(ln for ln in out.splitlines() if "Fed signals" in ln)
        rumor_line = next(ln for ln in out.splitlines() if "merger rumor" in ln)
        self.assertIn("(confirmed", confirmed_line)
        self.assertIn("(unconfirmed", rumor_line)
        self.assertIn("1 source: some-blog", rumor_line)

    def test_no_matches_reports_clearly(self):
        with mock.patch.object(newsflash, "_request", return_value={"count": 0, "events": []}):
            out = newsflash.get_news("OBSCURE", "2026-07-16", "2026-07-23")
        self.assertIn("No news events found for OBSCURE", out)

    def test_clamped_window_is_disclosed(self):
        # Keyless tiers clamp history depth server-side; the disclosure must be
        # surfaced (especially on empty results) so a backtest outside the tier
        # window is reported as clamped rather than as "no news".
        with mock.patch.object(newsflash, "_request", return_value=_CLAMPED_EMPTY):
            out = newsflash.get_news("AAPL", "2025-01-01", "2025-01-07")
        self.assertIn("No news events found", out)
        self.assertIn("history window clamped", out)
        self.assertIn("test tier can query the last 24 hours", out)


@pytest.mark.unit
class NewsflashWindowTests(unittest.TestCase):
    def test_get_news_sends_lookahead_safe_bounds(self):
        # The from/to bounds are the look-ahead guard: they must be passed
        # through verbatim so the server never returns post-window events.
        with mock.patch.object(newsflash, "_request", return_value=_PAYLOAD) as req:
            newsflash.get_news("AAPL", "2026-07-16", "2026-07-23")
        params = req.call_args.args[0]
        self.assertEqual(params["from"], "2026-07-16")
        # Inclusive of the whole end day (a bare date would be parsed as its
        # midnight and drop the day, #1126), but nothing after it leaks.
        self.assertEqual(params["to"], "2026-07-23T23:59:59.999Z")
        self.assertEqual(params["q"], "AAPL")
        self.assertEqual(params["semantic"], "1")  # meaning-based ticker match

    def test_global_news_window_derived_from_lookback(self):
        with mock.patch.object(newsflash, "_request", return_value=_PAYLOAD) as req:
            newsflash.get_global_news("2026-07-23", look_back_days=7, limit=10)
        params = req.call_args.args[0]
        self.assertEqual(params["from"], "2026-07-16")
        self.assertEqual(params["to"], "2026-07-23T23:59:59.999Z")
        self.assertEqual(params["limit"], "10")
        self.assertNotIn("q", params)  # keyword-less: latest events across categories

    def test_global_news_defaults_come_from_config(self):
        set_config({"global_news_lookback_days": 3, "global_news_article_limit": 5})
        with mock.patch.object(newsflash, "_request", return_value=_PAYLOAD) as req:
            newsflash.get_global_news("2026-07-23")
        params = req.call_args.args[0]
        self.assertEqual(params["from"], "2026-07-20")
        self.assertEqual(params["limit"], "5")

    def test_semantic_unavailable_degrades_to_keyword_match(self):
        # Deployments without embeddings answer 503 for semantic=1; the vendor
        # must retry as a plain keyword query instead of failing the call.
        def fake_request(params):
            if params.get("semantic"):
                raise ValueError("Newsflash request failed (503): semantic search is not configured")
            return _PAYLOAD

        with mock.patch.object(newsflash, "_request", side_effect=fake_request) as req:
            out = newsflash.get_news("AAPL", "2026-07-16", "2026-07-23")
        self.assertIn("Fed signals rate cut", out)
        self.assertNotIn("semantic", req.call_args.args[0])


@pytest.mark.unit
class NewsflashAuthTests(unittest.TestCase):
    def _get(self, status=200, payload=None):
        response = mock.Mock()
        response.status_code = status
        response.json.return_value = payload if payload is not None else _PAYLOAD
        return response

    def test_keyless_request_sends_no_auth_header(self):
        with (
            mock.patch.dict("os.environ"),
            mock.patch.object(newsflash.requests, "get", return_value=self._get()) as get,
        ):
            os.environ.pop("NEWSFLASH_API_KEY", None)
            newsflash._request({"q": "AAPL"})
        self.assertEqual(get.call_args.kwargs["headers"], {})

    def test_api_key_sent_as_bearer_token(self):
        with (
            mock.patch.dict("os.environ", {"NEWSFLASH_API_KEY": "nf_test_key"}),
            mock.patch.object(newsflash.requests, "get", return_value=self._get()) as get,
        ):
            newsflash._request({"q": "AAPL"})
        self.assertEqual(
            get.call_args.kwargs["headers"], {"Authorization": "Bearer nf_test_key"}
        )

    def test_daily_limit_raises_typed_rate_limit_error(self):
        # 429 must surface as a VendorRateLimitError so the router skips to the
        # next configured vendor instead of aborting the run.
        response = self._get(status=429, payload={"error": "daily limit reached (50 requests/day)"})
        with (
            mock.patch.object(newsflash.requests, "get", return_value=response),
            self.assertRaises(NewsflashRateLimitError) as ctx,
        ):
            newsflash._request({"q": "AAPL"})
        self.assertIsInstance(ctx.exception, VendorRateLimitError)
        self.assertIn("daily limit reached", str(ctx.exception))

    def test_api_error_body_is_surfaced(self):
        response = self._get(status=400, payload={"error": "invalid category"})
        with (
            mock.patch.object(newsflash.requests, "get", return_value=response),
            self.assertRaises(ValueError) as ctx,
        ):
            newsflash._request({"category": "bogus"})
        self.assertIn("invalid category", str(ctx.exception))


@pytest.mark.unit
class NewsflashRoutingTests(unittest.TestCase):
    def test_news_data_category_routes_to_newsflash(self):
        set_config({"data_vendors": {"news_data": "newsflash"}})
        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_news": {"newsflash": lambda *a, **k: "NEWSFLASH_OK"}},
            clear=False,
        ):
            out = interface.route_to_vendor("get_news", "AAPL", "2026-07-16", "2026-07-23")
        self.assertEqual(out, "NEWSFLASH_OK")

    def test_rate_limited_newsflash_falls_back_to_next_vendor(self):
        # data_vendors="newsflash,yfinance": a 429 on the primary must roll over
        # to the configured fallback, not abort the run.
        def limited(*a, **k):
            raise NewsflashRateLimitError("daily limit reached")

        set_config({"data_vendors": {"news_data": "newsflash,yfinance"}})
        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_news": {"newsflash": limited, "yfinance": lambda *a, **k: "YF_OK"}},
            clear=False,
        ):
            out = interface.route_to_vendor("get_news", "AAPL", "2026-07-16", "2026-07-23")
        self.assertEqual(out, "YF_OK")

    def test_both_news_methods_registered(self):
        self.assertIn("newsflash", interface.VENDOR_METHODS["get_news"])
        self.assertIn("newsflash", interface.VENDOR_METHODS["get_global_news"])
        self.assertIn("newsflash", interface.VENDOR_LIST)


if __name__ == "__main__":
    unittest.main()
