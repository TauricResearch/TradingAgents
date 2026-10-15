"""Unit tests for the no-premium Alpha Vantage daily OHLCV fallback."""
import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors.alpha_vantage.common import (
    AlphaVantagePremiumEndpointError,
    AlphaVantageRateLimitError,
)
from tradingagents.dataflows.vendors.alpha_vantage import stock
from tradingagents.dataflows.vendors.alpha_vantage import common
from tradingagents.dataflows.vendors.yahoo import market
from tradingagents.dataflows.errors import NoMarketDataError


class AlphaVantageFallbackTests(unittest.TestCase):
    def test_yahoo_rejects_requested_latest_bar_without_close_to_allow_fallback(self):
        frame = pd.DataFrame(
            {
                "Open": [10.0, 11.0],
                "High": [11.0, 12.0],
                "Low": [9.0, 10.0],
                "Close": [10.5, float("nan")],
                "Adj Close": [10.5, float("nan")],
                "Volume": [100, 110],
            },
            index=pd.to_datetime(["2026-10-08", "2026-10-09"]),
        )
        ticker = SimpleNamespace(history=lambda **kwargs: frame.copy())
        with patch.object(market.yf, "Ticker", return_value=ticker), patch.object(
            market, "yf_retry", side_effect=lambda func: func()
        ):
            with self.assertRaisesRegex(NoMarketDataError, "missing Close"):
                market.get_YFin_data_online("RHM.DE", "2026-10-08", "2026-10-09")

    def test_provider_symbol_comes_from_instrument_registry(self):
        registry = {
            "schema_version": 1,
            "instruments": {
                "RHM.DE": {
                    "ticker": "RHM.DE",
                    "isin": "DE0007030009",
                    "mic": "XETR",
                    "alpha_vantage_symbol": "RHM.DEX",
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with patch.object(stock, "get_config", return_value={"issuer_registry_path": str(path)}):
                self.assertEqual(stock._resolve_symbol("RHM.DE"), "RHM.DEX")

    def test_yfinance_is_followed_by_alpha_vantage_for_stock_history(self):
        from tradingagents.default_config import DEFAULT_CONFIG

        self.assertEqual(
            DEFAULT_CONFIG["data_vendors"]["core_stock_apis"],
            "yfinance,alpha_vantage",
        )

    def test_premium_entitlement_notice_is_not_misclassified_as_rate_limit(self):
        class Response:
            text = '{"Information":"This is a premium endpoint"}'

        with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "test-secret"}), patch.object(
            common, "get_scrubbed", return_value=Response()
        ):
            with self.assertRaises(AlphaVantagePremiumEndpointError) as raised:
                common._make_api_request("TIME_SERIES_DAILY_ADJUSTED", {"symbol": "RHM.DEX"})
        self.assertNotIsInstance(raised.exception, AlphaVantageRateLimitError)

    def test_adjusted_endpoint_premium_gate_falls_back_to_unadjusted_daily(self):
        daily_csv = (
            "timestamp,open,high,low,close,volume\n"
            "2026-10-10,11,13,10,12,120\n"
            "2026-10-09,10,12,9,11,100\n"
            "2026-10-08,9,11,8,10,90\n"
        )
        with patch.object(
            stock,
            "_make_api_request",
            side_effect=[
                AlphaVantagePremiumEndpointError("TIME_SERIES_DAILY_ADJUSTED is a premium endpoint"),
                daily_csv,
            ],
        ) as request:
            result = stock.get_stock("RHM.DEX", "2026-10-08", "2026-10-09")

        self.assertIn("unadjusted", result.lower())
        self.assertIn("TIME_SERIES_DAILY", result)
        self.assertIn("2026-10-09", result)
        self.assertIn("2026-10-08,9,11,8,10,90", result)
        self.assertNotIn("2026-10-10", result)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[0], "TIME_SERIES_DAILY_ADJUSTED")
        self.assertEqual(request.call_args_list[1].args[0], "TIME_SERIES_DAILY")

    def test_non_premium_vendor_failure_does_not_trigger_second_request(self):
        with patch.object(
            stock,
            "_make_api_request",
            side_effect=VendorUnavailableError("API request timed out"),
        ) as request:
            with self.assertRaisesRegex(VendorUnavailableError, "timed out"):
                stock.get_stock("RHM.DEX", "2026-10-08", "2026-10-09")
        request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
