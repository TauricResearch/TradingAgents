import unittest

from tradingagents.instruments import (
    get_asset_class,
    is_crypto_symbol,
    normalize_instrument_symbol,
)


class InstrumentSymbolTests(unittest.TestCase):
    def test_preserves_exchange_suffix(self):
        self.assertEqual(normalize_instrument_symbol(" cnc.to "), "CNC.TO")

    def test_normalizes_slash_pair(self):
        self.assertEqual(normalize_instrument_symbol("eth/usdt"), "ETH-USD")

    def test_normalizes_concat_pair(self):
        self.assertEqual(normalize_instrument_symbol("BTCUSDT"), "BTC-USD")

    def test_normalizes_bare_major_crypto(self):
        self.assertEqual(normalize_instrument_symbol("btc"), "BTC-USD")
        self.assertEqual(normalize_instrument_symbol("ont"), "ONT-USD")

    def test_detects_crypto_asset_class(self):
        self.assertTrue(is_crypto_symbol("ETH/USDT"))
        self.assertEqual(get_asset_class("BTC"), "crypto")

    def test_keeps_equity_asset_class(self):
        self.assertFalse(is_crypto_symbol("AAPL"))
        self.assertEqual(get_asset_class("AAPL"), "equity")


if __name__ == "__main__":
    unittest.main()
