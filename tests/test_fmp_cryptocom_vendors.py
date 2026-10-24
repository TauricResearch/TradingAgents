"""FMP and Crypto.com vendors: symbol spelling, error typing, settled bars, routing."""

import time
import unittest
from unittest import mock

import pandas as pd

from tradingagents.dataflows import router
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.vendors import cryptocom, fmp
from tradingagents.default_config import build_default_config

DAY_MS = 86_400_000


def _resp(status=200, body=None):
    r = mock.Mock(status_code=status, content=b"x")
    r.json.return_value = body
    return r


def _fmp_rows(n=260, end="2026-10-23"):
    days = pd.bdate_range(end=end, periods=n)
    return [{"date": d.strftime("%Y-%m-%d"), "open": 100 + i, "high": 101 + i, "low": 99 + i,
             "close": 100.5 + i, "volume": 1000} for i, d in enumerate(reversed(days))]


class FmpSymbolTests(unittest.TestCase):
    def test_spells_each_asset_class_the_fmp_way(self):
        self.assertEqual(fmp.fmp_symbol("AAPL"), "AAPL")
        self.assertEqual(fmp.fmp_symbol("^GSPC"), "^GSPC")
        self.assertEqual(fmp.fmp_symbol("SPX500"), "^GSPC")
        self.assertEqual(fmp.fmp_symbol("EURUSD"), "EURUSD")
        self.assertEqual(fmp.fmp_symbol("EURUSD=X"), "EURUSD")
        self.assertEqual(fmp.fmp_symbol("XAUUSD+"), "GCUSD")
        self.assertEqual(fmp.fmp_symbol("GC=F"), "GCUSD")
        self.assertEqual(fmp.fmp_symbol("brent"), "BZUSD")
        self.assertEqual(fmp.fmp_symbol("BTC-USD"), "BTCUSD")


class FmpVendorTests(unittest.TestCase):
    def test_missing_key_is_not_configured(self):
        with mock.patch.dict("os.environ", {"FMP_API_KEY": ""}), self.assertRaises(VendorNotConfiguredError):
            fmp.get_stock_data("AAPL", "2026-10-01", "2026-10-23")

    def test_plan_gated_symbol_is_no_data_not_a_crash(self):
        body = {"Error Message": "Premium Query Parameter: requires a higher plan."}
        with (
            mock.patch.dict("os.environ", {"FMP_API_KEY": "k"}),
            mock.patch("tradingagents.dataflows.vendors.fmp.get_scrubbed", return_value=_resp(402, body)),
            self.assertRaises(NoMarketDataError) as ctx,
        ):
            fmp.get_stock_data("^STI", "2026-10-01", "2026-10-23")
        self.assertIn("higher plan", str(ctx.exception))

    def test_plan_gated_plain_text_body_is_no_data(self):
        # What FMP really sends for a symbol outside the plan: 402, labelled JSON, plain text.
        r = mock.Mock(status_code=402, content=b"x", text="Premium Query Parameter: not available under your current subscription")
        r.json.side_effect = ValueError("Expecting value")
        with (
            mock.patch.dict("os.environ", {"FMP_API_KEY": "k"}),
            mock.patch("tradingagents.dataflows.vendors.fmp.get_scrubbed", return_value=r),
            self.assertRaises(NoMarketDataError) as ctx,
        ):
            fmp.get_stock_data("^STI", "2026-10-01", "2026-10-23")
        self.assertIn("current subscription", str(ctx.exception))

    def test_rate_limit_is_unavailable(self):
        with (
            mock.patch.dict("os.environ", {"FMP_API_KEY": "k"}),
            mock.patch("tradingagents.dataflows.vendors.fmp.get_scrubbed", return_value=_resp(429, {})),
            self.assertRaises(VendorUnavailableError),
        ):
            fmp.get_stock_data("AAPL", "2026-10-01", "2026-10-23")

    def test_rows_come_back_oldest_first_within_range(self):
        with mock.patch.dict("os.environ", {"FMP_API_KEY": "k"}), \
             mock.patch("tradingagents.dataflows.vendors.fmp.get_scrubbed", return_value=_resp(200, _fmp_rows())):
            out = fmp.get_stock_data("AAPL", "2026-10-20", "2026-10-23")
        lines = out.strip().splitlines()
        self.assertIn("source: Financial Modeling Prep", lines[0])
        self.assertEqual(lines[3], "Date,Open,High,Low,Close,Volume")
        self.assertEqual([line.split(",")[0] for line in lines[4:]], ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"])

    def test_indicator_ignores_bars_after_the_analysis_date(self):
        with mock.patch.dict("os.environ", {"FMP_API_KEY": "k"}), \
             mock.patch("tradingagents.dataflows.vendors.fmp.get_scrubbed", return_value=_resp(200, _fmp_rows())):
            out = fmp.get_indicators("AAPL", "close_10_ema", "2026-10-21", 1)
        self.assertIn("2026-10-21:", out)
        self.assertNotIn("2026-10-22:", out)


class CryptoComVendorTests(unittest.TestCase):
    def test_instrument_names(self):
        self.assertEqual(cryptocom.instrument("BTC-USD"), "BTC_USD")
        self.assertEqual(cryptocom.instrument("ethusdt"), "ETH_USD")
        self.assertIsNone(cryptocom.instrument("AAPL"))

    def test_non_crypto_is_no_data_so_the_chain_moves_on(self):
        with self.assertRaises(NoMarketDataError):
            cryptocom.get_stock_data("AAPL", "2026-10-01", "2026-10-23")

    def test_drops_the_day_still_trading_and_pages_back(self):
        today = int(time.time() * 1000) // DAY_MS * DAY_MS
        candles = [{"t": today - i * DAY_MS, "o": "1", "h": "2", "l": "0.5", "c": str(100 + i), "v": "3"}
                   for i in range(0, 600)]
        pages = [candles[0:300], candles[300:600], []]

        def fake_get(url, params, timeout):
            return _resp(200, {"code": 0, "result": {"data": pages.pop(0)}})

        with mock.patch("tradingagents.dataflows.vendors.cryptocom.requests.get", side_effect=fake_get), \
             mock.patch("tradingagents.dataflows.vendors.cryptocom.time.sleep"):
            df, name = cryptocom.load_daily("BTC-USD")
        self.assertEqual(name, "BTC_USD")
        self.assertEqual(df["Date"].max(), pd.Timestamp(today - DAY_MS, unit="ms").normalize())
        self.assertGreater(len(df), 300)
        self.assertTrue(df["Date"].is_monotonic_increasing)


class RoutingTests(unittest.TestCase):
    def tearDown(self):
        set_config(build_default_config())

    def test_vendor_chain_from_environment(self):
        with mock.patch.dict("os.environ", {"TRADINGAGENTS_VENDOR_CORE_STOCK_APIS": "cryptocom,fmp,yfinance"}):
            cfg = build_default_config()
        self.assertEqual(cfg["data_vendors"]["core_stock_apis"], "cryptocom,fmp,yfinance")
        self.assertEqual(cfg["data_vendors"]["technical_indicators"], "yfinance")

    def test_stock_skips_cryptocom_and_unkeyed_fmp(self):
        set_config({"data_vendors": {"core_stock_apis": "cryptocom,fmp,yfinance"}})
        served = mock.Mock(return_value="yahoo rows")
        with mock.patch.dict("os.environ", {"FMP_API_KEY": ""}), \
             mock.patch.dict(router.VENDOR_METHODS["get_stock_data"], {"yfinance": served}):
            self.assertEqual(router.route_to_vendor("get_stock_data", "AAPL", "2026-10-01", "2026-10-23"), "yahoo rows")


if __name__ == "__main__":
    unittest.main()
