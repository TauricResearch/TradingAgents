import unittest

import pytest

from cli.utils import normalize_ticker_symbol
from tradingagents.agents.utils.agent_utils import build_instrument_context


@pytest.mark.unit
class TickerSymbolHandlingTests(unittest.TestCase):
    def test_normalize_ticker_symbol_preserves_exchange_suffix(self):
        self.assertEqual(normalize_ticker_symbol(" cnc.to "), "CNC.TO")

    def test_normalize_ticker_symbol_infers_a_share_suffix(self):
        self.assertEqual(normalize_ticker_symbol("002636"), "002636.SZ")
        self.assertEqual(normalize_ticker_symbol("002636SZ"), "002636.SZ")
        self.assertEqual(normalize_ticker_symbol("600519"), "600519.SS")
        self.assertEqual(normalize_ticker_symbol("688981.SH"), "688981.SS")
        self.assertEqual(normalize_ticker_symbol("430047"), "430047.BJ")

    def test_build_instrument_context_mentions_exact_symbol(self):
        context = build_instrument_context("002636.SZ")
        self.assertIn("002636.SZ", context)
        self.assertIn("exchange suffix", context)


if __name__ == "__main__":
    unittest.main()
