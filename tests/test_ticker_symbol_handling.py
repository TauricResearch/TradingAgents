import unittest

import pytest

from cli.utils import normalize_ticker_symbol
from tradingagents.agents.utils.agent_utils import build_instrument_context


@pytest.mark.unit
class TickerSymbolHandlingTests(unittest.TestCase):
    def test_normalize_ticker_symbol_preserves_exchange_suffix(self):
        self.assertEqual(normalize_ticker_symbol(" cnc.to "), "CNC.TO")

    def test_build_instrument_context_mentions_exact_symbol(self):
        contract_id = "KXBTCD-26MAY05-T100000"
        context = build_instrument_context(contract_id)
        self.assertIn(contract_id, context)
        self.assertIn("Kalshi contract", context)


if __name__ == "__main__":
    unittest.main()
