"""Tests for the East Money (东方财富) A-share news vendor and its auto-routing."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from tradingagents.dataflows import eastmoney_news
from tradingagents.dataflows.eastmoney_news import get_news_eastmoney, is_ashare


def _jsonp(articles: list[dict]) -> bytes:
    body = json.dumps({"code": 0, "result": {"cmsArticleWebOld": articles}}, ensure_ascii=False)
    return f"cb({body});".encode("utf-8")


@contextmanager
def _fake_response(payload: bytes):
    class _Resp:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    yield _Resp()


_ARTICLES = [
    {
        "date": "2026-05-30 06:54:37",
        "title": "贵州茅台(<em>600519</em>.SH)一季报点评",
        "content": "净利润同比增长。",
        "mediaName": "每日经济新闻",
        "url": "http://finance.eastmoney.com/a/1.html",
    },
    {
        "date": "2026-04-01 09:00:00",  # before the window
        "title": "旧闻不应入选",
        "content": "",
        "mediaName": "证券时报网",
        "url": "http://finance.eastmoney.com/a/2.html",
    },
]


@pytest.mark.unit
class TestIsAshare:
    def test_shanghai_and_shenzhen_are_ashares(self):
        assert is_ashare("600519.SS")
        assert is_ashare("000858.SZ")
        assert is_ashare("600519.ss")  # case-insensitive

    def test_other_markets_are_not(self):
        for t in ("AAPL", "0700.HK", "7203.T", "BTC-USD", "RELIANCE.NS"):
            assert not is_ashare(t)


@pytest.mark.unit
class TestGetNewsEastmoney:
    def test_non_ashare_returns_out_of_scope_without_network(self):
        with patch.object(eastmoney_news, "urlopen") as m:
            out = get_news_eastmoney("AAPL", "2026-05-01", "2026-06-02")
        m.assert_not_called()
        assert "out of scope" in out

    def test_parses_filters_and_strips_tags(self):
        with patch.object(eastmoney_news, "urlopen", return_value=_fake_response(_jsonp(_ARTICLES))):
            out = get_news_eastmoney("600519.SS", "2026-05-01", "2026-06-02")
        assert "East Money" in out
        assert "贵州茅台(600519.SH)一季报点评" in out  # <em> tags stripped
        assert "每日经济新闻" in out
        assert "旧闻不应入选" not in out  # filtered out by date window

    def test_http_error_degrades_gracefully(self):
        err = HTTPError("u", 406, "Not Acceptable", {}, None)
        with patch.object(eastmoney_news, "urlopen", side_effect=err):
            out = get_news_eastmoney("600519.SS", "2026-05-01", "2026-06-02")
        assert "unavailable" in out  # never raises

    def test_empty_result_reports_no_news(self):
        with patch.object(eastmoney_news, "urlopen", return_value=_fake_response(_jsonp([]))):
            out = get_news_eastmoney("600519.SS", "2026-05-01", "2026-06-02")
        assert "No news found" in out


@pytest.mark.unit
class TestRouting:
    """A-share get_news must prefer East Money; other markets must not."""

    @staticmethod
    def _patched_vendors():
        # VENDOR_METHODS caches function references at import time, so patch the
        # dict entries directly rather than the module-level names.
        from tradingagents.dataflows import interface

        em = lambda *a, **k: "EASTMONEY"  # noqa: E731
        yf = lambda *a, **k: "YFINANCE"  # noqa: E731
        patched = dict(interface.VENDOR_METHODS["get_news"])
        patched.update({"eastmoney": em, "yfinance": yf})
        return interface, patched

    def test_ashare_routes_to_eastmoney(self):
        interface, patched = self._patched_vendors()
        # Pin the configured news vendor so the test is independent of any
        # global config another test may have mutated.
        with patch.dict(interface.VENDOR_METHODS, {"get_news": patched}), \
             patch.object(interface, "get_vendor", return_value="yfinance"):
            result = interface.route_to_vendor("get_news", "600519.SS", "2026-05-01", "2026-06-02")
        assert result == "EASTMONEY"

    def test_us_ticker_routes_to_yfinance(self):
        interface, patched = self._patched_vendors()
        with patch.dict(interface.VENDOR_METHODS, {"get_news": patched}), \
             patch.object(interface, "get_vendor", return_value="yfinance"):
            result = interface.route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-06-02")
        assert result == "YFINANCE"
