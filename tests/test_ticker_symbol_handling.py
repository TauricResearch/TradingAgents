import unittest

from cli.utils import normalize_ticker_symbol
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.instruments import get_asset_class, is_crypto_symbol


class TickerSymbolHandlingTests(unittest.TestCase):
    def test_normalize_ticker_symbol_preserves_exchange_suffix(self):
        self.assertEqual(normalize_ticker_symbol(" cnc.to "), "CNC.TO")

    def test_normalize_ticker_symbol_supports_crypto_slash_pair(self):
        self.assertEqual(normalize_ticker_symbol("eth/usdt"), "ETH-USD")

    def test_normalize_ticker_symbol_supports_crypto_concat_pair(self):
        self.assertEqual(normalize_ticker_symbol("btcusdt"), "BTC-USD")

    def test_normalize_ticker_symbol_supports_bare_crypto_base(self):
        self.assertEqual(normalize_ticker_symbol("btc"), "BTC-USD")
        self.assertEqual(normalize_ticker_symbol("ont"), "ONT-USD")

    def test_build_instrument_context_mentions_exact_symbol(self):
        context = build_instrument_context("7203.T")
        self.assertIn("7203.T", context)
        self.assertIn("exchange suffix", context)

    def test_build_instrument_context_mentions_crypto_pair_rules(self):
        context = build_instrument_context("BTC-USD")
        self.assertIn("BTC-USD", context)
        self.assertIn("cryptocurrency", context)
        self.assertIn("24/7", context)

    def test_get_asset_class_detects_crypto(self):
        self.assertEqual(get_asset_class("BTC-USD"), "crypto")
        self.assertTrue(is_crypto_symbol("ETH/USDT"))

    def test_get_asset_class_defaults_to_equity(self):
        self.assertEqual(get_asset_class("AAPL"), "equity")
        self.assertFalse(is_crypto_symbol("AAPL"))


if __name__ == "__main__":
    unittest.main()
