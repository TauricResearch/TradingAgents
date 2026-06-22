"""A-share auto-routing: Chinese tickers (.SS/.SZ) must automatically use
the akshare vendor first, while non-A-share tickers keep the configured path.
"""
import copy
import unittest
from unittest import mock

import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.akshare_utils import is_a_share


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
        """000001.SZ (SZ suffix) must also route to akshare."""
        seen = []

        def fake_akshare(symbol, *a, **k):
            seen.append(("akshare", symbol))
            return "ok"

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_stock_data": {"akshare": fake_akshare}},
        ):
            result = interface.route_to_vendor("get_stock_data", "000001.SZ", "2025-01-01", "2026-01-01")

        assert result == "ok"
        assert seen[0] == ("akshare", "000001.SZ")
