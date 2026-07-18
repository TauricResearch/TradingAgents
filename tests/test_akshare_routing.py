"""A-share auto-routing: Chinese tickers (.SS/.SZ) must automatically use
the akshare vendor first, while non-A-share tickers keep the configured path.
"""
import copy
import os
import unittest
from unittest import mock

import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.akshare_utils import (
    _DOMESTIC_HOSTS,
    _ensure_domestic_no_proxy,
    is_a_share,
)


def _reset_config():
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)


def _returns(value):
    def impl(symbol, *a, **k):
        return value
    return impl


@pytest.mark.unit
class IsAShareTests(unittest.TestCase):
    """is_a_share() must identify Shanghai (.SS) and Shenzhen (.SZ) tickers."""

    def test_shanghai_suffix(self):
        assert is_a_share("600519.SS") is True

    def test_shenzhen_suffix(self):
        assert is_a_share("000001.SZ") is True

    def test_case_insensitive(self):
        assert is_a_share("600519.ss") is True
        assert is_a_share("000001.sz") is True

    def test_us_ticker_not_a_share(self):
        assert is_a_share("AAPL") is False

    def test_hk_ticker_not_a_share(self):
        assert is_a_share("0700.HK") is False

    def test_crypto_not_a_share(self):
        assert is_a_share("BTC-USD") is False


@pytest.mark.unit
class DomesticNoProxyTests(unittest.TestCase):
    """Chinese data hosts must be added to NO_PROXY so a VPN/proxy that mangles
    TLS to domestic endpoints (SSL bad-record-mac) is bypassed for A-share data.
    """

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("NO_PROXY", "no_proxy")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_adds_domestic_hosts_when_empty(self):
        os.environ.pop("NO_PROXY", None)
        os.environ.pop("no_proxy", None)
        _ensure_domestic_no_proxy()
        for host in _DOMESTIC_HOSTS:
            assert host in os.environ["NO_PROXY"]

    def test_preserves_existing_entries(self):
        os.environ["NO_PROXY"] = "example.com"
        _ensure_domestic_no_proxy()
        assert "example.com" in os.environ["NO_PROXY"]
        assert "eastmoney.com" in os.environ["NO_PROXY"]

    def test_idempotent_no_duplicates(self):
        os.environ["NO_PROXY"] = ""
        _ensure_domestic_no_proxy()
        _ensure_domestic_no_proxy()
        assert os.environ["NO_PROXY"].split(",").count("eastmoney.com") == 1


@pytest.mark.unit
class AShareAutoRoutingTests(unittest.TestCase):
    """route_to_vendor() must prepend akshare for A-share tickers automatically."""

    def setUp(self):
        _reset_config()

    def tearDown(self):
        _reset_config()

    def test_a_share_uses_akshare_first(self):
        """600519.SS must call the akshare implementation, not yfinance."""
        akshare_called = []
        yfinance_called = []

        def fake_akshare(symbol, *a, **k):
            akshare_called.append(symbol)
            return "akshare_data"

        def fake_yfinance(symbol, *a, **k):
            yfinance_called.append(symbol)
            return "yfinance_data"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_stock_data": {"akshare": fake_akshare, "yfinance": fake_yfinance}},
        ):
            result = interface.route_to_vendor("get_stock_data", "600519.SS", "2025-01-01", "2026-01-01")

        assert result == "akshare_data"
        assert akshare_called == ["600519.SS"]
        assert yfinance_called == []

    def test_non_a_share_skips_akshare(self):
        """AAPL must not call akshare even when it is registered as a vendor."""
        akshare_called = []
        yfinance_called = []

        def fake_akshare(symbol, *a, **k):
            akshare_called.append(symbol)
            return "akshare_data"

        def fake_yfinance(symbol, *a, **k):
            yfinance_called.append(symbol)
            return "yfinance_data"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_stock_data": {"akshare": fake_akshare, "yfinance": fake_yfinance}},
        ):
            result = interface.route_to_vendor("get_stock_data", "AAPL", "2025-01-01", "2026-01-01")

        assert result == "yfinance_data"
        assert yfinance_called == ["AAPL"]
        # akshare may be tried as fallback (if yfinance succeeded first it won't be), but
        # the important thing is that yfinance responded and akshare was NOT invoked first.
        assert akshare_called == []

    def test_shenzhen_ticker_uses_akshare(self):
        """000001.SZ (SZ suffix) must also route to akshare first."""
        seen = []

        def fake_akshare(symbol, *a, **k):
            seen.append(("akshare", symbol))
            return "ok"

        def fake_yfinance(symbol, *a, **k):
            seen.append(("yfinance", symbol))
            return "yfinance_data"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_stock_data": {"akshare": fake_akshare, "yfinance": fake_yfinance}},
        ):
            result = interface.route_to_vendor("get_stock_data", "000001.SZ", "2025-01-01", "2026-01-01")

        assert result == "ok"
        assert seen[0] == ("akshare", "000001.SZ")
