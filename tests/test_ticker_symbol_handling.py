import unittest

import pytest

from cli.models import AssetType
from cli.utils import detect_market_region, normalize_ticker_symbol
from tradingagents.agents.utils.agent_utils import build_instrument_context


@pytest.mark.unit
class TickerSymbolHandlingTests(unittest.TestCase):
    def test_normalize_ticker_symbol_preserves_exchange_suffix(self):
        self.assertEqual(normalize_ticker_symbol(" cnc.to "), "CNC.TO")

    def test_normalize_ticker_symbol_infers_a_share_exchange(self):
        self.assertEqual(normalize_ticker_symbol("600519"), "600519.SH")
        self.assertEqual(normalize_ticker_symbol("sz000001"), "000001.SZ")

    def test_build_instrument_context_mentions_exact_symbol(self):
        context = build_instrument_context("7203.T")
        self.assertIn("7203.T", context)
        self.assertIn("exchange suffix", context)

    def test_detect_market_region_identifies_a_share(self):
        self.assertEqual(detect_market_region("600519"), "cn_a")
        self.assertEqual(detect_market_region("000001.SZ", AssetType.STOCK), "cn_a")
        self.assertEqual(detect_market_region("SPY"), "us")


if __name__ == "__main__":
    unittest.main()
