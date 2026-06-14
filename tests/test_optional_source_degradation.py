"""Optional/enrichment data sources degrade to a sentinel instead of aborting
the run; core data sources still raise so a broken primary stays loud.

Regression for the FRED crash: a missing FRED_API_KEY (macro_data) raised
VendorNotConfiguredError up through the news node and killed an otherwise-
complete LangGraph run.
"""

from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.errors import NoMarketDataError, VendorNotConfiguredError


@pytest.fixture(autouse=True)
def _fresh_config():
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    yield
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)


def _patch_impl(method, vendor, fn):
    return patch.dict(interface.VENDOR_METHODS[method], {vendor: fn})


@pytest.mark.unit
def test_macro_missing_key_returns_sentinel_not_raises():
    """macro_data is optional: a missing key degrades, never raises."""
    def _missing_key(*_a, **_k):
        raise VendorNotConfiguredError("FRED_API_KEY environment variable is not set.")

    with _patch_impl("get_macro_indicators", "fred", _missing_key):
        out = interface.route_to_vendor("get_macro_indicators", "cpi", "2026-06-12")

    assert "optional data source unavailable" in out.lower()
    assert "do not estimate or fabricate" in out.lower()


@pytest.mark.unit
def test_prediction_markets_network_error_returns_sentinel():
    """prediction_markets is optional: a hard error degrades, never raises."""
    def _boom(*_a, **_k):
        raise RuntimeError("gamma-api.polymarket.com unreachable")

    with _patch_impl("get_prediction_markets", "polymarket", _boom):
        out = interface.route_to_vendor("get_prediction_markets", "Fed rate cut")

    assert "optional data source unavailable" in out.lower()


@pytest.mark.unit
def test_core_category_still_raises_on_hard_error():
    """A core category (fundamentals) must still raise — never silently degrade."""
    config_module._config["data_vendors"]["fundamental_data"] = "yfinance"

    def _boom(*_a, **_k):
        raise RuntimeError("network down")

    with _patch_impl("get_fundamentals", "yfinance", _boom), \
            pytest.raises(RuntimeError, match="network down"):
        interface.route_to_vendor("get_fundamentals", "NVDA", "2026-06-12")


@pytest.mark.unit
def test_market_no_data_sentinel_path_unaffected():
    """The pre-existing NO_DATA path for NoMarketDataError still wins."""
    config_module._config["data_vendors"]["core_stock_apis"] = "yfinance"

    def _no_data(*_a, **_k):
        raise NoMarketDataError("FOOBAR", detail="symbol not found")

    with _patch_impl("get_stock_data", "yfinance", _no_data):
        out = interface.route_to_vendor("get_stock_data", "FOOBAR", "2026-06-12", "2026-06-12")

    assert out.startswith("NO_DATA_AVAILABLE")
