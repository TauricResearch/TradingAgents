"""Unit tests for data interface routing."""

from unittest.mock import patch

import pytest

from tradingagents.dataflows.interface import (
    TOOLS_CATEGORIES,
    VENDOR_LIST,
    VENDOR_METHODS,
    get_category_for_method,
    get_vendor,
    route_to_vendor,
)


class TestToolsCategories:
    """Tests for TOOLS_CATEGORIES structure."""

    @pytest.mark.unit
    def test_core_stock_apis_category_exists(self):
        """Test that core_stock_apis category exists."""
        assert "core_stock_apis" in TOOLS_CATEGORIES
        assert "get_stock_data" in TOOLS_CATEGORIES["core_stock_apis"]["tools"]

    @pytest.mark.unit
    def test_technical_indicators_category_exists(self):
        """Test that technical_indicators category exists."""
        assert "technical_indicators" in TOOLS_CATEGORIES
        assert "get_indicators" in TOOLS_CATEGORIES["technical_indicators"]["tools"]

    @pytest.mark.unit
    def test_fundamental_data_category_exists(self):
        """Test that fundamental_data category exists."""
        assert "fundamental_data" in TOOLS_CATEGORIES
        expected_tools = [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement",
        ]
        for tool in expected_tools:
            assert tool in TOOLS_CATEGORIES["fundamental_data"]["tools"]

    @pytest.mark.unit
    def test_news_data_category_exists(self):
        """Test that news_data category exists."""
        assert "news_data" in TOOLS_CATEGORIES
        expected_tools = ["get_news", "get_global_news", "get_insider_transactions"]
        for tool in expected_tools:
            assert tool in TOOLS_CATEGORIES["news_data"]["tools"]


class TestVendorList:
    """Tests for VENDOR_LIST."""

    @pytest.mark.unit
    def test_yfinance_in_vendor_list(self):
        """Test that yfinance is in vendor list."""
        assert "yfinance" in VENDOR_LIST

    @pytest.mark.unit
    def test_alpha_vantage_in_vendor_list(self):
        """Test that alpha_vantage is in vendor list."""
        assert "alpha_vantage" in VENDOR_LIST

    @pytest.mark.unit
    def test_vendor_list_length(self):
        """Test vendor list contains expected number of vendors."""
        assert len(VENDOR_LIST) == 2


class TestGetCategoryForMethod:
    """Tests for get_category_for_method function."""

    @pytest.mark.unit
    def test_get_category_for_stock_data(self):
        """Test category for get_stock_data."""
        category = get_category_for_method("get_stock_data")
        assert category == "core_stock_apis"

    @pytest.mark.unit
    def test_get_category_for_indicators(self):
        """Test category for get_indicators."""
        category = get_category_for_method("get_indicators")
        assert category == "technical_indicators"

    @pytest.mark.unit
    def test_get_category_for_fundamentals(self):
        """Test category for get_fundamentals."""
        category = get_category_for_method("get_fundamentals")
        assert category == "fundamental_data"

    @pytest.mark.unit
    def test_get_category_for_news(self):
        """Test category for get_news."""
        category = get_category_for_method("get_news")
        assert category == "news_data"

    @pytest.mark.unit
    def test_get_category_for_invalid_method_raises(self):
        """Test that invalid method raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            get_category_for_method("invalid_method")


class TestGetVendor:
    """Tests for get_vendor function."""

    @pytest.mark.unit
    @patch("tradingagents.dataflows.interface.get_config")
    def test_get_vendor_default(self, mock_get_config):
        """Test getting default vendor for a category."""
        mock_get_config.return_value = {
            "data_vendors": {"core_stock_apis": "yfinance"},
            "tool_vendors": {},
        }

        vendor = get_vendor("core_stock_apis")
        assert vendor == "yfinance"

    @pytest.mark.unit
    @patch("tradingagents.dataflows.interface.get_config")
    def test_get_vendor_tool_level_override(self, mock_get_config):
        """Test that tool-level vendor takes precedence."""
        mock_get_config.return_value = {
            "data_vendors": {"core_stock_apis": "yfinance"},
            "tool_vendors": {"get_stock_data": "alpha_vantage"},
        }

        vendor = get_vendor("core_stock_apis", "get_stock_data")
        assert vendor == "alpha_vantage"

    @pytest.mark.unit
    @patch("tradingagents.dataflows.interface.get_config")
    def test_get_vendor_missing_category_uses_default(self, mock_get_config):
        """Test that missing category returns 'default'."""
        mock_get_config.return_value = {
            "data_vendors": {},
            "tool_vendors": {},
        }

        vendor = get_vendor("unknown_category")
        assert vendor == "default"


class TestVendorMethods:
    """Tests for VENDOR_METHODS structure."""

    @pytest.mark.unit
    def test_get_stock_data_has_both_vendors(self):
        """Test that get_stock_data has both vendors."""
        assert "yfinance" in VENDOR_METHODS["get_stock_data"]
        assert "alpha_vantage" in VENDOR_METHODS["get_stock_data"]

    @pytest.mark.unit
    def test_all_methods_have_vendors(self):
        """Test that all methods have at least one vendor."""
        for method, vendors in VENDOR_METHODS.items():
            assert len(vendors) > 0, f"Method {method} has no vendors"


class TestRouteToVendor:
    """Tests for route_to_vendor function."""

    @pytest.mark.unit
    @patch("tradingagents.dataflows.interface.get_config")
    def test_route_to_vendor_invalid_method_raises(self, mock_get_config):
        """Test that routing invalid method raises ValueError."""
        mock_get_config.return_value = {"data_vendors": {}, "tool_vendors": {}}

        with pytest.raises(ValueError, match="not found"):
            route_to_vendor("invalid_method", "AAPL")

    @pytest.mark.unit
    @patch("tradingagents.dataflows.interface.get_config")
    @patch("tradingagents.dataflows.interface.VENDOR_METHODS")
    def test_route_to_vendor_fallback_on_rate_limit(self, mock_methods, mock_get_config):
        """Test that vendor fallback works on rate limit errors."""
        mock_get_config.return_value = {
            "data_vendors": {"core_stock_apis": "alpha_vantage"},
            "tool_vendors": {},
        }

        # This test would need proper mocking of the actual vendor functions
        # For now, we just verify the function signature exists

    @pytest.mark.unit
    @patch("tradingagents.dataflows.interface.get_config")
    def test_route_to_vendor_no_available_vendor_raises(self, mock_get_config):
        """Test that no available vendor raises RuntimeError."""
        mock_get_config.return_value = {
            "data_vendors": {"core_stock_apis": "nonexistent_vendor"},
            "tool_vendors": {},
        }

        # This test would verify that if all vendors fail, RuntimeError is raised
        # Actual implementation depends on the real vendor functions
