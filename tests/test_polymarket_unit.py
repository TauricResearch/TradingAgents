"""Unit tests for tradingagents.signals.polymarket (task 4, spec 034).

Covers:
- Mock Gamma API responses → fetch_polymarket_signals
- ≥40% probability filtering
- Volume filtering (≥$100k)
- Category classification (_is_relevant)
- Sector mapping (map_signals_to_tickers)
- format_signals_text output
- Graceful fallback on API failure (supplements test_polymarket_graceful.py)

Run with:
    python -m pytest tests/test_polymarket_unit.py -v
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from tradingagents.signals.polymarket import (
    PolymarketSignal,
    _extract_probability,
    _filter_relevant,
    _is_relevant,
    fetch_polymarket_signals,
    format_signals_text,
    map_signals_to_tickers,
)


def _make_market(question: str, prob: float = 0.65, volume: float = 500_000, end_date: str = "2026-06-30") -> dict:
    """Build a minimal Gamma API market dict."""
    return {
        "question": question,
        "outcomePrices": json.dumps([str(prob), str(round(1 - prob, 2))]),
        "volumeNum": volume,
        "volume": volume,
        "endDate": end_date,
        "active": True,
        "closed": False,
    }


class TestProbabilityFiltering(unittest.TestCase):
    """Verify ≥40% probability threshold."""

    def test_above_threshold_included(self):
        markets = [_make_market("Will the Fed cut rates in June 2026?", prob=0.72, volume=2_000_000)]
        signals = _filter_relevant(markets, max_signals=10)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["probability"], 0.72)

    def test_exactly_40_included(self):
        markets = [_make_market("Will inflation exceed 4%?", prob=0.40)]
        signals = _filter_relevant(markets, max_signals=10)
        self.assertEqual(len(signals), 1)

    def test_below_40_excluded(self):
        markets = [_make_market("Will the Fed cut rates?", prob=0.39)]
        signals = _filter_relevant(markets, max_signals=10)
        self.assertEqual(len(signals), 0)

    def test_mixed_probabilities(self):
        markets = [
            _make_market("Fed rate cut June?", prob=0.80, volume=3_000_000),
            _make_market("Recession by Q3?", prob=0.25, volume=1_000_000),
            _make_market("CPI above 3%?", prob=0.55, volume=500_000),
        ]
        signals = _filter_relevant(markets, max_signals=10)
        self.assertEqual(len(signals), 2)
        probs = {s["probability"] for s in signals}
        self.assertEqual(probs, {0.80, 0.55})


class TestVolumeFiltering(unittest.TestCase):
    """Verify ≥$100k volume threshold."""

    def test_below_volume_excluded(self):
        markets = [_make_market("Fed rate cut?", prob=0.60, volume=50_000)]
        signals = _filter_relevant(markets, max_signals=10)
        self.assertEqual(len(signals), 0)

    def test_above_volume_included(self):
        markets = [_make_market("Fed rate cut?", prob=0.60, volume=200_000)]
        signals = _filter_relevant(markets, max_signals=10)
        self.assertEqual(len(signals), 1)


class TestCategoryClassification(unittest.TestCase):
    """Verify _is_relevant keyword → category mapping."""

    def test_fed_rates(self):
        self.assertEqual(_is_relevant("Will the Fed cut rates in June?"), "Fed/Rates")
        self.assertEqual(_is_relevant("Federal Reserve rate hike"), "Fed/Rates")

    def test_economy(self):
        self.assertEqual(_is_relevant("US GDP growth above 3%?"), "Economy")
        self.assertEqual(_is_relevant("Will unemployment rise?"), "Economy")
        self.assertEqual(_is_relevant("CPI above 4%?"), "Economy")

    def test_trade(self):
        self.assertEqual(_is_relevant("New tariff on China imports?"), "Trade")
        self.assertEqual(_is_relevant("Trade war escalation?"), "Trade")

    def test_regulation(self):
        self.assertEqual(_is_relevant("FTC antitrust action against Big Tech?"), "Regulation")

    def test_corporate(self):
        self.assertEqual(_is_relevant("NVDA earnings beat Q2?"), "Corporate")

    def test_crypto(self):
        self.assertEqual(_is_relevant("Bitcoin above $100k by July?"), "Crypto")

    def test_energy(self):
        self.assertEqual(_is_relevant("Crude oil above $90?"), "Energy")

    def test_tech(self):
        self.assertEqual(_is_relevant("Semiconductor shortage continues?"), "Tech")
        self.assertEqual(_is_relevant("AI chip demand surges?"), "Tech")

    def test_ai_regulation_categorized_as_regulation(self):
        """'AI regulation' matches Regulation before Tech (first-match priority)."""
        self.assertEqual(_is_relevant("Will AI regulation pass?"), "Regulation")

    def test_irrelevant_returns_none(self):
        self.assertIsNone(_is_relevant("Who wins the Super Bowl?"))
        self.assertIsNone(_is_relevant("Will it rain tomorrow?"))


class TestExtractProbability(unittest.TestCase):

    def test_outcome_prices_json_string(self):
        m = {"outcomePrices": '["0.72","0.28"]'}
        self.assertAlmostEqual(_extract_probability(m), 0.72)

    def test_outcome_prices_list(self):
        m = {"outcomePrices": [0.55, 0.45]}
        self.assertAlmostEqual(_extract_probability(m), 0.55)

    def test_fallback_to_best_bid(self):
        m = {"bestBid": "0.60"}
        self.assertAlmostEqual(_extract_probability(m), 0.60)

    def test_no_price_returns_zero(self):
        self.assertEqual(_extract_probability({}), 0.0)


class TestSectorMapping(unittest.TestCase):
    """Verify map_signals_to_tickers maps categories to held tickers."""

    def test_fed_rates_maps_to_tech_and_financials(self):
        signals: list[PolymarketSignal] = [
            {"event": "Fed cuts rates June 2026", "probability": 0.72, "volume": "$2.1M", "category": "Fed/Rates", "end_date": "2026-06-30"},
        ]
        held = {"MSFT", "JPM", "NKE"}
        mapping = map_signals_to_tickers(signals, held)
        self.assertIn(0, mapping)
        tickers = mapping[0]
        self.assertIn("MSFT", tickers)  # rates-sensitive tech
        self.assertIn("JPM", tickers)   # financials
        self.assertNotIn("NKE", tickers)  # not in rates/financials sectors

    def test_trade_maps_to_supply_chain(self):
        signals: list[PolymarketSignal] = [
            {"event": "New tariff on China imports", "probability": 0.55, "volume": "$1M", "category": "Trade", "end_date": "2026-12-31"},
        ]
        held = {"AAPL", "NVDA", "DIS"}
        mapping = map_signals_to_tickers(signals, held)
        self.assertIn(0, mapping)
        self.assertIn("AAPL", mapping[0])
        self.assertIn("NVDA", mapping[0])
        self.assertNotIn("DIS", mapping[0])

    def test_no_held_tickers_match(self):
        signals: list[PolymarketSignal] = [
            {"event": "Bitcoin above $100k", "probability": 0.60, "volume": "$5M", "category": "Crypto", "end_date": "2026-12-31"},
        ]
        held = {"NVDA", "MSFT"}  # no crypto tickers
        mapping = map_signals_to_tickers(signals, held)
        # Crypto category doesn't map to NVDA/MSFT
        self.assertEqual(mapping.get(0, []), [])

    def test_direct_ticker_mention_in_event(self):
        signals: list[PolymarketSignal] = [
            {"event": "NVDA earnings beat Q2 2026", "probability": 0.65, "volume": "$3M", "category": "Corporate", "end_date": "2026-07-31"},
        ]
        held = {"NVDA", "AAPL"}
        mapping = map_signals_to_tickers(signals, held)
        self.assertIn(0, mapping)
        self.assertIn("NVDA", mapping[0])

    def test_keyword_override_tariff(self):
        """Event keyword 'tariff' should map to trade sector even if category is Macro."""
        signals: list[PolymarketSignal] = [
            {"event": "New tariff announced on semiconductors", "probability": 0.50, "volume": "$1M", "category": "Macro", "end_date": "2026-12-31"},
        ]
        held = {"AAPL", "NVDA"}
        mapping = map_signals_to_tickers(signals, held)
        self.assertIn(0, mapping)
        # tariff keyword → trade sector → AAPL, NVDA
        self.assertIn("AAPL", mapping[0])
        self.assertIn("NVDA", mapping[0])


class TestFetchWithMockAPI(unittest.TestCase):
    """End-to-end fetch_polymarket_signals with mocked Gamma API."""

    @patch("tradingagents.signals.polymarket._fetch_active_markets")
    def test_returns_filtered_signals(self, mock_fetch):
        mock_fetch.return_value = [
            _make_market("Fed rate cut June 2026?", prob=0.72, volume=2_000_000),
            _make_market("Will it snow in Miami?", prob=0.05, volume=10_000),  # irrelevant + low prob + low vol
            _make_market("Bitcoin above $100k?", prob=0.55, volume=500_000),
        ]
        result = fetch_polymarket_signals(max_signals=10)
        self.assertIn("signals", result)
        self.assertIn("fetched_at", result)
        # Only Fed and Bitcoin should pass (relevant + ≥40% + ≥$100k)
        self.assertEqual(len(result["signals"]), 2)
        events = {s["event"] for s in result["signals"]}
        self.assertIn("Fed rate cut June 2026?", events)
        self.assertIn("Bitcoin above $100k?", events)

    @patch("tradingagents.signals.polymarket._fetch_active_markets")
    def test_max_signals_respected(self, mock_fetch):
        mock_fetch.return_value = [
            _make_market(f"Fed rate cut scenario {i}?", prob=0.60, volume=500_000 + i * 100_000)
            for i in range(10)
        ]
        result = fetch_polymarket_signals(max_signals=3)
        self.assertLessEqual(len(result["signals"]), 3)

    @patch("tradingagents.signals.polymarket._fetch_active_markets")
    def test_sorted_by_volume_descending(self, mock_fetch):
        mock_fetch.return_value = [
            _make_market("Fed rate cut?", prob=0.60, volume=200_000),
            _make_market("Recession risk?", prob=0.50, volume=5_000_000),
            _make_market("Inflation above 4%?", prob=0.45, volume=1_000_000),
        ]
        result = fetch_polymarket_signals(max_signals=10)
        signals = result["signals"]
        self.assertEqual(len(signals), 3)
        # Highest volume first
        self.assertEqual(signals[0]["event"], "Recession risk?")


class TestFormatSignalsText(unittest.TestCase):

    def test_empty_signals(self):
        self.assertEqual(format_signals_text({"signals": [], "fetched_at": ""}), "")

    def test_formats_correctly(self):
        result = {
            "signals": [
                {"event": "Fed cuts rates", "probability": 0.72, "volume": "$2.1M", "category": "Fed/Rates", "end_date": "2026-06-30"},
            ],
            "fetched_at": "2026-04-21T00:00:00Z",
        }
        text = format_signals_text(result)
        self.assertIn("Fed cuts rates", text)
        self.assertIn("72%", text)
        self.assertIn("$2.1M", text)
        self.assertIn("Fed/Rates", text)
        self.assertIn("prediction market", text.lower())


if __name__ == "__main__":
    unittest.main()
