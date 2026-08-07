"""Crypto derivatives/on-chain vendors (binance, feargreed, mempool): symbol
normalization, output formatting, graceful degradation on network errors, and
router integration — plus the crypto-native subreddit selection in the
sentiment analyst.

All HTTP access is mocked, so these run without a network connection.
"""
import copy
import unittest
from unittest import mock
from unittest.mock import MagicMock

import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import binance, feargreed, interface, mempool
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.reddit import CRYPTO_SUBREDDITS, DEFAULT_SUBREDDITS


@pytest.mark.unit
class BinanceSymbolTests(unittest.TestCase):
    def test_dash_usd_pair_maps_to_usdt_perp(self):
        self.assertEqual(binance._binance_symbol("BTC-USD"), "BTCUSDT")
        self.assertEqual(binance._binance_symbol("ETH-USD"), "ETHUSDT")

    def test_lowercase_and_bare_usd_forms(self):
        self.assertEqual(binance._binance_symbol("btc-usd"), "BTCUSDT")
        self.assertEqual(binance._binance_symbol("BTCUSD"), "BTCUSDT")


@pytest.mark.unit
class BinanceFundingRateTests(unittest.TestCase):
    _ROWS = [
        {"symbol": "BTCUSDT", "fundingTime": 1786003200000, "fundingRate": "0.00002632", "markPrice": "64789.40"},
        {"symbol": "BTCUSDT", "fundingTime": 1786032000000, "fundingRate": "0.00005939", "markPrice": "64604.20"},
    ]

    def test_report_has_table_and_neutral_read(self):
        with mock.patch.object(binance, "_request", return_value=self._ROWS):
            out = binance.get_funding_rate("BTC-USD")
        self.assertIn("### Perpetual Funding Rate (BTCUSDT, Binance)", out)
        self.assertIn("| 64,789.40 |", out)
        self.assertIn("neutral", out)

    def test_elevated_positive_funding_flags_crowded_longs(self):
        rows = [{"symbol": "BTCUSDT", "fundingTime": 1786003200000, "fundingRate": "0.0005", "markPrice": "64789.40"}]
        with mock.patch.object(binance, "_request", return_value=rows):
            out = binance.get_funding_rate("BTC-USD")
        self.assertIn("crowded", out)
        self.assertIn("long", out)

    def test_negative_funding_flags_crowded_shorts(self):
        rows = [{"symbol": "BTCUSDT", "fundingTime": 1786003200000, "fundingRate": "-0.0005", "markPrice": "64789.40"}]
        with mock.patch.object(binance, "_request", return_value=rows):
            out = binance.get_funding_rate("BTC-USD")
        self.assertIn("squeeze", out)

    def test_empty_response_reports_no_data(self):
        with mock.patch.object(binance, "_request", return_value=[]):
            out = binance.get_funding_rate("BTC-USD")
        self.assertIn("No funding rate data", out)

    def test_network_error_degrades_gracefully(self):
        import requests
        with mock.patch.object(binance, "_request", side_effect=requests.RequestException("boom")):
            out = binance.get_funding_rate("BTC-USD")
        self.assertIn("currently unavailable", out)
        self.assertIn("BTCUSDT", out)


@pytest.mark.unit
class BinanceOpenInterestTests(unittest.TestCase):
    def test_report_shows_current_oi(self):
        with mock.patch.object(binance, "_request", return_value={"symbol": "BTCUSDT", "openInterest": "105581.817"}):
            out = binance.get_open_interest("BTC-USD")
        self.assertIn("### Open Interest (BTCUSDT, Binance perpetual)", out)
        self.assertIn("105,581.82 BTC contracts", out)

    def test_network_error_degrades_gracefully(self):
        import requests
        with mock.patch.object(binance, "_request", side_effect=requests.RequestException("boom")):
            out = binance.get_open_interest("BTC-USD")
        self.assertIn("currently unavailable", out)


@pytest.mark.unit
class FearGreedIndexTests(unittest.TestCase):
    def _mock_response(self, rows):
        resp = MagicMock()
        resp.json.return_value = {"data": rows}
        resp.raise_for_status.return_value = None
        return resp

    def test_report_has_table(self):
        rows = [{"value": "29", "value_classification": "Fear", "timestamp": "1786060800"}]
        with mock.patch.object(feargreed.requests, "get", return_value=self._mock_response(rows)):
            out = feargreed.get_fear_greed_index()
        self.assertIn("Crypto Fear & Greed Index", out)
        self.assertIn("| 2026-08-07 | 29 | Fear |", out)

    def test_empty_response_reports_no_data(self):
        with mock.patch.object(feargreed.requests, "get", return_value=self._mock_response([])):
            out = feargreed.get_fear_greed_index()
        self.assertIn("No Fear & Greed Index data", out)

    def test_network_error_degrades_gracefully(self):
        import requests
        with mock.patch.object(feargreed.requests, "get", side_effect=requests.RequestException("boom")):
            out = feargreed.get_fear_greed_index()
        self.assertIn("currently unavailable", out)


@pytest.mark.unit
class MempoolHashrateTests(unittest.TestCase):
    def _mock_response(self):
        resp = MagicMock()
        resp.json.return_value = {
            "currentHashrate": 928265012830267900000,
            "currentDifficulty": 126231507121868.2,
            "hashrates": [
                {"timestamp": 1785974400, "avgHashrate": 899192029875902200000},
                {"timestamp": 1786060800, "avgHashrate": 794167855200950800000},
            ],
        }
        resp.raise_for_status.return_value = None
        return resp

    def test_report_has_current_and_trend(self):
        with mock.patch.object(mempool.requests, "get", return_value=self._mock_response()):
            out = mempool.get_network_hashrate()
        self.assertIn("### Bitcoin Network Hashrate (mempool.space)", out)
        self.assertIn("928.3 EH/s", out)
        self.assertIn("| 2026-08-07 | 794.2 |", out)

    def test_network_error_degrades_gracefully(self):
        import requests
        with mock.patch.object(mempool.requests, "get", side_effect=requests.RequestException("boom")):
            out = mempool.get_network_hashrate()
        self.assertIn("currently unavailable", out)


@pytest.mark.unit
class CryptoSignalsRoutingTests(unittest.TestCase):
    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def test_all_four_methods_route_to_crypto_signals_category(self):
        for method in (
            "get_crypto_funding_rate",
            "get_crypto_open_interest",
            "get_crypto_fear_greed_index",
            "get_bitcoin_network_hashrate",
        ):
            self.assertEqual(interface.get_category_for_method(method), "crypto_signals")

    def test_default_vendor_resolves_per_method(self):
        set_config({"data_vendors": {"crypto_signals": "default"}})
        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_bitcoin_network_hashrate": {"mempool": lambda: "HASHRATE_OK"}},
            clear=False,
        ):
            out = interface.route_to_vendor("get_bitcoin_network_hashrate")
        self.assertEqual(out, "HASHRATE_OK")

    def test_unexpected_vendor_error_degrades_gracefully(self):
        # crypto_signals is an optional category: an unhandled vendor exception
        # (beyond the internal requests.RequestException catch each vendor
        # already does) must not abort the run.
        set_config({"data_vendors": {"crypto_signals": "default"}})

        def _boom():
            raise RuntimeError("unexpected")

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_bitcoin_network_hashrate": {"mempool": _boom}},
            clear=False,
        ):
            out = interface.route_to_vendor("get_bitcoin_network_hashrate")
        self.assertIn("DATA_UNAVAILABLE", out)


@pytest.mark.unit
class SentimentAnalystCryptoSubredditsTests(unittest.TestCase):
    """The sentiment analyst must search crypto-native subreddits for a crypto
    asset — the equities default (wallstreetbets/stocks/investing) returns
    near-zero signal for a ticker like BTC-USD."""

    def _run(self, asset_type):
        from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst
        from tradingagents.agents.schemas import SentimentBand, SentimentReport

        captured = {}
        report = SentimentReport(
            overall_band=SentimentBand.BULLISH, overall_score=7.0,
            confidence="high", narrative="n/a",
        )
        structured = MagicMock()
        structured.invoke.return_value = report
        llm = MagicMock()
        llm.with_structured_output.return_value = structured

        state = {
            "company_of_interest": "BTC-USD" if asset_type == "crypto" else "NVDA",
            "trade_date": "2026-08-06",
            "asset_type": asset_type,
            "messages": [],
        }

        with mock.patch(
            "tradingagents.agents.analysts.sentiment_analyst.fetch_reddit_posts",
            side_effect=lambda ticker, subreddits: captured.__setitem__("subreddits", subreddits) or "",
        ), mock.patch(
            "tradingagents.agents.analysts.sentiment_analyst.fetch_stocktwits_messages",
            return_value="",
        ), mock.patch(
            "tradingagents.agents.analysts.sentiment_analyst.get_news"
        ) as get_news:
            get_news.func.return_value = ""
            create_sentiment_analyst(llm)(state)
        return captured["subreddits"]

    def test_crypto_asset_uses_crypto_subreddits(self):
        self.assertEqual(self._run("crypto"), CRYPTO_SUBREDDITS)

    def test_stock_asset_uses_default_subreddits(self):
        self.assertEqual(self._run("stock"), DEFAULT_SUBREDDITS)


if __name__ == "__main__":
    unittest.main()
