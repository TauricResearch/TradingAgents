"""AKShare (Sina) vendor: caching, symbol routing, and error reporting."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors import akshare as akshare_vendor
from tradingagents.dataflows.vendors.akshare import market as ak_market


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2026-08-01", periods=20),
            "open": [10.0] * 20,
            "high": [10.5] * 20,
            "low": [9.8] * 20,
            "close": [10.2] * 20,
            "volume": [1_000_000] * 20,
        }
    )


class _FakeAk:
    def __init__(self) -> None:
        self.calls = 0

    def stock_us_daily(self, symbol: str, adjust: str) -> pd.DataFrame:
        self.calls += 1
        return _sample_frame()

    def stock_zh_a_daily(self, symbol: str, adjust: str) -> pd.DataFrame:
        self.calls += 1
        return _sample_frame()


@pytest.fixture
def fake_ak(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeAk()
    monkeypatch.setattr(ak_market, "ak", fake)
    ak_market._ohlcv_cache.clear()
    yield fake
    ak_market._ohlcv_cache.clear()


def test_second_fetch_hits_cache(fake_ak: _FakeAk) -> None:
    first = ak_market._fetch_ohlcv("NVDA")
    second = ak_market._fetch_ohlcv("NVDA")
    assert fake_ak.calls == 1
    assert len(first) == len(second)


def test_cache_key_is_case_insensitive(fake_ak: _FakeAk) -> None:
    ak_market._fetch_ohlcv("NVDA")
    ak_market._fetch_ohlcv("nvda")
    assert fake_ak.calls == 1


def test_unknown_symbol_reports_friendly_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(symbol: str, adjust: str) -> pd.DataFrame:
        raise IndexError("list index out of range")

    monkeypatch.setattr(ak_market.ak, "stock_us_daily", boom)
    with pytest.raises(NoMarketDataError, match="not recognized by Sina"):
        ak_market._fetch_ohlcv("0700.HK")


def test_a_share_codes_route_to_zh_daily(fake_ak: _FakeAk) -> None:
    ak_market._fetch_ohlcv("sz000001")
    assert fake_ak.calls == 1


def test_stock_data_csv_contract(fake_ak: _FakeAk) -> None:
    out = ak_market.get_akshare_stock_data("NVDA", "2026-08-03", "2026-08-07")
    assert out.startswith("# Stock data for NVDA")
    assert "akshare/Sina" in out
    assert "Date,Open,High,Low,Close,Volume" in out
