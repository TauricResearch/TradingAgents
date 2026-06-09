import unittest

import pytest

from cli.utils import is_valid_ticker_symbol, normalize_ticker_symbol
from tradingagents.agents.utils.agent_utils import build_instrument_context


@pytest.mark.unit
class TickerSymbolHandlingTests(unittest.TestCase):
    def test_normalize_ticker_symbol_preserves_exchange_suffix(self):
        self.assertEqual(normalize_ticker_symbol(" cnc.to "), "CNC.TO")

    def test_cli_ticker_validation_accepts_yahoo_and_broker_symbols(self):
        for symbol in ("GC=F", "XAUUSD+", "EURUSD+", "^GSPC"):
            self.assertTrue(is_valid_ticker_symbol(symbol), symbol)

    def test_cli_ticker_validation_rejects_unsafe_symbols(self):
        for symbol in ("AAP L", "../AAPL", "AAPL\x00", "A" * 33):
            self.assertFalse(is_valid_ticker_symbol(symbol), symbol)

    def test_build_instrument_context_mentions_exact_symbol(self):
        context = build_instrument_context("7203.T")
        self.assertIn("7203.T", context)
        self.assertIn("exchange suffix", context)

    def test_single_get_ticker_no_shadow(self):
        # Regression: cli/main.py had a duplicate get_ticker with an empty
        # questionary prompt (rendered as a bare "?") that shadowed the
        # descriptive one in cli/utils. Keep a single canonical definition.
        import cli.main
        import cli.utils
        self.assertIs(cli.main.get_ticker, cli.utils.get_ticker)


if __name__ == "__main__":
    unittest.main()
