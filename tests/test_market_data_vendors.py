import copy
import unittest
from unittest.mock import Mock, patch

import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.config import get_config, set_config


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.text = str(payload)

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.mark.unit
class MarketDataVendorConfigTests(unittest.TestCase):
    def setUp(self):
        set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))

    def test_default_vendor_order_uses_official_apis_before_scraping_fallbacks(self):
        cfg = get_config()

        self.assertEqual(
            cfg["data_vendors"]["core_stock_apis"],
            "fmp,alpha_vantage,marketstack,yfinance",
        )
        self.assertEqual(
            cfg["data_vendors"]["fundamental_data"],
            "fmp,alpha_vantage,finnhub,yfinance",
        )
        self.assertEqual(
            cfg["data_vendors"]["news_data"],
            "finnhub,fmp,alpha_vantage,yfinance",
        )

    def test_new_vendor_methods_are_registered_without_historical_finnhub_candles(self):
        self.assertIn("fmp", interface.VENDOR_LIST)
        self.assertIn("finnhub", interface.VENDOR_LIST)
        self.assertIn("marketstack", interface.VENDOR_LIST)

        self.assertIn("fmp", interface.VENDOR_METHODS["get_stock_data"])
        self.assertIn("marketstack", interface.VENDOR_METHODS["get_stock_data"])
        self.assertNotIn("finnhub", interface.VENDOR_METHODS["get_stock_data"])

        self.assertIn("finnhub", interface.VENDOR_METHODS["get_fundamentals"])
        self.assertIn("fmp", interface.VENDOR_METHODS["get_news"])


@pytest.mark.unit
class FinancialModelingPrepAdapterTests(unittest.TestCase):
    def test_stock_history_requests_stable_eod_endpoint_and_returns_csv(self):
        from tradingagents.dataflows import fmp_stock
        from tradingagents.dataflows import fmp_common

        payload = [
            {
                "date": "2026-06-15",
                "open": 10.1,
                "high": 10.9,
                "low": 9.9,
                "close": 10.5,
                "volume": 12345,
            }
        ]

        with patch.dict("os.environ", {"FMP_API_KEY": "fmp-key"}):
            with patch.object(fmp_common.requests, "get", return_value=_FakeResponse(payload)) as get:
                result = fmp_stock.get_stock("AAPL", "2026-06-01", "2026-06-15")

        self.assertIn("date,open,high,low,close,volume", result)
        self.assertIn("2026-06-15,10.1,10.9,9.9,10.5,12345", result)
        url = get.call_args.args[0]
        params = get.call_args.kwargs["params"]
        self.assertEqual(url, "https://financialmodelingprep.com/stable/historical-price-eod/full")
        self.assertEqual(params["symbol"], "AAPL")
        self.assertEqual(params["from"], "2026-06-01")
        self.assertEqual(params["to"], "2026-06-15")
        self.assertEqual(params["apikey"], "fmp-key")


@pytest.mark.unit
class FinnhubAdapterTests(unittest.TestCase):
    def test_fundamentals_merge_profile_metrics_and_earnings_calendar(self):
        from tradingagents.dataflows import finnhub_fundamentals
        from tradingagents.dataflows import finnhub_common

        responses = [
            _FakeResponse({"name": "Apple Inc", "marketCapitalization": 3000}),
            _FakeResponse({"metric": {"peNormalizedAnnual": 28.2}}),
            _FakeResponse({"earningsCalendar": [{"date": "2026-07-29", "epsEstimate": 1.5}]}),
            _FakeResponse({"data": [{"transactionDate": "2026-06-01", "name": "Director"}]}),
        ]

        with patch.dict("os.environ", {"FINNHUB_API_KEY": "fh-key"}):
            with patch.object(finnhub_common.requests, "get", side_effect=responses) as get:
                result = finnhub_fundamentals.get_fundamentals("AAPL", "2026-06-16")

        self.assertIn("Company Profile", result)
        self.assertIn("Basic Financial Metrics", result)
        self.assertIn("Upcoming / Recent Earnings", result)
        self.assertIn("Recent Insider Transactions", result)
        self.assertEqual(get.call_count, 4)
        first_params = get.call_args_list[0].kwargs["params"]
        self.assertEqual(first_params["symbol"], "AAPL")
        self.assertEqual(first_params["token"], "fh-key")


@pytest.mark.unit
class MarketstackAdapterTests(unittest.TestCase):
    def test_eod_history_requests_access_key_endpoint_and_returns_csv(self):
        from tradingagents.dataflows import marketstack_stock
        from tradingagents.dataflows import marketstack_common

        payload = {
            "data": [
                {
                    "date": "2026-06-14T00:00:00+0000",
                    "open": 20,
                    "high": 22,
                    "low": 19,
                    "close": 21,
                    "volume": 9876,
                }
            ]
        }

        with patch.dict("os.environ", {"MARKETSTACK_API_KEY": "ms-key"}):
            with patch.object(marketstack_common.requests, "get", return_value=_FakeResponse(payload)) as get:
                result = marketstack_stock.get_stock("MSFT", "2026-06-01", "2026-06-15")

        self.assertIn("date,open,high,low,close,volume", result)
        self.assertIn("2026-06-14,20,22,19,21,9876", result)
        url = get.call_args.args[0]
        params = get.call_args.kwargs["params"]
        self.assertEqual(url, "https://api.marketstack.com/v1/eod")
        self.assertEqual(params["symbols"], "MSFT")
        self.assertEqual(params["date_from"], "2026-06-01")
        self.assertEqual(params["date_to"], "2026-06-15")
        self.assertEqual(params["access_key"], "ms-key")
