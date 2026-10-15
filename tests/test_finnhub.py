"""Tests for the Finnhub vendor (US-coverage alternative source).

Finnhub (finnhub.io) is wired as a *secondary/alternative* vendor, not the
primary: it is selected only by its configured chain position and degrades
cleanly so any ticker stays analyzable:

* **Coverage gate** — every entry point first queries ``/stock/profile2``; an
  empty profile means "not covered by this plan" (verified: DE tickers return
  ``{}`` while US tickers return a full profile) -> ``NoMarketDataError`` so
  the router falls through, never an HTTP error or zeros-as-fact.
* **No token** — a missing ``FINNHUB_API_KEY``/``FINNHUB_API_TOKEN`` is a
  *configuration* error (``VendorNotConfiguredError``), not a vendor outage.
* **Point-in-time insider** — SEC Form 4 records carry ``filingDate``, so a
  historical run is filtered to filings already public on/before the run date
  (unlike vendors that date a trade by execution and are withheld entirely).
* **Empty news window** — raises ``NoMarketDataError`` so the vendor chain
  continues; an aggregator returning a string would stop the chain and
  suppress every later news vendor.

All tests are offline: the module's own ``_get_json`` is patched, so the token
never reaches the network and error-message scrubbing is exercised directly.
"""

import os
import unittest
from unittest.mock import patch

from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.vendors import finnhub
from tradingagents.dataflows.vendors.finnhub import get_finnhub_api_key

TOKEN = "fb-token-1234567890abcdefghij"

PROFILE = {
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "exchange": "NASDAQ",
    "country": "US",
    "currency": "USD",
    "finnhubIndustry": "Technology",
    "marketCapitalization": 4000,
    "shareOutstanding": 15.0,
}

MATERIAL = {"metric": {"peTTM": 35.1, "beta": 1.25, "52WeekHigh": 260.1,
                       "52WeekLow": 170.4, "dividendYieldTTM": 0.5}}

# SEC Form 4 filings with a realistic ~12-month clamp (observed coverage
# window 2025-11-21 .. 2026-10-08), matching the free-plan behaviour verified
# live (AAPL returns ~12 months of filings, not a complete history).
INSIDER = {"data": [
    {"name": "Dirk Ahmad", "share": 200, "isDerivative": 0,
     "transactionDate": "2026-10-06", "transactionCode": "S",
     "filingDate": "2026-10-08"},
    {"name": "Tim D. Cook", "share": 1000, "isDerivative": 0,
     "transactionDate": "2026-01-15", "transactionCode": "S",
     "filingDate": "2026-01-17"},
    {"name": "Luigi M. Garza", "share": 500, "isDerivative": 1,
     "transactionDate": "2025-11-20", "transactionCode": "M",
     "filingDate": "2025-11-21"},
]}

# 1761792000 = 2025-10-29T00:00Z (in the 2026-10-01..2026-10-09 window is
# FALSE — used as the "other article" to confirm window filtering); the
# in-window article is 1790000000 = 2026-09-22T04:13Z.
NEWS = [
    {"headline": "Apple posts record quarter", "source": "reuters.com",
     "summary": "Revenue up.", "url": "https://reuters.com/a",
     "datetime": "1790000000", "related": "AAPL"},
    {"headline": "Older, out-of-window story", "source": "yahoo.com",
     "summary": "Old.", "url": "https://yahoo.com/b",
     "datetime": "1699900000", "related": "AAPL"},
]


def _resp(path, params, token):
    if "insider-transactions" in path:
        return INSIDER
    if "company-news" in path:
        return NEWS
    if "profile2" in path:
        return PROFILE
    if "/metric" in path:
        return MATERIAL
    return {}


class FinnhubTestBase(unittest.TestCase):
    def setUp(self):
        self._tok = patch.object(finnhub, "get_finnhub_api_key", return_value=TOKEN)
        self._tok.start()
        self.addCleanup(self._tok.stop)
        self._get = patch.object(finnhub, "_get_json")
        self.mock_get = self._get.start()
        self.addCleanup(self._get.stop)


class ApiKeyTests(unittest.TestCase):
    def test_reads_canonical_key_env(self):
        with patch.dict(os.environ, {"FINNHUB_API_KEY": "k1"}, clear=False):
            os.environ.pop("FINNHUB_API_TOKEN", None)
            self.assertEqual(get_finnhub_api_key(), "k1")

    def test_falls_back_to_token_env(self):
        with patch.dict(os.environ, {"FINNHUB_API_TOKEN": "t1"}, clear=False):
            os.environ.pop("FINNHUB_API_KEY", None)
            self.assertEqual(get_finnhub_api_key(), "t1")

    def test_missing_key_is_empty_not_exception(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("FINNHUB_API_KEY", "FINNHUB_API_TOKEN")}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(get_finnhub_api_key(), "")


class NoTokenTests(unittest.TestCase):
    def test_missing_key_raises_not_configured(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("FINNHUB_API_KEY", "FINNHUB_API_TOKEN")}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(VendorNotConfiguredError):
                finnhub.get_finnhub_fundamentals("AAPL")
            with self.assertRaises(VendorNotConfiguredError):
                finnhub.get_finnhub_insider_transactions("AAPL")
            with self.assertRaises(VendorNotConfiguredError):
                finnhub.get_news_finnhub("AAPL", "2026-10-01", "2026-10-09")


class CoverageGateTests(FinnhubTestBase):
    def test_empty_profile_is_no_coverage_not_outage(self):
        # A symbol the free plan does not cover returns an empty profile
        # (HTTP 200). That is "not covered here", so the router must fall
        # through to the next vendor — never an HTTP error, never zeros.
        self.mock_get.return_value = {}
        with self.assertRaises(NoMarketDataError) as ctx:
            finnhub.get_finnhub_fundamentals("RHM.DE")
        self.assertEqual(ctx.exception.symbol, "RHM.DE")

    def test_none_profile_is_no_coverage(self):
        # 404 on profile2 (also "not covered") is handled the same way.
        self.mock_get.return_value = None
        with self.assertRaises(NoMarketDataError):
            finnhub.get_finnhub_fundamentals("RHM.DE")


class FundamentalsTests(FinnhubTestBase):
    def test_present_day_serves_profile_and_metrics(self):
        self.mock_get.side_effect = _resp
        out = finnhub.get_finnhub_fundamentals("AAPL")
        self.assertIn("# Finnhub fundamentals for AAPL", out)
        self.assertIn("Name: Apple Inc.", out)
        self.assertIn("P/E (TTM): 35.1", out)
        # header is honest about scope
        self.assertIn("present-day snapshot", out)

    def test_past_date_is_withheld_not_served(self):
        self.mock_get.side_effect = _resp
        out = finnhub.get_finnhub_fundamentals("AAPL", as_of_date="2026-01-01")
        # the shared point-in-time guard withholds present-day profiles
        self.assertIn("withheld", out.lower())


class InsiderPointInTimeTests(FinnhubTestBase):
    def test_only_disclosed_filings_returned(self):
        self.mock_get.side_effect = _resp
        out = finnhub.get_finnhub_insider_transactions("AAPL", as_of_date="2026-01-31")
        # the Oct 2026 filing is after the as-of date and must be filtered out
        self.assertNotIn("Dirk Ahmad", out)
        self.assertIn("Tim D. Cook", out)
        self.assertIn("Luigi M. Garza", out)
        # header names the point-in-time rule
        self.assertIn("point-in-time", out)

    def test_as_of_before_coverage_window_raises_not_string(self):
        # The free feed is a clamped ~12-month sample. A date before its
        # earliest filing cannot be answered honestly, so the vendor raises
        # (chain continues) rather than claim "no filings existed" for it.
        self.mock_get.side_effect = _resp
        with self.assertRaises(NoMarketDataError) as ctx:
            finnhub.get_finnhub_insider_transactions("AAPL", as_of_date="2024-06-01")
        self.assertIn("before", ctx.exception.detail.lower())

    def test_no_filings_returns_honest_empty(self):
        def fake(path, params, token):
            if "insider-transactions" in path:
                return {"data": []}
            return PROFILE
        self.mock_get.side_effect = fake
        out = finnhub.get_finnhub_insider_transactions("AAPL")
        self.assertIn("No insider transactions", out)
        self.assertIn("Source coverage is unverified", out)

    def test_invalid_as_of_date_is_ignored(self):
        self.mock_get.side_effect = _resp
        out = finnhub.get_finnhub_insider_transactions("AAPL", as_of_date="not-a-date")
        # malformed date -> treated as no filter, all covered filings returned
        self.assertIn("Dirk Ahmad", out)


class NewsTests(FinnhubTestBase):
    def test_window_filters_and_formats(self):
        self.mock_get.side_effect = _resp
        out = finnhub.get_news_finnhub("AAPL", "2026-09-01", "2026-10-09")
        self.assertIn("Apple posts record quarter", out)
        self.assertNotIn("Older, out-of-window story", out)
        self.assertIn("Source: finnhub.io /company-news", out)

    def test_empty_news_window_raises_not_string(self):
        # An empty/clamped news sample must not stop the vendor chain.
        def fake(path, params, token):
            if "company-news" in path:
                return []
            return PROFILE
        self.mock_get.side_effect = fake
        with self.assertRaises(NoMarketDataError) as ctx:
            finnhub.get_news_finnhub("AAPL", "2020-01-01", "2020-01-05")
        self.assertEqual(ctx.exception.symbol, "AAPL")

    def test_out_of_window_articles_do_not_crash_coverage(self):
        # Regression: articles were returned but all fall outside the window.
        # coverage_gap() must receive datetime objects (not date strings) or
        # it raises AttributeError — the free-plan "everything is recent" case.
        def fake(path, params, token):
            if "company-news" in path:
                return NEWS  # both articles are 2025/2023, window is 2020
            return PROFILE
        self.mock_get.side_effect = fake
        with self.assertRaises(NoMarketDataError) as ctx:
            finnhub.get_news_finnhub("AAPL", "2020-01-01", "2020-01-05")
        self.assertIn("not an absence", ctx.exception.detail)

    def test_malformed_date_raises_value_error(self):
        self.mock_get.side_effect = _resp
        with self.assertRaises(ValueError):
            finnhub.get_news_finnhub("AAPL", "2026-10-01", "not-a-date")


class ErrorMappingTests(FinnhubTestBase):
    def test_auth_failure_is_unavailable(self):
        self.mock_get.side_effect = VendorUnavailableError(
            "finnhub rejected the request (401/403) — check FINNHUB_API_KEY")
        with self.assertRaises(VendorUnavailableError):
            finnhub.get_finnhub_fundamentals("AAPL")

    def test_404_on_profile_is_no_market_data(self):
        self.mock_get.return_value = None
        with self.assertRaises(NoMarketDataError) as ctx:
            finnhub.get_finnhub_fundamentals("RHM.DE")
        self.assertEqual(ctx.exception.symbol, "RHM.DE")


if __name__ == "__main__":
    unittest.main()
