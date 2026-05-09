import unittest
from unittest.mock import patch

import pytest

from cli.utils import normalize_ticker_symbol
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.dataflows import y_finance


@pytest.mark.unit
class TickerSymbolHandlingTests(unittest.TestCase):
    def setUp(self):
        y_finance.get_instrument_metadata.cache_clear()

    def test_normalize_ticker_symbol_preserves_exchange_suffix(self):
        self.assertEqual(normalize_ticker_symbol(" cnc.to "), "CNC.TO")

    def test_build_instrument_context_mentions_exact_symbol(self):
        with patch.object(y_finance, "get_instrument_metadata", return_value=None):
            context = build_instrument_context("7203.T")
        self.assertIn("7203.T", context)
        self.assertIn("exchange suffix", context)

    def test_build_instrument_context_includes_resolved_company_identity(self):
        metadata = {
            "name": "Naspers Limited",
            "exchange": "Johannesburg Stock Exchange",
            "quote_type": "EQUITY",
            "currency": "ZAR",
        }
        with patch.object(y_finance, "get_instrument_metadata", return_value=metadata):
            context = build_instrument_context("NPN.JO")
        self.assertIn("NPN.JO", context)
        self.assertIn("Naspers Limited", context)
        self.assertIn("Johannesburg Stock Exchange", context)
        self.assertIn("ZAR", context)
        self.assertNotIn("Nornickel", context)
        self.assertNotIn("Oslo", context)

    def test_build_instrument_context_falls_back_when_lookup_fails(self):
        with patch.object(y_finance, "get_instrument_metadata", return_value=None):
            context = build_instrument_context("UNKNOWN.XX")
        self.assertIn("UNKNOWN.XX", context)
        self.assertNotIn("This ticker refers to", context)


if __name__ == "__main__":
    unittest.main()
