"""Tests that empty vendor results never become fabricated data.

Covers two systematic fixes:
  - load_ohlcv must not cache an empty download (cache poisoning), and must
    raise NoMarketDataError instead of returning an empty frame.
  - route_to_vendor must convert NoMarketDataError into a single explicit
    "NO_DATA_AVAILABLE" sentinel after all vendors are exhausted.
"""

import os
import unittest
from unittest import mock

import pandas as pd
import pytest

from tradingagents.dataflows import stockstats_utils, interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.symbol_utils import NoMarketDataError


@pytest.mark.unit
class TestLoadOhlcvNoPoison(unittest.TestCase):
    def setUp(self):
        self._tmp = os.path.join(os.path.dirname(__file__), "_tmp_cache")
        os.makedirs(self._tmp, exist_ok=True)
        set_config({"data_cache_dir": self._tmp})

    def tearDown(self):
        for f in os.listdir(self._tmp):
            os.remove(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_empty_download_raises_and_does_not_cache(self):
        empty = pd.DataFrame()
        with mock.patch.object(stockstats_utils.yf, "download", return_value=empty) as dl:
            with self.assertRaises(NoMarketDataError):
                stockstats_utils.load_ohlcv("FAKE", "2026-01-01")
        # Nothing should have been written to the cache.
        self.assertEqual(os.listdir(self._tmp), [])

        # A second call must re-attempt the fetch (no poisoned cache served).
        with mock.patch.object(stockstats_utils.yf, "download", return_value=empty) as dl2:
            with self.assertRaises(NoMarketDataError):
                stockstats_utils.load_ohlcv("FAKE", "2026-01-01")
            self.assertTrue(dl2.called)

    def test_download_window_matches_documented_cache_horizon(self):
        downloaded = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [101.0],
                "Low": [99.0],
                "Close": [100.5],
                "Volume": [1000],
            },
            index=pd.DatetimeIndex(["2025-01-02"], name="Date"),
        )

        with (
            mock.patch.object(stockstats_utils, "_today", return_value=pd.Timestamp("2026-01-15")),
            mock.patch.object(stockstats_utils.yf, "download", return_value=downloaded) as dl,
        ):
            stockstats_utils.load_ohlcv("AAPL", "2025-12-31")

        kwargs = dl.call_args.kwargs
        start = pd.Timestamp(kwargs["start"])
        end = pd.Timestamp(kwargs["end"])

        self.assertEqual(end, pd.Timestamp("2026-01-15"))
        self.assertGreaterEqual(
            (end - start).days,
            stockstats_utils.OHLCV_CACHE_YEARS * 365,
        )

    def test_cache_file_is_stable_across_days(self):
        downloaded = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [101.0],
                "Low": [99.0],
                "Close": [100.5],
                "Volume": [1000],
            },
            index=pd.DatetimeIndex(["2026-01-10"], name="Date"),
        )
        legacy_cache = os.path.join(
            self._tmp,
            "AAPL-YFin-data-2011-01-15-2026-01-15.csv",
        )
        with open(legacy_cache, "w", encoding="utf-8") as f:
            f.write("Date,Close\n2026-01-10,100.5\n")

        with (
            mock.patch.object(
                stockstats_utils,
                "_today",
                side_effect=[pd.Timestamp("2026-01-15"), pd.Timestamp("2026-01-16")],
            ),
            mock.patch.object(stockstats_utils.yf, "download", return_value=downloaded) as dl,
        ):
            stockstats_utils.load_ohlcv("AAPL", "2026-01-10")
            stockstats_utils.load_ohlcv("AAPL", "2026-01-10")

        self.assertEqual(dl.call_count, 1)
        self.assertEqual(os.listdir(self._tmp), ["AAPL-YFin-data-15y.csv"])


@pytest.mark.unit
class TestRouteToVendorSentinel(unittest.TestCase):
    def test_no_data_from_all_vendors_returns_sentinel(self):
        def raises_no_data(symbol, *a, **k):
            raise NoMarketDataError(symbol, "GC=F", "no rows")

        patched = {"yfinance": raises_no_data, "alpha_vantage": raises_no_data}
        with mock.patch.dict(
            interface.VENDOR_METHODS, {"get_stock_data": patched}, clear=False
        ):
            result = interface.route_to_vendor(
                "get_stock_data", "XAUUSD+", "2026-01-01", "2026-01-10"
            )
        self.assertIn("NO_DATA_AVAILABLE", result)
        self.assertIn("XAUUSD+", result)
        self.assertIn("GC=F", result)
        self.assertIn("Do not estimate", result)

    def test_unconfigured_fallback_does_not_mask_no_data(self):
        # When the primary vendor reports no data and the fallback is simply
        # unavailable (e.g. missing API key -> raises), the no-data sentinel
        # must win rather than the fallback's incidental error crashing out.
        def raises_no_data(symbol, *a, **k):
            raise NoMarketDataError(symbol, symbol, "no rows")

        def raises_unavailable(symbol, *a, **k):
            raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is not set.")

        patched = {"yfinance": raises_no_data, "alpha_vantage": raises_unavailable}
        with mock.patch.dict(
            interface.VENDOR_METHODS, {"get_stock_data": patched}, clear=False
        ):
            result = interface.route_to_vendor(
                "get_stock_data", "FAKE", "2026-01-01", "2026-01-10"
            )
        self.assertIn("NO_DATA_AVAILABLE", result)


if __name__ == "__main__":
    unittest.main()
