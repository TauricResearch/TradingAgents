"""Tests for the marketaux news vendor (licensed JSON news API).

The token only ever enters via the MARKETAUX_API_TOKEN environment variable
and must never appear in output, errors, or raised messages. HTTP is mocked
at get_scrubbed (the vendor's single network seam), so no test touches the
network or a real token.
"""

import os
import unittest
from unittest.mock import Mock, patch

from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.vendors import marketaux


def _response(status: int, payload) -> Mock:
    resp = Mock()
    resp.status_code = status
    resp.ok = status < 400
    resp.json.return_value = payload
    return resp


ENTITY_OK = {
    "data": [
        {"symbol": "RHM.DE", "name": "RHEINMETALL AG", "type": "equity",
         "country": "de", "match_score": 98.1},
        {"symbol": "RHM", "name": "RHEINMETALL AG", "type": "equity",
         "country": "us", "match_score": 40.0},
    ]
}

NEWS_OK = {
    "meta": {"found": 3, "returned": 3, "limit": 10, "page": 1},
    "data": [
        {"uuid": "a1", "title": "PDMR notice: manager purchases shares",
         "published_at": "2026-10-08T08:30:00.000000Z",
         "source": "eqs-news.com", "url": "https://www.eqs-news.com/x1",
         "description": "Disclosure of inside information.",
         "sentiment_score": 0.31},
        {"uuid": "a2", "title": "Rheinmetall orders update",
         "published_at": "2026-10-02T12:00:00.000000Z",
         "source": "eqs-news.com", "url": "https://www.eqs-news.com/x2",
         "description": "New contract awarded.", "sentiment_score": 0.55},
        {"uuid": "a3", "title": "Old article outside window",
         "published_at": "2026-09-01T09:00:00.000000Z",
         "source": "dpa.com", "url": "https://www.dpa.com/x3",
         "description": "September story.", "sentiment_score": -0.2},
    ],
}


class MarketauxVendorTests(unittest.TestCase):
    def setUp(self):
        self._env_patcher = patch.dict(
            os.environ, {"MARKETAUX_API_TOKEN": "TEST-TOKEN-DO-NOT-LEAK"})
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)
        self.cfg = patch.object(
            marketaux, "get_config", return_value={"news_article_limit": 10})
        self.cfg.start()
        self.addCleanup(self.cfg.stop)

    # --- configuration -----------------------------------------------------

    def test_missing_token_raises_not_configured(self):
        os.environ.pop("MARKETAUX_API_TOKEN")
        with self.assertRaises(VendorNotConfiguredError):
            marketaux.get_news_marketaux("RHM.DE", "2026-10-01", "2026-10-09")

    def test_token_is_read_from_env(self):
        self.assertEqual(marketaux.get_marketaux_api_token(), "TEST-TOKEN-DO-NOT-LEAK")

    # --- country mapping ----------------------------------------------------

    def test_country_suffix_mapping(self):
        self.assertEqual(marketaux._country_for("RHM.DE"), "de")
        self.assertEqual(marketaux._country_for("AAPL.US"), "us")
        self.assertEqual(marketaux._country_for("DTE.DE"), "de")
        self.assertEqual(marketaux._country_for("BTCUSD"), "")

    # --- happy path ----------------------------------------------------------

    @patch.object(marketaux, "get_scrubbed")
    def test_news_window_articles_with_provenance_header(self, get):
        calls = []

        def fake(url, **kwargs):
            calls.append((url, kwargs))
            if "/entity/search" in url:
                return _response(200, ENTITY_OK)
            return _response(200, NEWS_OK)

        get.side_effect = fake
        result = marketaux.get_news_marketaux("RHM.DE", "2026-10-01", "2026-10-09")

        self.assertIn("## Marketaux news: RHM.DE", result)
        self.assertIn("PDMR notice: manager purchases shares", result)
        self.assertIn("Rheinmetall orders update", result)
        self.assertNotIn("Old article outside window", result)  # outside window
        self.assertIn("sentiment", result.lower())
        self.assertIn("eqs-news.com", result)
        self.assertIn("2026-10-08", result)
        self.assertNotIn("TEST-TOKEN-DO-NOT-LEAK", result)  # token never leaks into output
        # token rides in the api_token param of every request
        for _, kwargs in calls:
            self.assertEqual(kwargs["params"].get("api_token"), "TEST-TOKEN-DO-NOT-LEAK")
            self.assertEqual(kwargs["secret"], "TEST-TOKEN-DO-NOT-LEAK")

    @patch.object(marketaux, "get_scrubbed")
    def test_window_boundaries_and_sentiment_average(self, get):
        def fake(url, **kwargs):
            if "/entity/search" in url:
                return _response(200, ENTITY_OK)
            return _response(200, NEWS_OK)

        get.side_effect = fake
        result = marketaux.get_news_marketaux("RHM.DE", "2026-10-01", "2026-10-09")
        # avg of +0.31 and +0.55 = +0.430
        self.assertIn("+0.430", result)

    @patch.object(marketaux, "get_scrubbed")
    def test_entity_resolution_notes_fuzzy_match(self, get):
        calls = {"entity": []}

        def fake(url, **kwargs):
            if "/entity/search" in url:
                calls["entity"].append(kwargs["params"])
                # full-ticker lookup: only a non-exact (fuzzy) candidate
                if kwargs["params"]["search"] == "RHM.DE":
                    return _response(200, {"data": [
                        {"symbol": "RHM.DEU", "name": "RHEINMETALL AG",
                         "type": "equity", "country": "de",
                         "match_score": 40.0},
                    ]})
                # root lookup: the exact listing, ranked by match_score
                return _response(200, {"data": [
                    {"symbol": "RHM.DE", "name": "RHEINMETALL AG",
                     "type": "equity", "country": "de",
                     "match_score": 61.5},
                ]})
            # no news in the window -> the vendor raises NoMarketDataError
            # (chain continues) after resolving the symbol
            return _response(200, {"meta": {"found": 0}, "data": []})

        get.side_effect = fake
        with self.assertRaises(NoMarketDataError):
            marketaux.get_news_marketaux("RHM.DE", "2026-10-01", "2026-10-09")
        # full ticker first, then the bare root as the disambiguation fallback
        self.assertEqual([c["search"] for c in calls["entity"]], ["RHM.DE", "RHM"])
        self.assertEqual(calls["entity"][-1]["countries"], "de")

    # --- coverage / empty -----------------------------------------------------

    @patch.object(marketaux, "get_scrubbed")
    def test_empty_window_raises_no_data_not_string(self, get):
        def fake(url, **kwargs):
            if "/entity/search" in url:
                return _response(200, ENTITY_OK)
            return _response(200, {"meta": {"found": 0}, "data": []})

        get.side_effect = fake
        # marketaux sits AHEAD of the authoritative news vendors in the chain,
        # so an empty/clamped sample must NOT stop the chain: it raises
        # NoMarketDataError (chain continues) rather than returning a "no news"
        # string that would suppress issuer_rss / yfinance / alpha_vantage.
        with self.assertRaises(NoMarketDataError) as ctx:
            marketaux.get_news_marketaux("RHM.DE", "2026-01-01", "2026-01-05")
        # the coverage caveat (a past window a recent-only feed can't fully
        # observe) rides in the error detail, visible in the router log
        self.assertIn("not an absence", str(ctx.exception))

    @patch.object(marketaux, "get_scrubbed")
    def test_empty_recent_window_still_no_data(self, get):
        def fake(url, **kwargs):
            if "/entity/search" in url:
                return _response(200, ENTITY_OK)
            return _response(200, {"meta": {"found": 0}, "data": []})

        get.side_effect = fake
        # even a recent window with zero articles is not proof of absence —
        # the free plan clamps the sample, so the chain continues
        with self.assertRaises(NoMarketDataError):
            marketaux.get_news_marketaux("RHM.DE", "2026-10-01", "2026-10-09")

    @patch.object(marketaux, "get_scrubbed")
    def test_news_404_is_unavailable_not_silence(self, get):
        def fake(url, **kwargs):
            if "/entity/search" in url:
                return _response(200, ENTITY_OK)
            return _response(404, {"error": "not found"})

        get.side_effect = fake
        with self.assertRaises(VendorUnavailableError):
            marketaux.get_news_marketaux("RHM.DE", "2026-10-01", "2026-10-09")

    # --- error mapping ---------------------------------------------------------

    @patch.object(marketaux, "get_scrubbed")
    def test_auth_failure_maps_to_unavailable(self, get):
        get.return_value = _response(401, {"error": "bad token"})
        with self.assertRaises(VendorUnavailableError) as ctx:
            marketaux.get_news_marketaux("RHM.DE", "2026-10-01", "2026-10-09")
        self.assertIn("401/403", str(ctx.exception))

    @patch.object(marketaux, "get_scrubbed")
    def test_rate_limit_maps_to_unavailable(self, get):
        get.return_value = _response(429, {"error": "quota"})
        with self.assertRaises(VendorUnavailableError) as ctx:
            marketaux.get_news_marketaux("RHM.DE", "2026-10-01", "2026-10-09")
        self.assertIn("429", str(ctx.exception))

    @patch.object(marketaux, "get_scrubbed")
    def test_transport_error_maps_to_unavailable_without_token(self, get):
        get.side_effect = Exception("connection aborted: https://api.marketaux.com/v1/entity/search?api_token=TEST-TOKEN-DO-NOT-LEAK")
        with self.assertRaises(VendorUnavailableError) as ctx:
            marketaux.get_news_marketaux("RHM.DE", "2026-10-01", "2026-10-09")
        # get_scrubbed already scrubs, and the vendor must not re-leak
        self.assertNotIn("TEST-TOKEN-DO-NOT-LEAK", str(ctx.exception))

    # --- validation ---------------------------------------------------------------

    def test_malformed_date_raises(self):
        with self.assertRaises(ValueError):
            marketaux.get_news_marketaux("RHM.DE", "01.10.2026", "2026-10-09")

    def test_start_after_end_raises(self):
        with self.assertRaises(ValueError):
            marketaux.get_news_marketaux("RHM.DE", "2026-10-09", "2026-10-01")

    # --- limit clamp --------------------------------------------------------------

    @patch.object(marketaux, "get_scrubbed")
    def test_article_limit_clamps_output(self, get):
        many = {
            "meta": {"found": 30, "returned": 30, "limit": 30, "page": 1},
            "data": [
                {"uuid": f"u{i}", "title": f"Article {i}",
                 "published_at": "2026-10-05T08:00:00.000000Z",
                 "source": "eqs-news.com", "url": f"https://x/{i}",
                 "description": "", "sentiment_score": None}
                for i in range(30)
            ],
        }

        def fake(url, **kwargs):
            if "/entity/search" in url:
                return _response(200, ENTITY_OK)
            return _response(200, many)

        get.side_effect = fake
        result = marketaux.get_news_marketaux("RHM.DE", "2026-10-01", "2026-10-09")
        # default news_article_limit is 10: the 30 matched items are clamped to 10
        self.assertIn("showing 10 of 30", result)
        self.assertEqual(result.count("### "), 10)


if __name__ == "__main__":
    unittest.main()
