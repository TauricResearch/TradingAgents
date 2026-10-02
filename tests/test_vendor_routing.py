"""Vendor router must respect the configured chain and never silently hide a
broken primary.

Regressions for #988 (explicit single-vendor config still fell back to others),
#289 (fallback ran for unchosen vendors), and #989 (serious primary failures
were swallowed without a trace).
"""
import copy
import unittest
from unittest import mock

import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import router
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import NoMarketDataError


def _reset_config():
    # Hard reset: set_config() merges, so empty DEFAULT dicts (e.g. tool_vendors)
    # don't clear keys leaked by other tests. Replace the global outright.
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)


def _no_data(symbol, *a, **k):
    raise NoMarketDataError(symbol, symbol, "no rows")


def _returns(value):
    def impl(symbol, *a, **k):
        return value
    return impl


def _raises(exc):
    def impl(symbol, *a, **k):
        raise exc
    return impl


@pytest.mark.unit
class VendorRoutingTests(unittest.TestCase):
    def setUp(self):
        _reset_config()

    def tearDown(self):
        _reset_config()

    def _route(self, vendors_for_get_stock_data):
        return mock.patch.dict(
            router.VENDOR_METHODS,
            {"get_stock_data": vendors_for_get_stock_data},
            clear=False,
        )

    def test_explicit_single_vendor_does_not_fall_back(self):
        # #988: with yfinance pinned, a healthy alpha_vantage must NOT be used.
        set_config({"data_vendors": {"core_stock_apis": "yfinance"}})
        av = mock.Mock(side_effect=_returns("AV_DATA"))
        with self._route({"yfinance": _no_data, "alpha_vantage": av}):
            result = router.route_to_vendor("get_stock_data", "FAKE", "2026-01-01", "2026-01-10")
        self.assertIn("NO_DATA_AVAILABLE", result)
        av.assert_not_called()  # the unchosen vendor was never tried

    def test_explicit_multi_vendor_falls_back_within_chain(self):
        # Listing both vendors opts in to ordered fallback.
        set_config({"data_vendors": {"core_stock_apis": "yfinance,alpha_vantage"}})
        with self._route({"yfinance": _no_data, "alpha_vantage": _returns("AV_DATA")}):
            result = router.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
        self.assertEqual(result, "AV_DATA")

    def test_primary_error_is_logged_not_masked(self):
        # #989: a broken primary is not hidden behind a fallback's verdict. It
        # never said whether it has the symbol, so the answer is unavailable,
        # and the failure is in the logs.
        set_config({"data_vendors": {"core_stock_apis": "yfinance,alpha_vantage"}})
        with self._route({"yfinance": _raises(ValueError("boom")), "alpha_vantage": _no_data}), \
                self.assertLogs("tradingagents.dataflows.router", level="WARNING") as cm:
            result = router.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
        self.assertTrue(result.startswith("DATA_UNAVAILABLE"), result)
        joined = "\n".join(cm.output)
        self.assertIn("boom", joined)            # the real error surfaced in logs
        self.assertIn("yfinance", joined)

    def test_unknown_configured_vendor_raises(self):
        set_config({"data_vendors": {"core_stock_apis": "bogus_vendor"}})
        with self.assertRaises(ValueError) as ctx:
            router.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
        self.assertIn("bogus_vendor", str(ctx.exception))

    def test_default_sentinel_uses_all_vendors(self):
        # No explicit choice ("default") keeps the resilient full-chain behavior.
        set_config({"data_vendors": {"core_stock_apis": "default"}})
        with self._route({"yfinance": _no_data, "alpha_vantage": _returns("AV_DATA")}):
            result = router.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
        self.assertEqual(result, "AV_DATA")

    def _route_method(self, method, vendors):
        return mock.patch.dict(router.VENDOR_METHODS, {method: vendors}, clear=False)

    def test_optional_category_degrades_instead_of_raising(self):
        # An optional enrichment vendor (FRED macro) that raises must NOT abort
        # the run — the router returns a sentinel so the analysis proceeds.
        set_config({"data_vendors": {"macro_data": "fred"}})
        with self._route_method(
            "get_macro_indicators", {"fred": _raises(ValueError("FRED 400: bad series"))}
        ):
            result = router.route_to_vendor("get_macro_indicators", "cpi", "2026-01-01")
        self.assertIn("DATA_UNAVAILABLE", result)
        self.assertIn("macro_data", result)

    def test_core_category_still_raises_on_error(self):
        # A core category (single configured vendor) propagates the error so a
        # broken primary is loud, not silently degraded.
        set_config({"data_vendors": {"core_stock_apis": "yfinance"}})
        with self._route({"yfinance": _raises(ValueError("boom"))}), \
                self.assertRaises(ValueError):
            router.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")


    def test_news_queries_every_configured_vendor(self):
        set_config({"data_vendors": {"news_data": "one,two,three"}})
        calls = []

        def source(name):
            def fetch(*args, **kwargs):
                calls.append(name)
                return f"{name.upper()} NEWS"
            return fetch

        with self._route_method(
            "get_news",
            {"one": source("one"), "two": source("two"), "three": source("three")},
        ):
            result = router.route_to_vendor(
                "get_news", "AAPL", "2026-01-01", "2026-01-10"
            )

        self.assertEqual(calls, ["one", "two", "three"])
        self.assertIn("All 3 successful configured provider(s) were queried", result)
        for vendor in calls:
            self.assertIn(f"## Provider: `{vendor}`", result)
            self.assertIn(f"{vendor.upper()} NEWS", result)
        self.assertLess(result.index("`one`"), result.index("`two`"))
        self.assertLess(result.index("`two`"), result.index("`three`"))

    def test_global_news_aggregates_partial_success_and_reports_failure(self):
        from tradingagents.dataflows.errors import VendorUnavailableError

        set_config({"data_vendors": {"news_data": "down,working"}})

        def down(*args, **kwargs):
            raise VendorUnavailableError("quota")

        with self._route_method(
            "get_global_news", {"down": down, "working": lambda *a, **k: "GLOBAL NEWS"}
        ):
            result = router.route_to_vendor("get_global_news", "2026-01-10", 7, 10)

        self.assertIn("## Provider: `working`", result)
        self.assertIn("GLOBAL NEWS", result)
        self.assertIn("## Provider availability", result)
        self.assertIn("`down`: temporarily unavailable", result)

    def test_non_news_routes_still_stop_after_first_success(self):
        set_config({"data_vendors": {"core_stock_apis": "one,two"}})
        first = mock.Mock(return_value="FIRST")
        second = mock.Mock(return_value="SECOND")
        with self._route({"one": first, "two": second}):
            result = router.route_to_vendor(
                "get_stock_data", "AAPL", "2026-01-01", "2026-01-10"
            )
        self.assertEqual(result, "FIRST")
        first.assert_called_once()
        second.assert_not_called()


if __name__ == "__main__":
    unittest.main()
