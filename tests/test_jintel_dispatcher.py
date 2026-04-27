"""Tests for ``route_to_vendor`` fallback semantics in ``interface.py``."""

from __future__ import annotations

import logging

import pytest

from tradingagents.dataflows import interface as iface
from tradingagents.dataflows.jintel import (
    JintelNoDataError,
    JintelRateLimitError,
)

pytestmark = pytest.mark.unit


def _patch_method(monkeypatch, method, impls):
    new = dict(iface.VENDOR_METHODS)
    new[method] = impls
    monkeypatch.setattr(iface, "VENDOR_METHODS", new)


def _patch_primary(monkeypatch, vendor):
    monkeypatch.setattr(iface, "get_vendor", lambda category, m=None: vendor)


class TestRouteToVendor:
    def test_jintel_rate_limit_falls_to_yfinance(self, monkeypatch, caplog):
        def fail(*a, **kw):
            raise JintelRateLimitError("simulated 429")

        def yfin(*a, **kw):
            return "yfinance"

        _patch_method(monkeypatch, "get_stock_data",
                      {"jintel": fail, "yfinance": yfin})
        _patch_primary(monkeypatch, "jintel")
        with caplog.at_level(logging.WARNING):
            assert iface.route_to_vendor(
                "get_stock_data", "X", "Y", "Z") == "yfinance"
        assert "rate-limited" in caplog.text

    def test_jintel_no_data_falls_to_yfinance(self, monkeypatch, caplog):
        def fail(*a, **kw):
            raise JintelNoDataError("Entity not found")

        def yfin(*a, **kw):
            return "yfinance"

        _patch_method(monkeypatch, "get_stock_data",
                      {"jintel": fail, "yfinance": yfin})
        _patch_primary(monkeypatch, "jintel")
        with caplog.at_level(logging.WARNING):
            assert iface.route_to_vendor(
                "get_stock_data", "X", "Y", "Z") == "yfinance"
        assert "no-data" in caplog.text

    def test_alpha_vantage_rate_limit_falls_to_next(self, monkeypatch, caplog):
        from tradingagents.dataflows.alpha_vantage_common import (
            AlphaVantageRateLimitError,
        )

        def fail_av(*a, **kw):
            raise AlphaVantageRateLimitError("av 429")

        def yfin(*a, **kw):
            return "yfinance"

        _patch_method(monkeypatch, "get_stock_data",
                      {"alpha_vantage": fail_av, "yfinance": yfin})
        _patch_primary(monkeypatch, "alpha_vantage")
        with caplog.at_level(logging.WARNING):
            assert iface.route_to_vendor(
                "get_stock_data", "X", "Y", "Z") == "yfinance"
        assert "rate-limited" in caplog.text

    def test_all_vendors_fail_raises_runtime_error(self, monkeypatch):
        def fail(*a, **kw):
            raise JintelNoDataError("no")

        _patch_method(monkeypatch, "get_stock_data",
                      {"jintel": fail, "yfinance": fail})
        _patch_primary(monkeypatch, "jintel")
        with pytest.raises(RuntimeError, match="No available vendor"):
            iface.route_to_vendor("get_stock_data", "X", "Y", "Z")

    def test_unrelated_exception_propagates(self, monkeypatch):
        """Non-rate-limit, non-no-data errors must NOT trigger fallback."""
        def fail_other(*a, **kw):
            raise ValueError("unexpected boom")

        def yfin(*a, **kw):
            return "yfinance"

        _patch_method(monkeypatch, "get_stock_data",
                      {"jintel": fail_other, "yfinance": yfin})
        _patch_primary(monkeypatch, "jintel")
        with pytest.raises(ValueError, match="unexpected boom"):
            iface.route_to_vendor("get_stock_data", "X", "Y", "Z")

    def test_jintel_only_method_no_fallback_chain(self, monkeypatch):
        def fail(*a, **kw):
            raise JintelNoDataError("none")

        _patch_method(monkeypatch, "get_filings", {"jintel": fail})
        _patch_primary(monkeypatch, "jintel")
        with pytest.raises(RuntimeError, match="No available vendor"):
            iface.route_to_vendor("get_filings", "X")
