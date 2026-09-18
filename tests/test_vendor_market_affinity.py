"""The router skips vendors whose market affinity doesn't match the ticker.

With ``data_vendors="brapi,yfinance"`` the B3-only brapi vendor must be tried
for ``.SA`` tickers and skipped for everything else, with no per-run config.
"""
import copy

import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import NoMarketDataError


@pytest.fixture(autouse=True)
def _fresh_config():
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    yield
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)


@pytest.fixture
def calls(monkeypatch):
    """Patch get_stock_data vendors; return the ordered list of vendors tried."""
    tried = []

    def brapi(symbol, *a, **k):
        tried.append("brapi")
        raise NoMarketDataError(symbol, symbol, "no rows")

    def yfinance(symbol, *a, **k):
        tried.append("yfinance")
        return "YF_DATA"

    monkeypatch.setitem(
        interface.VENDOR_METHODS, "get_stock_data",
        {"brapi": brapi, "yfinance": yfinance},
    )
    set_config({"data_vendors": {"core_stock_apis": "brapi,yfinance"}})
    return tried


@pytest.mark.unit
def test_b3_ticker_tries_brapi_then_yfinance(calls):
    result = interface.route_to_vendor("get_stock_data", "PETR4.SA", "2026-01-01", "2026-01-10")
    assert calls == ["brapi", "yfinance"]
    assert result == "YF_DATA"


@pytest.mark.unit
def test_b3_ticker_match_is_case_insensitive(calls):
    interface.route_to_vendor("get_stock_data", "petr4.sa", "2026-01-01", "2026-01-10")
    assert calls == ["brapi", "yfinance"]


@pytest.mark.unit
def test_non_b3_ticker_skips_brapi(calls):
    result = interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
    assert calls == ["yfinance"]
    assert result == "YF_DATA"


@pytest.mark.unit
def test_brapi_only_chain_is_not_emptied_for_non_b3_ticker(calls):
    # If filtering would leave nothing, the configured chain is kept as-is.
    set_config({"data_vendors": {"core_stock_apis": "brapi"}})
    result = interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
    assert calls == ["brapi"]
    assert "NO_DATA_AVAILABLE" in result
