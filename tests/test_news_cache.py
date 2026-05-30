"""Tests for news result caching across analysts."""

import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows.interface import _news_result_cache, route_to_vendor


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure a clean cache for every test."""
    _news_result_cache.clear()
    yield
    _news_result_cache.clear()


class TestNewsResultCache:
    def test_same_call_returns_cached_result(self, monkeypatch):
        call_count = {"n": 0}

        def counting_news(*args, **kwargs):
            call_count["n"] += 1
            return f"news result #{call_count['n']}"

        monkeypatch.setattr(interface, "get_vendor", lambda cat, method=None: "tavily")
        monkeypatch.setitem(
            interface.VENDOR_METHODS,
            "get_news",
            {"tavily": counting_news},
        )

        r1 = route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")
        r2 = route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")

        assert r1 == r2
        assert call_count["n"] == 1  # only one actual call

    def test_different_params_bypass_cache(self, monkeypatch):
        call_count = {"n": 0}

        def counting_news(*args, **kwargs):
            call_count["n"] += 1
            return f"news result #{call_count['n']}"

        monkeypatch.setattr(interface, "get_vendor", lambda cat, method=None: "tavily")
        monkeypatch.setitem(
            interface.VENDOR_METHODS,
            "get_news",
            {"tavily": counting_news},
        )

        route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")
        route_to_vendor("get_news", "AAPL", "2026-05-08", "2026-05-14")

        assert call_count["n"] == 2

    def test_non_news_methods_not_cached(self, monkeypatch):
        call_count = {"n": 0}

        def counting_stock(*args, **kwargs):
            call_count["n"] += 1
            return f"stock result #{call_count['n']}"

        monkeypatch.setattr(interface, "get_vendor", lambda cat, method=None: "yfinance")
        monkeypatch.setitem(
            interface.VENDOR_METHODS,
            "get_stock_data",
            {"yfinance": counting_stock},
        )

        route_to_vendor("get_stock_data", "AAPL", "2026-05-01", "2026-05-07")
        route_to_vendor("get_stock_data", "AAPL", "2026-05-01", "2026-05-07")

        assert call_count["n"] == 2  # no caching for non-news

    def test_global_news_also_cached(self, monkeypatch):
        call_count = {"n": 0}

        def counting_global(*args, **kwargs):
            call_count["n"] += 1
            return f"global #{call_count['n']}"

        monkeypatch.setattr(interface, "get_vendor", lambda cat, method=None: "tavily")
        monkeypatch.setitem(
            interface.VENDOR_METHODS,
            "get_global_news",
            {"tavily": counting_global},
        )

        route_to_vendor("get_global_news", "2026-05-07")
        route_to_vendor("get_global_news", "2026-05-07")

        assert call_count["n"] == 1

    def test_cache_cleared_externally(self, monkeypatch):
        call_count = {"n": 0}

        def counting_news(*args, **kwargs):
            call_count["n"] += 1
            return f"result #{call_count['n']}"

        monkeypatch.setattr(interface, "get_vendor", lambda cat, method=None: "tavily")
        monkeypatch.setitem(
            interface.VENDOR_METHODS,
            "get_news",
            {"tavily": counting_news},
        )

        route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")
        _news_result_cache.clear()
        route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")

        assert call_count["n"] == 2  # cache was cleared, so 2 calls
