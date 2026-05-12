import unittest
from unittest.mock import patch

import pytest

from cli.utils import normalize_ticker_symbol
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_instrument_context_from_state,
    resolve_instrument_identity,
)


@pytest.mark.unit
class TickerSymbolHandlingTests(unittest.TestCase):
    def setUp(self):
        resolve_instrument_identity.cache_clear()

    def test_normalize_ticker_symbol_preserves_exchange_suffix(self):
        self.assertEqual(normalize_ticker_symbol(" cnc.to "), "CNC.TO")

    def test_build_instrument_context_mentions_exact_symbol(self):
        context = build_instrument_context("7203.T")
        self.assertIn("7203.T", context)
        self.assertIn("exchange suffix", context)

    def test_build_instrument_context_includes_resolved_identity(self):
        context = build_instrument_context(
            "TOTDY",
            {
                "company_name": "TOTO LTD.",
                "sector": "Industrials",
                "industry": "Building Products & Equipment",
                "exchange": "PNK",
                "quote_type": "EQUITY",
            },
        )

        self.assertIn("TOTDY", context)
        self.assertIn("Company: TOTO LTD.", context)
        self.assertIn(
            "Business classification: Industrials / Building Products & Equipment",
            context,
        )
        self.assertIn("Exchange: PNK", context)
        self.assertIn("Do not substitute a different company or ticker", context)

    def test_get_instrument_context_from_state_prefers_precomputed_context(self):
        state = {
            "company_of_interest": "TOTDY",
            "instrument_context": "precomputed identity context",
        }

        self.assertEqual(
            get_instrument_context_from_state(state),
            "precomputed identity context",
        )

    def test_resolve_instrument_identity_uses_yfinance_metadata(self):
        with patch("tradingagents.agents.utils.agent_utils.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = {
                "longName": "TOTO LTD.",
                "shortName": "TOTO",
                "sector": "Industrials",
                "industry": "Building Products & Equipment",
                "exchange": "PNK",
                "quoteType": "EQUITY",
            }

            identity = resolve_instrument_identity("totdy")

        mock_ticker.assert_called_once_with("TOTDY")
        self.assertEqual(
            identity,
            {
                "company_name": "TOTO LTD.",
                "sector": "Industrials",
                "industry": "Building Products & Equipment",
                "exchange": "PNK",
                "quote_type": "EQUITY",
            },
        )

    def test_resolve_instrument_identity_caches_yfinance_metadata(self):
        with patch("tradingagents.agents.utils.agent_utils.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = {
                "longName": "TOTO LTD.",
                "sector": "Industrials",
            }

            first_identity = resolve_instrument_identity("TOTDY")
            second_identity = resolve_instrument_identity("TOTDY")

        mock_ticker.assert_called_once_with("TOTDY")
        self.assertEqual(first_identity, second_identity)

    def test_resolve_instrument_identity_fails_open(self):
        with patch(
            "tradingagents.agents.utils.agent_utils.yf.Ticker",
            side_effect=RuntimeError("rate limited"),
        ):
            self.assertEqual(resolve_instrument_identity("TOTDY"), {})


if __name__ == "__main__":
    unittest.main()
