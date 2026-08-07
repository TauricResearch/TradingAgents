"""Cross-source price-basis caveat: when the agent prices on a non-yfinance
(unadjusted) vendor but reflection measures realized returns on yfinance
split/dividend-adjusted prices, the stored reflection must disclose the basis
difference so a raw-vs-adjusted artifact can't silently poison the memory log
(cross-source consistency guard).
"""
import unittest
from unittest import mock

import pandas as pd
import pytest

from tradingagents.dataflows.market_data_validator import build_verified_market_snapshot
from tradingagents.graph.trading_graph import TradingAgentsGraph


def _graph_with_vendor(core_vendor: str) -> TradingAgentsGraph:
    # Build a bare instance without running the full (LLM/graph) __init__ — the
    # caveat helper only reads self.config.
    g = object.__new__(TradingAgentsGraph)
    g.config = {"data_vendors": {"core_stock_apis": core_vendor}}
    return g


@pytest.mark.unit
class PriceBasisCaveatTests(unittest.TestCase):
    def test_yfinance_primary_has_no_caveat(self):
        self.assertEqual(_graph_with_vendor("yfinance")._price_basis_caveat(), "")

    def test_default_sentinel_has_no_caveat(self):
        self.assertEqual(_graph_with_vendor("default")._price_basis_caveat(), "")

    def test_empty_vendor_has_no_caveat(self):
        self.assertEqual(_graph_with_vendor("")._price_basis_caveat(), "")

    def test_schwab_primary_emits_caveat(self):
        note = _graph_with_vendor("schwab,yfinance")._price_basis_caveat()
        self.assertIn("schwab", note)
        self.assertIn("adjusted", note)

    def test_alpha_vantage_primary_emits_caveat(self):
        note = _graph_with_vendor("alpha_vantage")._price_basis_caveat()
        self.assertIn("alpha_vantage", note)

    def test_caveat_uses_first_vendor_in_chain(self):
        # The chain's primary determines the basis note, not later fallbacks.
        note = _graph_with_vendor("schwab,yfinance")._price_basis_caveat()
        self.assertIn("'schwab'", note)


@pytest.mark.unit
class SnapshotBasisDisclosureTests(unittest.TestCase):
    def test_snapshot_discloses_yfinance_adjusted_basis(self):
        dates = pd.date_range("2026-01-02", periods=10, freq="B")
        df = pd.DataFrame({
            "Date": dates,
            "Open": range(100, 110),
            "High": range(101, 111),
            "Low": range(99, 109),
            "Close": range(100, 110),
            "Volume": [1_000_000] * 10,
        })
        with mock.patch(
            "tradingagents.dataflows.market_data_validator.load_ohlcv",
            return_value=df,
        ):
            out = build_verified_market_snapshot("AAPL", "2026-01-15")
        self.assertIn("yfinance split/dividend-adjusted", out)


if __name__ == "__main__":
    unittest.main()
