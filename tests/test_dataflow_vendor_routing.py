import pytest
import requests
from yfinance.exceptions import YFRateLimitError

from tradingagents.dataflows.config import reset_config, use_config
from tradingagents.dataflows import interface
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


def test_route_to_vendor_falls_back_after_generic_transient_error(monkeypatch):
    calls = []

    def primary(*args, **kwargs):
        calls.append("primary")
        raise requests.Timeout("temporary timeout")

    def fallback(*args, **kwargs):
        calls.append("fallback")
        return "fallback result"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "yfinance": primary,
            "alpha_vantage": fallback,
        },
    )
    token = use_config({"data_vendors": {"core_stock_apis": "yfinance"}})
    try:
        assert route_to_vendor("get_stock_data", "NVDA", "2026-01-01", "2026-01-10") == "fallback result"
        assert calls == ["primary", "fallback"]
    finally:
        reset_config(token)


def test_route_to_vendor_falls_back_after_connection_error(monkeypatch):
    calls = []

    def primary(*args, **kwargs):
        calls.append("primary")
        raise requests.ConnectionError("temporary connection reset")

    def fallback(*args, **kwargs):
        calls.append("fallback")
        return "fallback result"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "yfinance": primary,
            "alpha_vantage": fallback,
        },
    )
    token = use_config({"data_vendors": {"core_stock_apis": "yfinance"}})
    try:
        assert route_to_vendor("get_stock_data", "NVDA", "2026-01-01", "2026-01-10") == "fallback result"
        assert calls == ["primary", "fallback"]
    finally:
        reset_config(token)


def test_route_to_vendor_falls_back_after_yfinance_rate_limit(monkeypatch):
    calls = []

    def primary(*args, **kwargs):
        calls.append("primary")
        raise YFRateLimitError()

    def fallback(*args, **kwargs):
        calls.append("fallback")
        return "fallback result"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "yfinance": primary,
            "alpha_vantage": fallback,
        },
    )
    token = use_config({"data_vendors": {"core_stock_apis": "yfinance"}})
    try:
        assert route_to_vendor("get_stock_data", "NVDA", "2026-01-01", "2026-01-10") == "fallback result"
        assert calls == ["primary", "fallback"]
    finally:
        reset_config(token)
