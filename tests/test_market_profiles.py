"""Tests for suffix-based market identification (Taiwan Adapter step 2)."""

import unittest

import pytest

from tradingagents.dataflows.market_profiles import (
    MARKET_DEFAULT,
    MARKET_TAIWAN,
    get_market_profile,
    resolve_market,
)
from tradingagents.default_config import DEFAULT_CONFIG


@pytest.mark.unit
class ResolveMarketTests(unittest.TestCase):
    def test_taiwan_tickers_resolve_to_taiwan(self):
        for ticker in ("2330.TW", "2454.TW", "3443.TW", "6488.TWO", "5274.TWO"):
            with self.subTest(ticker=ticker):
                self.assertEqual(resolve_market(ticker), MARKET_TAIWAN)

    def test_other_markets_are_not_taiwan(self):
        for ticker in ("7203.T", "0700.HK", "SHOP.TO", "AAPL", "RELIANCE.NS", "BRK.B"):
            with self.subTest(ticker=ticker):
                self.assertNotEqual(resolve_market(ticker), MARKET_TAIWAN)
                # No profile is declared for these yet, so they read as default.
                self.assertEqual(resolve_market(ticker), MARKET_DEFAULT)

    def test_case_and_whitespace_insensitive(self):
        self.assertEqual(resolve_market("2330.tw"), MARKET_TAIWAN)
        self.assertEqual(resolve_market("  2330.Tw  "), MARKET_TAIWAN)
        self.assertEqual(resolve_market("6488.two"), MARKET_TAIWAN)

    def test_suffix_must_terminate_symbol_not_merely_appear(self):
        # substring / prefix / different-suffix look-alikes must not match
        for ticker in ("TW2330", "2330TW", "2330.TWOX", "TWLO", ".TW", ".TWO", "TW"):
            with self.subTest(ticker=ticker):
                self.assertEqual(resolve_market(ticker), MARKET_DEFAULT)

    def test_non_string_and_empty_inputs_are_default(self):
        self.assertEqual(resolve_market(""), MARKET_DEFAULT)
        self.assertEqual(resolve_market("   "), MARKET_DEFAULT)
        self.assertEqual(resolve_market(None), MARKET_DEFAULT)  # type: ignore[arg-type]

    def test_longest_suffix_wins_on_overlap(self):
        config = {"market_profiles": {
            "tokyo": {"suffixes": [".T"]},
            "taiwan": {"suffixes": [".TW"]},
        }}
        self.assertEqual(resolve_market("2330.TW", config), "taiwan")
        self.assertEqual(resolve_market("7203.T", config), "tokyo")

    def test_missing_profiles_key_is_default(self):
        self.assertEqual(resolve_market("2330.TW", {}), MARKET_DEFAULT)


@pytest.mark.unit
class MarketProfileTests(unittest.TestCase):
    def test_taiwan_profile_fields(self):
        for ticker in ("2330.TW", "6488.TWO"):
            with self.subTest(ticker=ticker):
                profile = get_market_profile(ticker)
                self.assertEqual(profile["currency"], "TWD")
                self.assertEqual(profile["locale"], "zh-TW")
                self.assertEqual(profile["suffixes"], [".TW", ".TWO"])
        # TWSE and TPEx share one market but not one index.
        self.assertEqual(get_market_profile("2330.TW")["benchmarks"][".TW"], "^TWII")
        self.assertEqual(get_market_profile("6488.TWO")["benchmarks"][".TWO"], "^TWOII")

    def test_default_market_has_empty_profile(self):
        self.assertEqual(get_market_profile("AAPL"), {})
        self.assertEqual(get_market_profile("7203.T"), {})

    def test_profile_benchmark_agrees_with_benchmark_map(self):
        """Step 1's benchmark_map stays the resolver's source; keep the two
        tables from drifting apart."""
        for market, profile in DEFAULT_CONFIG["market_profiles"].items():
            # every suffix has its own benchmark row, and vice versa
            self.assertEqual(set(profile["benchmarks"]), set(profile["suffixes"]), market)
            for suffix, benchmark in profile["benchmarks"].items():
                with self.subTest(market=market, suffix=suffix):
                    self.assertEqual(DEFAULT_CONFIG["benchmark_map"][suffix], benchmark)

    def test_taiwan_suffixes_pin_expected_benchmarks(self):
        self.assertEqual(DEFAULT_CONFIG["benchmark_map"][".TW"], "^TWII")
        self.assertEqual(DEFAULT_CONFIG["benchmark_map"][".TWO"], "^TWOII")
