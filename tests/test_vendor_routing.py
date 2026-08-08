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
from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import VendorError, VendorRateLimitError
from tradingagents.dataflows.symbol_utils import NoMarketDataError


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
            interface.VENDOR_METHODS,
            {"get_stock_data": vendors_for_get_stock_data},
            clear=False,
        )

    def test_explicit_single_vendor_does_not_fall_back(self):
        # #988: with yfinance pinned, a healthy alpha_vantage must NOT be used.
        set_config({"data_vendors": {"core_stock_apis": "yfinance"}})
        av = mock.Mock(side_effect=_returns("AV_DATA"))
        with self._route({"yfinance": _no_data, "alpha_vantage": av}):
            result = interface.route_to_vendor("get_stock_data", "FAKE", "2026-01-01", "2026-01-10")
        self.assertIn("NO_DATA_AVAILABLE", result)
        av.assert_not_called()  # the unchosen vendor was never tried

    def test_explicit_multi_vendor_falls_back_within_chain(self):
        # Listing both vendors opts in to ordered fallback.
        set_config({"data_vendors": {"core_stock_apis": "yfinance,alpha_vantage"}})
        with self._route({"yfinance": _no_data, "alpha_vantage": _returns("AV_DATA")}):
            result = interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
        self.assertEqual(result, "AV_DATA")

    def test_primary_error_is_not_misreported_as_no_data(self):
        # A clean empty result cannot prove absence when another provider was
        # never observed successfully.
        set_config({"data_vendors": {"core_stock_apis": "yfinance,alpha_vantage"}})
        secret = "https://provider.invalid/?token=must-not-escape"
        with self._route(
            {"yfinance": _raises(ValueError(secret)), "alpha_vantage": _no_data}
        ), self.assertLogs(
            "tradingagents.dataflows.interface", level="INFO"
        ) as cm, self.assertRaises(VendorError) as captured:
            interface.route_to_vendor(
                "get_stock_data", "AAPL", "2026-01-01", "2026-01-10"
            )
        joined = "\n".join(cm.output) + str(captured.exception)
        self.assertNotIn(secret, joined)
        self.assertIn("ValueError", joined)
        self.assertIn("yfinance", joined)

    def test_unknown_configured_vendor_raises(self):
        set_config({"data_vendors": {"core_stock_apis": "bogus_vendor"}})
        with self.assertRaises(ValueError) as ctx:
            interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
        self.assertIn("bogus_vendor", str(ctx.exception))

    def test_default_sentinel_uses_all_vendors(self):
        # No explicit choice ("default") keeps the resilient full-chain behavior.
        set_config({"data_vendors": {"core_stock_apis": "default"}})
        with self._route({"yfinance": _no_data, "alpha_vantage": _returns("AV_DATA")}):
            result = interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
        self.assertEqual(result, "AV_DATA")

    def _route_method(self, method, vendors):
        return mock.patch.dict(interface.VENDOR_METHODS, {method: vendors}, clear=False)

    def test_optional_category_degrades_instead_of_raising(self):
        # An optional enrichment vendor (FRED macro) that raises must NOT abort
        # the run — the router returns a sentinel so the analysis proceeds.
        set_config({"data_vendors": {"macro_data": "fred"}})
        secret = "https://fred.invalid/?api_key=must-not-escape"
        with self._route_method(
            "get_macro_indicators", {"fred": _raises(ValueError(secret))}
        ), self.assertLogs(
            "tradingagents.dataflows.interface", level="WARNING"
        ) as captured:
            result = interface.route_to_vendor("get_macro_indicators", "cpi", "2026-01-01")
        self.assertIn("DATA_UNAVAILABLE", result)
        self.assertIn("macro_data", result)
        rendered = "\n".join(captured.output) + result
        self.assertNotIn(secret, rendered)
        self.assertIn("ValueError", rendered)

    def test_successful_fallback_does_not_emit_a_warning(self):
        set_config({"data_vendors": {"core_stock_apis": "yfinance,alpha_vantage"}})
        secret = "https://provider.invalid/?token=must-not-escape"
        with self._route(
            {"yfinance": _raises(ValueError(secret)), "alpha_vantage": _returns("OK")}
        ), mock.patch.object(interface.logger, "warning") as warning:
            result = interface.route_to_vendor(
                "get_stock_data", "AAPL", "2026-01-01", "2026-01-10"
            )

        self.assertEqual(result, "OK")
        warning.assert_not_called()

    def test_optional_rate_limit_degrades_instead_of_falling_through(self):
        set_config({"data_vendors": {"macro_data": "fred"}})
        with self._route_method(
            "get_macro_indicators",
            {"fred": _raises(VendorRateLimitError("opaque provider text"))},
        ):
            result = interface.route_to_vendor(
                "get_macro_indicators", "cpi", "2026-01-01"
            )
        self.assertIn("DATA_UNAVAILABLE", result)

    def test_core_category_still_raises_on_error(self):
        # A core category (single configured vendor) propagates the error so a
        # broken primary is loud, not silently degraded.
        set_config({"data_vendors": {"core_stock_apis": "yfinance"}})
        secret = "https://provider.invalid/?token=must-not-escape"
        with self._route({"yfinance": _raises(ValueError(secret))}), \
                self.assertRaises(VendorError) as captured:
            interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
        self.assertNotIn(secret, str(captured.exception))
        self.assertIn("ValueError", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
