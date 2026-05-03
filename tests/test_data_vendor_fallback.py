from yfinance.exceptions import YFRateLimitError
import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config


def test_route_to_vendor_falls_back_when_yfinance_is_rate_limited(monkeypatch):
    calls = []

    def yfinance_impl(*args, **kwargs):
        calls.append("yfinance")
        raise YFRateLimitError()

    def alpha_vantage_impl(*args, **kwargs):
        calls.append("alpha_vantage")
        return "alpha fallback data"

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "yfinance": yfinance_impl,
            "alpha_vantage": alpha_vantage_impl,
        },
    )

    result = interface.route_to_vendor(
        "get_stock_data",
        "AAPL",
        "2026-01-01",
        "2026-01-31",
    )

    assert result == "alpha fallback data"
    assert calls == ["yfinance", "alpha_vantage"]


def test_route_to_vendor_returns_readable_message_when_fallback_is_unavailable(monkeypatch):
    def yfinance_impl(*args, **kwargs):
        raise YFRateLimitError()

    def alpha_vantage_impl(*args, **kwargs):
        raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is not set.")

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "yfinance": yfinance_impl,
            "alpha_vantage": alpha_vantage_impl,
        },
    )

    set_config({"halt_on_missing_data": True})

    with pytest.raises(interface.DataUnavailableError) as exc:
        interface.route_to_vendor(
            "get_stock_data",
            "AAPL",
            "2026-01-01",
            "2026-01-31",
        )

    assert "Data unavailable for 'get_stock_data'" in str(exc.value)
    assert "rate limited by Yahoo Finance" in str(exc.value)
    assert "ALPHA_VANTAGE_API_KEY environment variable is not set" in str(exc.value)
