import sys
import types

import pandas as pd
import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows.china_data import (
    ChinaDataUnavailableError,
    get_stock_tushare,
)
from tradingagents.dataflows.config import set_config


def test_get_stock_tushare_formats_daily_data_and_logs_raw(monkeypatch, tmp_path):
    calls = {}

    class FakePro:
        def daily(self, **kwargs):
            calls["daily"] = kwargs
            return pd.DataFrame(
                [
                    {
                        "ts_code": "002636.SZ",
                        "trade_date": "20260105",
                        "open": 10.0,
                        "high": 10.5,
                        "low": 9.8,
                        "close": 10.2,
                        "pre_close": 10.0,
                        "change": 0.2,
                        "pct_chg": 2.0,
                        "vol": 1000,
                        "amount": 2000,
                    }
                ]
            )

    fake_tushare = types.SimpleNamespace(
        set_token=lambda token: calls.setdefault("token", token),
        pro_api=lambda token: FakePro(),
    )

    monkeypatch.setitem(sys.modules, "tushare", fake_tushare)
    monkeypatch.setenv("TUSHARE_TOKEN", "token-test")
    set_config({"results_dir": str(tmp_path)})

    result = get_stock_tushare("002636", "2026-01-01", "2026-01-31")

    assert calls["daily"]["ts_code"] == "002636.SZ"
    assert calls["daily"]["start_date"] == "20260101"
    assert "Source: tushare" in result
    assert "2026-01-05" in result
    raw_files = list((tmp_path / "002636" / "2026-01-31" / "data").glob("tushare_get_stock_*.json"))
    assert len(raw_files) == 1


def test_route_to_vendor_falls_back_from_tushare_to_akshare_for_a_shares(monkeypatch):
    calls = []

    def tushare_impl(*args, **kwargs):
        calls.append("tushare")
        raise ChinaDataUnavailableError("missing tushare")

    def akshare_impl(*args, **kwargs):
        calls.append("akshare")
        return "akshare data"

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "tushare,akshare,yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "tushare": tushare_impl,
            "akshare": akshare_impl,
            "yfinance": lambda *args, **kwargs: "yfinance data",
        },
    )

    result = interface.route_to_vendor("get_stock_data", "002636.SZ", "2026-01-01", "2026-01-31")

    assert result == "akshare data"
    assert calls == ["tushare", "akshare"]


def test_route_to_vendor_skips_yfinance_for_a_shares(monkeypatch):
    """A-share tickers must not try yfinance (needs VPN, poor coverage).

    Even when yfinance is listed first in the vendor config, it is skipped
    for A-share tickers so tushare/akshare are the primary sources.
    """
    calls = []

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "yfinance,tushare,akshare")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "yfinance": lambda *args, **kwargs: calls.append("yfinance") or "yfinance data",
            "tushare": lambda *args, **kwargs: calls.append("tushare") or "tushare data",
            "akshare": lambda *args, **kwargs: calls.append("akshare") or "akshare data",
        },
    )

    result = interface.route_to_vendor("get_stock_data", "002636.SZ", "2026-01-01", "2026-01-08")

    assert result == "tushare data"
    assert calls == ["tushare"]


def test_route_to_vendor_skips_china_sources_for_non_a_share_symbols(monkeypatch):
    calls = []

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "tushare,akshare,yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "tushare": lambda *args, **kwargs: calls.append("tushare") or "tushare data",
            "akshare": lambda *args, **kwargs: calls.append("akshare") or "akshare data",
            "yfinance": lambda *args, **kwargs: calls.append("yfinance") or "yfinance data",
        },
    )

    result = interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-31")

    assert result == "yfinance data"
    assert calls == ["yfinance"]


def test_route_to_vendor_raises_when_required_data_is_unavailable(monkeypatch):
    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "yfinance,alpha_vantage")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "yfinance": lambda *args, **kwargs: "No data found for symbol 'AAPL'",
            "alpha_vantage": lambda *args, **kwargs: "Error retrieving stock data",
        },
    )
    set_config({"halt_on_missing_data": True})

    with pytest.raises(interface.DataUnavailableError) as exc:
        interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-31")

    assert "Data unavailable for 'get_stock_data'" in str(exc.value)


def test_route_to_vendor_returns_sentinel_when_all_vendors_in_cooldown(monkeypatch):
    """When every vendor is in cooldown, a halt-on-missing method must return
    a NO_DATA_AVAILABLE sentinel, not raise.  A cooldown is transient and the
    agent should report 'unavailable' rather than crash the whole turn."""
    import time as _time

    from tradingagents.dataflows.health import Cooldown, VendorHealthKey

    fake_cooldown = Cooldown(
        key=VendorHealthKey("yfinance", "a_share", "get_indicators"),
        reason="rate_limit",
        retry_at=_time.monotonic() + 60.0,
    )

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_indicators",
        {"yfinance": lambda *args, **kwargs: "should not be called"},
    )
    monkeypatch.setattr(
        interface._vendor_health,
        "cooldown_for",
        lambda **kwargs: fake_cooldown,
    )
    set_config({"halt_on_missing_data": True})

    result = interface.route_to_vendor("get_indicators", "600519.SS", "2026-01-01", "2026-01-31")

    assert result.startswith("NO_DATA_AVAILABLE:")
    assert "cooldown" in result.lower()
