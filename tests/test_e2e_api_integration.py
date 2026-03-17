"""End-to-end integration tests combining the Y Finance and Alpha Vantage data layers.

These tests validate the full pipeline from the vendor-routing layer
(interface.route_to_vendor) through data retrieval to formatted output, using
mocks so that no real network calls are made.
"""

import json
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, PropertyMock


# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

_OHLCV_CSV_AV = (
    "timestamp,open,high,low,close,adjusted_close,volume,dividend_amount,split_coefficient\n"
    "2024-01-05,185.00,187.50,184.20,186.00,186.00,50000000,0.0000,1.0\n"
    "2024-01-04,183.00,186.00,182.50,185.00,185.00,45000000,0.0000,1.0\n"
)

_OVERVIEW_JSON = json.dumps({
    "Symbol": "AAPL",
    "Name": "Apple Inc",
    "Sector": "TECHNOLOGY",
    "MarketCapitalization": "3000000000000",
    "PERatio": "30.5",
})

_NEWS_JSON = json.dumps({
    "feed": [
        {
            "title": "Apple Hits Record High",
            "url": "https://example.com/news/1",
            "time_published": "20240105T150000",
            "summary": "Apple stock reached a new record.",
            "overall_sentiment_label": "Bullish",
        }
    ]
})

_RATE_LIMIT_JSON = json.dumps({
    "Information": (
        "Thank you for using Alpha Vantage! Our standard API rate limit is 25 requests per day."
    )
})


def _mock_av_response(text: str):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


def _make_yf_ohlcv_df():
    idx = pd.date_range("2024-01-04", periods=2, freq="B", tz="America/New_York")
    return pd.DataFrame(
        {"Open": [183.0, 185.0], "High": [186.0, 187.5], "Low": [182.5, 184.2],
         "Close": [185.0, 186.0], "Volume": [45_000_000, 50_000_000]},
        index=idx,
    )


# ---------------------------------------------------------------------------
# Vendor-routing layer tests
# ---------------------------------------------------------------------------

class TestRouteToVendor:
    """Tests for interface.route_to_vendor."""

    def test_routes_stock_data_to_yfinance_by_default(self):
        """With default config (yfinance), get_stock_data is routed to yfinance."""
        from tradingagents.dataflows.interface import route_to_vendor

        df = _make_yf_ohlcv_df()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = route_to_vendor("get_stock_data", "AAPL", "2024-01-04", "2024-01-05")

        assert isinstance(result, str)
        assert "AAPL" in result

    def test_routes_stock_data_to_alpha_vantage_when_configured(self):
        """When the vendor is overridden to alpha_vantage, the AV implementation is called."""
        from tradingagents.dataflows.interface import route_to_vendor
        from tradingagents.dataflows.config import get_config

        original_config = get_config()
        patched_config = {
            **original_config,
            "data_vendors": {**original_config.get("data_vendors", {}), "core_stock_apis": "alpha_vantage"},
        }

        with patch("tradingagents.dataflows.interface.get_config", return_value=patched_config):
            with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                       return_value=_mock_av_response(_OHLCV_CSV_AV)):
                with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                    result = route_to_vendor("get_stock_data", "AAPL", "2024-01-04", "2024-01-05")

        assert isinstance(result, str)

    def test_fallback_to_yfinance_when_alpha_vantage_rate_limited(self):
        """When AV hits a rate limit, the router falls back to yfinance automatically."""
        from tradingagents.dataflows.interface import route_to_vendor
        from tradingagents.dataflows.config import get_config

        original_config = get_config()
        patched_config = {
            **original_config,
            "data_vendors": {**original_config.get("data_vendors", {}), "core_stock_apis": "alpha_vantage"},
        }

        df = _make_yf_ohlcv_df()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("tradingagents.dataflows.interface.get_config", return_value=patched_config):
            # AV returns a rate-limit response
            with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                       return_value=_mock_av_response(_RATE_LIMIT_JSON)):
                with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                    # yfinance is the fallback
                    with patch("tradingagents.dataflows.y_finance.yf.Ticker",
                               return_value=mock_ticker):
                        result = route_to_vendor(
                            "get_stock_data", "AAPL", "2024-01-04", "2024-01-05"
                        )

        assert isinstance(result, str)
        assert "AAPL" in result

    def test_raises_runtime_error_when_all_vendors_fail(self):
        """When every vendor fails, a RuntimeError is raised."""
        from tradingagents.dataflows.interface import route_to_vendor
        from tradingagents.dataflows.config import get_config
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError

        original_config = get_config()
        patched_config = {
            **original_config,
            "data_vendors": {**original_config.get("data_vendors", {}), "core_stock_apis": "alpha_vantage"},
        }

        with patch("tradingagents.dataflows.interface.get_config", return_value=patched_config):
            with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                       return_value=_mock_av_response(_RATE_LIMIT_JSON)):
                with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                    with patch(
                        "tradingagents.dataflows.y_finance.yf.Ticker",
                        side_effect=ConnectionError("network unavailable"),
                    ):
                        with pytest.raises(RuntimeError, match="No available vendor"):
                            route_to_vendor("get_stock_data", "AAPL", "2024-01-04", "2024-01-05")

    def test_unknown_method_raises_value_error(self):
        from tradingagents.dataflows.interface import route_to_vendor

        with pytest.raises(ValueError):
            route_to_vendor("nonexistent_method", "AAPL")


# ---------------------------------------------------------------------------
# Full pipeline: fetch → process → output
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """End-to-end tests that walk through the complete data retrieval pipeline."""

    def test_yfinance_stock_data_pipeline(self):
        """Fetch OHLCV data via yfinance, verify the formatted CSV output."""
        from tradingagents.dataflows.y_finance import get_YFin_data_online

        df = _make_yf_ohlcv_df()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            raw = get_YFin_data_online("AAPL", "2024-01-04", "2024-01-05")

        # Response structure checks
        assert raw.startswith("# Stock data for AAPL")
        assert "# Total records: 2" in raw
        assert "Close" in raw  # CSV column
        assert "186.0" in raw  # rounded close price

    def test_alpha_vantage_stock_data_pipeline(self):
        """Fetch OHLCV data via Alpha Vantage, verify the CSV output is filtered."""
        from tradingagents.dataflows.alpha_vantage_stock import get_stock

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_av_response(_OHLCV_CSV_AV)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_stock("AAPL", "2024-01-04", "2024-01-05")

        assert isinstance(result, str)
        # pandas may reformat "185.00" → "185.0"; check for the numeric value
        assert "185.0" in result or "186.0" in result

    def test_yfinance_fundamentals_pipeline(self):
        """Fetch company fundamentals via yfinance, verify key fields appear."""
        from tradingagents.dataflows.y_finance import get_fundamentals

        mock_info = {
            "longName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "marketCap": 3_000_000_000_000,
            "trailingPE": 30.5,
            "beta": 1.2,
        }
        mock_ticker = MagicMock()
        type(mock_ticker).info = PropertyMock(return_value=mock_info)

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_fundamentals("AAPL")

        assert "Apple Inc." in result
        assert "Technology" in result
        assert "30.5" in result

    def test_alpha_vantage_fundamentals_pipeline(self):
        """Fetch company overview via Alpha Vantage, verify key fields appear."""
        from tradingagents.dataflows.alpha_vantage_fundamentals import get_fundamentals

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_av_response(_OVERVIEW_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_fundamentals("AAPL")

        assert "Apple Inc" in result
        assert "TECHNOLOGY" in result

    def test_yfinance_news_pipeline(self):
        """Fetch news via yfinance and verify basic response structure."""
        from tradingagents.dataflows.yfinance_news import get_news_yfinance

        mock_search = MagicMock()
        mock_search.news = [
            {
                "title": "Apple Earnings Beat Expectations",
                "publisher": "Reuters",
                "link": "https://example.com",
                "providerPublishTime": 1704499200,
                "summary": "Apple reports Q1 earnings above estimates.",
            }
        ]

        with patch("tradingagents.dataflows.yfinance_news.yf.Search", return_value=mock_search):
            result = get_news_yfinance("AAPL", "2024-01-01", "2024-01-05")

        assert isinstance(result, str)

    def test_alpha_vantage_news_pipeline(self):
        """Fetch ticker news via Alpha Vantage and verify basic response structure."""
        from tradingagents.dataflows.alpha_vantage_news import get_news

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_av_response(_NEWS_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_news("AAPL", "2024-01-01", "2024-01-05")

        assert "Apple Hits Record High" in result

    def test_combined_yfinance_and_alpha_vantage_workflow(self):
        """
        Simulates a multi-source workflow:
          1. Fetch stock price data from yfinance.
          2. Fetch company fundamentals from Alpha Vantage.
          3. Verify both results contain expected data and can be used together.
        """
        from tradingagents.dataflows.y_finance import get_YFin_data_online
        from tradingagents.dataflows.alpha_vantage_fundamentals import get_fundamentals

        # --- Step 1: yfinance price data ---
        df = _make_yf_ohlcv_df()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            price_data = get_YFin_data_online("AAPL", "2024-01-04", "2024-01-05")

        # --- Step 2: Alpha Vantage fundamentals ---
        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_av_response(_OVERVIEW_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                fundamentals = get_fundamentals("AAPL")

        # --- Assertions ---
        assert isinstance(price_data, str)
        assert isinstance(fundamentals, str)

        # Price data should reference the ticker
        assert "AAPL" in price_data

        # Fundamentals should contain company info
        assert "Apple Inc" in fundamentals

        # Both contain data – a real application could merge them here
        combined_report = price_data + "\n\n" + fundamentals
        assert "AAPL" in combined_report
        assert "Apple Inc" in combined_report

    def test_error_handling_in_combined_workflow(self):
        """
        When Alpha Vantage fails with a rate-limit error, the workflow can
        continue with yfinance data alone – the error is surfaced rather than
        silently swallowed.
        """
        from tradingagents.dataflows.y_finance import get_YFin_data_online
        from tradingagents.dataflows.alpha_vantage_fundamentals import get_fundamentals
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError

        # yfinance succeeds
        df = _make_yf_ohlcv_df()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            price_data = get_YFin_data_online("AAPL", "2024-01-04", "2024-01-05")

        assert isinstance(price_data, str)
        assert "AAPL" in price_data

        # Alpha Vantage rate-limits
        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_av_response(_RATE_LIMIT_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                with pytest.raises(AlphaVantageRateLimitError):
                    get_fundamentals("AAPL")


# ---------------------------------------------------------------------------
# Vendor configuration and method routing
# ---------------------------------------------------------------------------

class TestVendorConfiguration:
    """Tests for vendor configuration helpers in the interface module."""

    def test_get_category_for_method_core_stock_apis(self):
        from tradingagents.dataflows.interface import get_category_for_method

        assert get_category_for_method("get_stock_data") == "core_stock_apis"

    def test_get_category_for_method_fundamental_data(self):
        from tradingagents.dataflows.interface import get_category_for_method

        assert get_category_for_method("get_fundamentals") == "fundamental_data"

    def test_get_category_for_method_news_data(self):
        from tradingagents.dataflows.interface import get_category_for_method

        assert get_category_for_method("get_news") == "news_data"

    def test_get_category_for_unknown_method_raises_value_error(self):
        from tradingagents.dataflows.interface import get_category_for_method

        with pytest.raises(ValueError, match="not found"):
            get_category_for_method("nonexistent_method")

    def test_vendor_methods_contains_both_vendors_for_stock_data(self):
        """Both yfinance and alpha_vantage implementations are registered."""
        from tradingagents.dataflows.interface import VENDOR_METHODS

        assert "get_stock_data" in VENDOR_METHODS
        assert "yfinance" in VENDOR_METHODS["get_stock_data"]
        assert "alpha_vantage" in VENDOR_METHODS["get_stock_data"]

    def test_vendor_methods_contains_both_vendors_for_news(self):
        from tradingagents.dataflows.interface import VENDOR_METHODS

        assert "get_news" in VENDOR_METHODS
        assert "yfinance" in VENDOR_METHODS["get_news"]
        assert "alpha_vantage" in VENDOR_METHODS["get_news"]
