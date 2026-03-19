"""Tests for fail-fast vendor routing (ADR 011).

Methods NOT in FALLBACK_ALLOWED must fail immediately when the primary vendor
fails, rather than silently falling back to a vendor with a different data contract.
"""

import pytest
from unittest.mock import patch, MagicMock

from tradingagents.dataflows.interface import route_to_vendor, FALLBACK_ALLOWED
from tradingagents.dataflows.alpha_vantage_common import AlphaVantageError
from tradingagents.dataflows.finnhub_common import FinnhubError
from tradingagents.dataflows.config import get_config


def _config_with_vendor(category: str, vendor: str):
    """Return a patched config dict that sets a specific vendor for a category."""
    original = get_config()
    return {
        **original,
        "data_vendors": {**original.get("data_vendors", {}), category: vendor},
    }


class TestFailFastMethods:
    """Methods NOT in FALLBACK_ALLOWED must not fall back to other vendors."""

    def test_news_fails_fast_no_fallback(self):
        """get_news configured for alpha_vantage should NOT fall back to yfinance."""
        config = _config_with_vendor("news_data", "alpha_vantage")

        with patch("tradingagents.dataflows.interface.get_config", return_value=config):
            with patch(
                "tradingagents.dataflows.alpha_vantage_common.requests.get",
                side_effect=ConnectionError("AV down"),
            ):
                with pytest.raises(RuntimeError, match="All vendors failed for 'get_news'"):
                    route_to_vendor("get_news", "AAPL", "2024-01-01", "2024-01-05")

    def test_indicators_fail_fast_no_fallback(self):
        """get_indicators configured for alpha_vantage should NOT fall back to yfinance."""
        from tradingagents.dataflows.interface import VENDOR_METHODS
        config = _config_with_vendor("technical_indicators", "alpha_vantage")

        original = VENDOR_METHODS["get_indicators"]["alpha_vantage"]
        VENDOR_METHODS["get_indicators"]["alpha_vantage"] = MagicMock(
            side_effect=AlphaVantageError("AV down")
        )
        try:
            with patch("tradingagents.dataflows.interface.get_config", return_value=config):
                with pytest.raises(RuntimeError, match="All vendors failed for 'get_indicators'"):
                    route_to_vendor("get_indicators", "AAPL", "SMA", "2024-01-01", 50)
        finally:
            VENDOR_METHODS["get_indicators"]["alpha_vantage"] = original

    def test_fundamentals_fail_fast_no_fallback(self):
        """get_fundamentals configured for alpha_vantage should NOT fall back to yfinance."""
        config = _config_with_vendor("fundamental_data", "alpha_vantage")

        with patch("tradingagents.dataflows.interface.get_config", return_value=config):
            with patch(
                "tradingagents.dataflows.alpha_vantage_common.requests.get",
                side_effect=ConnectionError("AV down"),
            ):
                with pytest.raises(RuntimeError, match="All vendors failed for 'get_fundamentals'"):
                    route_to_vendor("get_fundamentals", "AAPL")

    def test_insider_transactions_fail_fast_no_fallback(self):
        """get_insider_transactions configured for finnhub should NOT fall back."""
        from tradingagents.dataflows.interface import VENDOR_METHODS
        config = _config_with_vendor("news_data", "finnhub")

        original = VENDOR_METHODS["get_insider_transactions"]["finnhub"]
        VENDOR_METHODS["get_insider_transactions"]["finnhub"] = MagicMock(
            side_effect=FinnhubError("Finnhub down")
        )
        try:
            with patch("tradingagents.dataflows.interface.get_config", return_value=config):
                with pytest.raises(RuntimeError, match="All vendors failed for 'get_insider_transactions'"):
                    route_to_vendor("get_insider_transactions", "AAPL")
        finally:
            VENDOR_METHODS["get_insider_transactions"]["finnhub"] = original

    def test_topic_news_fail_fast_no_fallback(self):
        """get_topic_news should NOT fall back across vendors."""
        from tradingagents.dataflows.interface import VENDOR_METHODS
        config = _config_with_vendor("scanner_data", "finnhub")

        original = VENDOR_METHODS["get_topic_news"]["finnhub"]
        VENDOR_METHODS["get_topic_news"]["finnhub"] = MagicMock(
            side_effect=FinnhubError("Finnhub down")
        )
        try:
            with patch("tradingagents.dataflows.interface.get_config", return_value=config):
                with pytest.raises(RuntimeError, match="All vendors failed for 'get_topic_news'"):
                    route_to_vendor("get_topic_news", "technology")
        finally:
            VENDOR_METHODS["get_topic_news"]["finnhub"] = original

    def test_calendar_fail_fast_single_vendor(self):
        """get_earnings_calendar (Finnhub-only) fails fast."""
        from tradingagents.dataflows.interface import VENDOR_METHODS
        config = _config_with_vendor("calendar_data", "finnhub")

        original = VENDOR_METHODS["get_earnings_calendar"]["finnhub"]
        VENDOR_METHODS["get_earnings_calendar"]["finnhub"] = MagicMock(
            side_effect=FinnhubError("Finnhub down")
        )
        try:
            with patch("tradingagents.dataflows.interface.get_config", return_value=config):
                with pytest.raises(RuntimeError, match="All vendors failed for 'get_earnings_calendar'"):
                    route_to_vendor("get_earnings_calendar", "2024-01-01", "2024-01-05")
        finally:
            VENDOR_METHODS["get_earnings_calendar"]["finnhub"] = original


class TestErrorChaining:
    """Verify error messages and exception chaining."""

    def test_error_chain_preserved(self):
        """RuntimeError.__cause__ should be the original vendor exception."""
        config = _config_with_vendor("news_data", "alpha_vantage")

        with patch("tradingagents.dataflows.interface.get_config", return_value=config):
            with patch(
                "tradingagents.dataflows.alpha_vantage_common.requests.get",
                side_effect=ConnectionError("network down"),
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    route_to_vendor("get_news", "AAPL", "2024-01-01", "2024-01-05")

                assert exc_info.value.__cause__ is not None
                assert isinstance(exc_info.value.__cause__, ConnectionError)

    def test_error_message_includes_method_and_vendors(self):
        """Error message should include method name and vendors tried."""
        config = _config_with_vendor("fundamental_data", "alpha_vantage")

        with patch("tradingagents.dataflows.interface.get_config", return_value=config):
            with patch(
                "tradingagents.dataflows.alpha_vantage_common.requests.get",
                side_effect=ConnectionError("down"),
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    route_to_vendor("get_fundamentals", "AAPL")

                msg = str(exc_info.value)
                assert "get_fundamentals" in msg
                assert "alpha_vantage" in msg

    def test_auth_error_propagates(self):
        """401/403 errors (wrapped as vendor errors) should not silently retry."""
        config = _config_with_vendor("news_data", "alpha_vantage")

        with patch("tradingagents.dataflows.interface.get_config", return_value=config):
            with patch(
                "tradingagents.dataflows.alpha_vantage_common.requests.get",
                side_effect=AlphaVantageError("Invalid API key (401)"),
            ):
                with pytest.raises(RuntimeError, match="All vendors failed"):
                    route_to_vendor("get_news", "AAPL", "2024-01-01", "2024-01-05")


class TestFallbackAllowedStillWorks:
    """Methods IN FALLBACK_ALLOWED should still get cross-vendor fallback."""

    def test_stock_data_falls_back(self):
        """get_stock_data (in FALLBACK_ALLOWED) should fall back from AV to yfinance."""
        import pandas as pd

        config = _config_with_vendor("core_stock_apis", "alpha_vantage")
        df = pd.DataFrame(
            {"Open": [183.0], "High": [186.0], "Low": [182.5],
             "Close": [185.0], "Volume": [45_000_000]},
            index=pd.date_range("2024-01-04", periods=1, freq="B", tz="America/New_York"),
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("tradingagents.dataflows.interface.get_config", return_value=config):
            with patch(
                "tradingagents.dataflows.alpha_vantage_common.requests.get",
                side_effect=ConnectionError("AV down"),
            ):
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    result = route_to_vendor("get_stock_data", "AAPL", "2024-01-04", "2024-01-05")

        assert isinstance(result, str)
        assert "AAPL" in result

    def test_fallback_allowed_set_contents(self):
        """Verify the FALLBACK_ALLOWED set contains exactly the expected methods."""
        expected = {
            "get_stock_data",
            "get_market_indices",
            "get_sector_performance",
            "get_market_movers",
            "get_industry_performance",
        }
        assert FALLBACK_ALLOWED == expected
