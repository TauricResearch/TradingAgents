import pytest

from tradingagents.dataflows.config import reset_config, use_config
from tradingagents.dataflows.interface import get_vendor, route_to_vendor


def test_get_vendor_rejects_non_string_category_vendor():
    token = use_config({"data_vendors": {"core_stock_apis": ["yfinance"]}})
    try:
        with pytest.raises(ValueError, match="must be a string"):
            get_vendor("core_stock_apis", "get_stock_data")
    finally:
        reset_config(token)


def test_get_vendor_rejects_non_string_tool_vendor():
    token = use_config({"tool_vendors": {"get_stock_data": ["yfinance"]}})
    try:
        with pytest.raises(ValueError, match="must be a string"):
            get_vendor("core_stock_apis", "get_stock_data")
    finally:
        reset_config(token)


def test_route_to_vendor_rejects_unknown_method_before_routing():
    with pytest.raises(ValueError, match="not found in any category"):
        route_to_vendor("missing_method")
