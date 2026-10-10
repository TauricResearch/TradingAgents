"""Regression coverage for the web ticker endpoint's shared dataflow imports."""

import unittest
from datetime import date
from importlib.util import find_spec
from unittest.mock import patch

from tradingagents.dataflows.errors import NoMarketDataError

# The web UI dependencies are optional for the core CLI test suite.
if find_spec("fastapi") and find_spec("httpx"):
    from fastapi.testclient import TestClient

    from webui.backend.app import app
else:
    TestClient = None


@unittest.skipIf(TestClient is None, "Web UI tests require FastAPI and httpx")
class TestWebTickerValidation(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        loader_patch = patch(
            "tradingagents.dataflows.vendors.yahoo.ohlcv.load_ohlcv",
            return_value=[{"Close": 100.0}],
        )
        self.loader = loader_patch.start()
        self.addCleanup(loader_patch.stop)

    def test_existing_ticker_returns_json_instead_of_import_error(self):
        response = self.client.get("/api/validate", params={"symbol": " aapl "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "canonical": "AAPL", "rows": 1})
        self.loader.assert_called_once_with(
            "AAPL", date.today().isoformat(), fill_gaps=False
        )

    def test_vendor_aliases_use_shared_normalization(self):
        for symbol, canonical in (
            ("BTCUSDT", "BTC-USD"),
            ("700.HK", "0700.HK"),
            ("600519.SH", "600519.SS"),
            ("XAUUSD+", "GC=F"),
            ("EURUSD", "EURUSD=X"),
            ("RELIANCE.NS", "RELIANCE.NS"),
        ):
            with self.subTest(symbol=symbol):
                response = self.client.get("/api/validate", params={"symbol": symbol})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["canonical"], canonical)

    def test_empty_input_skips_price_lookup(self):
        response = self.client.get("/api/validate", params={"symbol": "  "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": False, "message": "Enter a ticker symbol."})
        self.loader.assert_not_called()

    def test_invalid_input_skips_price_lookup(self):
        for symbol in ("../AAPL", "AAPL/MSFT", "AAPL?", "...", "A" * 33):
            with self.subTest(symbol=symbol):
                response = self.client.get("/api/validate", params={"symbol": symbol})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()["ok"])
                self.assertIn("valid symbol format", response.json()["message"])
        self.loader.assert_not_called()

    def test_bare_exchange_suffix_has_specific_message(self):
        response = self.client.get("/api/validate", params={"symbol": ".NS"})
        self.assertFalse(response.json()["ok"])
        self.assertIn("only an exchange suffix", response.json()["message"])
        self.loader.assert_not_called()

    def test_empty_vendor_data_returns_validation_failure(self):
        for rows in (None, []):
            with self.subTest(rows=rows):
                self.loader.return_value = rows
                response = self.client.get("/api/validate", params={"symbol": "UNKNOWN"})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()["ok"])

    def test_missing_price_data_preserves_ticker_suggestion(self):
        self.loader.side_effect = NoMarketDataError("RELIANCE", "RELIANCE", "no rows")
        response = self.client.get("/api/validate", params={"symbol": "RELIANCE"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["suggestion"], "RELIANCE.NS")
        self.assertIn("Did you mean", response.json()["message"])


if __name__ == "__main__":
    unittest.main()
