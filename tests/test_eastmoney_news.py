"""Tests for the Eastmoney news vendor + auto-router.

Pins:
  1. Ticker-format conversion: ``.SS`` / ``.SZ`` strip suffix, ``.HK`` zero-pads to 5 digits.
  2. The news vendor formats Eastmoney's Chinese DataFrame into a
     Markdown report covering title / source / publish date / link.
  3. Date filtering drops articles outside the requested window.
  4. The ``auto`` vendor in ``route_to_vendor`` routes ``.HK`` / ``.SS`` /
     ``.SZ`` tickers to Eastmoney and US tickers to yfinance.
  5. ``get_global_news`` always goes to yfinance regardless of ``auto``.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows import eastmoney_news as em
from tradingagents.dataflows import interface as iface
from tradingagents.dataflows.config import set_config


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path):
    set_config({"data_cache_dir": str(tmp_path)})
    yield


def _fake_em_frame(rows):
    return pd.DataFrame(rows, columns=["关键词", "新闻标题", "新闻内容", "发布时间", "文章来源", "新闻链接"])


def test_to_eastmoney_symbol_a_share():
    sym = em._to_eastmoney_symbol("600519.SS")
    assert sym == ("600519", "Shanghai A-share")
    sym = em._to_eastmoney_symbol("000001.SZ")
    assert sym == ("000001", "Shenzhen A-share")


def test_to_eastmoney_symbol_hk_zero_pads():
    sym = em._to_eastmoney_symbol("0700.HK")
    assert sym == ("00700", "Hong Kong")
    sym = em._to_eastmoney_symbol("9988.HK")
    assert sym == ("09988", "Hong Kong")


def test_to_eastmoney_symbol_returns_none_for_unsupported():
    assert em._to_eastmoney_symbol("AAPL") is None
    assert em._to_eastmoney_symbol("D05.SI") is None  # Singapore not covered
    assert em._to_eastmoney_symbol("") is None


def test_get_news_eastmoney_formats_dataframe():
    fake = _fake_em_frame([
        ["00700", "腾讯控股回购", "腾讯今日宣布回购计划。", "2026-05-08 09:00:00", "证券时报", "https://example.com/1"],
        ["00700", "腾讯Q1财报", "营收增长10%。", "2026-05-06 14:00:00", "财新网", "https://example.com/2"],
    ])

    with patch("akshare.stock_news_em", return_value=fake):
        out = em.get_news_eastmoney("0700.HK", "2026-05-01", "2026-05-10")

    assert "腾讯控股回购" in out
    assert "腾讯Q1财报" in out
    assert "证券时报" in out
    assert "https://example.com/1" in out
    assert "Hong Kong" in out


def test_get_news_eastmoney_filters_by_date():
    fake = _fake_em_frame([
        ["600519", "在窗口内", "x", "2026-05-08 09:00:00", "界面新闻", "https://example.com/1"],
        ["600519", "窗口前", "y", "2026-04-01 09:00:00", "界面新闻", "https://example.com/2"],
        ["600519", "窗口后", "z", "2026-06-01 09:00:00", "界面新闻", "https://example.com/3"],
    ])

    with patch("akshare.stock_news_em", return_value=fake):
        out = em.get_news_eastmoney("600519.SS", "2026-05-01", "2026-05-15")

    assert "在窗口内" in out
    assert "窗口前" not in out
    assert "窗口后" not in out


def test_get_news_eastmoney_handles_unsupported_ticker():
    out = em.get_news_eastmoney("AAPL", "2026-05-01", "2026-05-10")
    assert "[Eastmoney skip" in out
    assert "AAPL" in out


def test_get_news_eastmoney_handles_fetch_error():
    with patch("akshare.stock_news_em", side_effect=RuntimeError("network down")):
        out = em.get_news_eastmoney("0700.HK", "2026-05-01", "2026-05-10")
    assert "Eastmoney fetch failed" in out
    assert "network down" in out


def test_auto_routes_hk_to_eastmoney():
    assert iface._resolve_auto_vendor("get_news", ("0700.HK", "2026-05-01", "2026-05-10")) == "eastmoney"


def test_auto_routes_a_share_to_eastmoney():
    assert iface._resolve_auto_vendor("get_news", ("600519.SS", "2026-05-01", "2026-05-10")) == "eastmoney"
    assert iface._resolve_auto_vendor("get_news", ("000001.SZ", "2026-05-01", "2026-05-10")) == "eastmoney"


def test_auto_routes_us_ticker_to_yfinance():
    assert iface._resolve_auto_vendor("get_news", ("AAPL", "2026-05-01", "2026-05-10")) == "yfinance"



def test_auto_global_news_always_yfinance():
    """get_global_news has no ticker; auto must not crash and must route to yfinance."""
    assert iface._resolve_auto_vendor("get_global_news", ("2026-05-08", 7, 10)) == "yfinance"


def test_route_to_vendor_with_auto_calls_eastmoney_for_hk(tmp_path):
    """End-to-end: when news_data='auto' and ticker is HK, the eastmoney vendor is invoked."""
    # Isolated cache dir so the per-vendor cache doesn't leak across runs.
    set_config({
        "data_cache_dir": str(tmp_path),
        "data_vendors": {"news_data": "auto"},
        "tool_vendors": {},
    })
    fake = _fake_em_frame([
        ["00700", "测试", "x", "2026-05-08 09:00:00", "test", "https://example.com"],
    ])
    with patch("akshare.stock_news_em", return_value=fake) as m:
        out = iface.route_to_vendor("get_news", "0700.HK", "2026-05-01", "2026-05-10")
    # Multi-source merge calls eastmoney + cls (HK fans to both); we only
    # care that eastmoney was reached at least once.
    assert m.call_count >= 1
    assert "测试" in out


def test_route_to_vendor_with_auto_calls_yfinance_for_us(tmp_path):
    """End-to-end: US ticker via auto goes to yfinance, not eastmoney.

    ``VENDOR_METHODS`` is a dict of function references captured at import
    time, so patching the module attribute does not redirect the call.
    Patch the dict entry directly instead.
    """
    set_config({
        "data_cache_dir": str(tmp_path),
        "data_vendors": {"news_data": "auto"},
        "tool_vendors": {},
    })
    yf_mock = MagicMock(return_value="<yf body>")
    ak_mock = MagicMock()
    original_yf = iface.VENDOR_METHODS["get_news"]["yfinance"]
    iface.VENDOR_METHODS["get_news"]["yfinance"] = yf_mock
    try:
        with patch("akshare.stock_news_em", ak_mock):
            out = iface.route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-10")
    finally:
        iface.VENDOR_METHODS["get_news"]["yfinance"] = original_yf

    yf_mock.assert_called_once()
    ak_mock.assert_not_called()
    assert out == "<yf body>"
