from unittest import mock

import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.india.symbols import IndiaSymbolError


@pytest.mark.unit
def test_india_router_rejects_non_india_before_yfinance_fallback():
    set_config(
        {
            "market_scope": "india",
            "allow_non_india_tickers": False,
            "data_vendors": {"core_stock_apis": "india,yfinance"},
        }
    )
    with pytest.raises(IndiaSymbolError):
        interface.route_to_vendor("get_stock_data", "AAPL", "2026-06-01", "2026-06-05")


@pytest.mark.unit
def test_india_router_normalizes_bare_indian_symbol():
    set_config(
        {
            "market_scope": "india",
            "allow_non_india_tickers": False,
            "data_vendors": {"core_stock_apis": "india"},
        }
    )

    def fake_india(symbol, start, end):
        return f"{symbol}|{start}|{end}"

    with mock.patch.dict(interface.VENDOR_METHODS, {"get_stock_data": {"india": fake_india}}, clear=False):
        result = interface.route_to_vendor("get_stock_data", "RELIANCE", "2026-06-01", "2026-06-05")
    assert result == "RELIANCE.NS|2026-06-01|2026-06-05"
