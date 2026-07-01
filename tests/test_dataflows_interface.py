"""Tests for the dataflows interface (route_to_vendor, get_category_for_method, get_vendor)."""

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows.interface import (
    TOOLS_CATEGORIES,
    VENDOR_METHODS,
    get_category_for_method,
    get_vendor,
    route_to_vendor,
)
from tradingagents.dataflows.symbol_utils import NoMarketDataError

# ---------------------------------------------------------------------------
# get_category_for_method
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetCategoryForMethod:
    def test_get_stock_data_in_core_stock_apis(self):
        assert get_category_for_method("get_stock_data") == "core_stock_apis"

    def test_get_indicators_in_technical_indicators(self):
        assert get_category_for_method("get_indicators") == "technical_indicators"

    def test_get_fundamentals_in_fundamental_data(self):
        assert get_category_for_method("get_fundamentals") == "fundamental_data"

    def test_get_news_in_news_data(self):
        assert get_category_for_method("get_news") == "news_data"

    def test_get_global_news_in_news_data(self):
        assert get_category_for_method("get_global_news") == "news_data"

    def test_get_insider_transactions_in_news_data(self):
        assert get_category_for_method("get_insider_transactions") == "news_data"

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="not found in any category"):
            get_category_for_method("get_nonexistent")

    def test_all_vendor_methods_have_categories(self):
        for method in VENDOR_METHODS:
            get_category_for_method(method)


# ---------------------------------------------------------------------------
# get_vendor
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetVendor:
    @patch("tradingagents.dataflows.interface.get_config")
    def test_returns_category_vendor(self, mock_config):
        mock_config.return_value = {
            "data_vendors": {"core_stock_apis": "yfinance"},
            "tool_vendors": {},
        }
        assert get_vendor("core_stock_apis") == "yfinance"

    @patch("tradingagents.dataflows.interface.get_config")
    def test_tool_level_overrides_category(self, mock_config):
        mock_config.return_value = {
            "data_vendors": {"core_stock_apis": "yfinance"},
            "tool_vendors": {"get_stock_data": "alpha_vantage"},
        }
        assert get_vendor("core_stock_apis", method="get_stock_data") == "alpha_vantage"

    @patch("tradingagents.dataflows.interface.get_config")
    def test_falls_back_to_default_when_category_missing(self, mock_config):
        mock_config.return_value = {"data_vendors": {}, "tool_vendors": {}}
        assert get_vendor("core_stock_apis") == "default"


# ---------------------------------------------------------------------------
# route_to_vendor
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRouteToVendor:
    @patch("tradingagents.dataflows.interface.get_vendor")
    @patch("tradingagents.dataflows.interface.get_category_for_method")
    def test_routes_to_primary_vendor(self, mock_category, mock_vendor):
        mock_category.return_value = "core_stock_apis"
        mock_vendor.return_value = "yfinance"
        mock_impl = MagicMock(return_value="OHLCV data")

        with patch.dict(VENDOR_METHODS, {
            "get_stock_data": {"yfinance": mock_impl, "alpha_vantage": MagicMock()},
        }):
            result = route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-15")
            assert result == "OHLCV data"
            mock_impl.assert_called_once_with("AAPL", "2026-01-01", "2026-01-15")

    @patch("tradingagents.dataflows.interface.get_vendor")
    @patch("tradingagents.dataflows.interface.get_category_for_method")
    def test_falls_back_on_primary_failure(self, mock_category, mock_vendor):
        mock_category.return_value = "core_stock_apis"
        mock_vendor.return_value = "alpha_vantage,yfinance"
        failing_impl = MagicMock(side_effect=RuntimeError("API down"))
        fallback_impl = MagicMock(return_value="Fallback data")

        with patch.dict(VENDOR_METHODS, {
            "get_stock_data": {"alpha_vantage": failing_impl, "yfinance": fallback_impl},
        }):
            result = route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-15")
            assert result == "Fallback data"

    @patch("tradingagents.dataflows.interface.get_vendor")
    @patch("tradingagents.dataflows.interface.get_category_for_method")
    def test_no_data_returns_sentinel(self, mock_category, mock_vendor):
        mock_category.return_value = "core_stock_apis"
        mock_vendor.return_value = "yfinance"
        no_data_impl = MagicMock(side_effect=NoMarketDataError("INVALID", "INVALID"))

        with patch.dict(VENDOR_METHODS, {
            "get_stock_data": {"yfinance": no_data_impl},
        }):
            result = route_to_vendor("get_stock_data", "INVALID", "2026-01-01", "2026-01-15")
            assert "NO_DATA_AVAILABLE" in result
            assert "INVALID" in result

    @patch("tradingagents.dataflows.interface.get_vendor")
    @patch("tradingagents.dataflows.interface.get_category_for_method")
    def test_all_vendors_fail_raises_first_error(self, mock_category, mock_vendor):
        mock_category.return_value = "core_stock_apis"
        mock_vendor.return_value = "yfinance,alpha_vantage"
        first_error = RuntimeError("yfinance down")
        second_error = RuntimeError("alpha_vantage down")

        with patch.dict(VENDOR_METHODS, {
            "get_stock_data": {
                "yfinance": MagicMock(side_effect=first_error),
                "alpha_vantage": MagicMock(side_effect=second_error),
            },
        }), pytest.raises(RuntimeError, match="yfinance down"):
            route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-15")

    def test_unsupported_method_raises(self):
        with pytest.raises(ValueError, match="not found in any category"):
            route_to_vendor("nonexistent_method", "AAPL")


# ---------------------------------------------------------------------------
# TOOLS_CATEGORIES structure integrity
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestToolsCategoriesIntegrity:
    def test_all_categories_have_description(self):
        for cat, info in TOOLS_CATEGORIES.items():
            assert "description" in info, f"{cat} missing description"
            assert isinstance(info["description"], str)

    def test_all_categories_have_tools(self):
        for cat, info in TOOLS_CATEGORIES.items():
            assert "tools" in info, f"{cat} missing tools"
            assert len(info["tools"]) > 0, f"{cat} has empty tools list"

    def test_all_categorized_tools_have_vendor_methods(self):
        for cat, info in TOOLS_CATEGORIES.items():
            for tool_name in info["tools"]:
                assert tool_name in VENDOR_METHODS, (
                    f"Tool '{tool_name}' in category '{cat}' has no VENDOR_METHODS entry"
                )
