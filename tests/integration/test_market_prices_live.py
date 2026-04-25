"""Live integration tests for gold, oil, and bitcoin price tools."""

import pytest

from tradingagents.agents.utils.scanner_tools import (
    get_bitcoin_price,
    get_gold_price,
    get_oil_prices,
)
from tradingagents.dataflows.market_prices import MarketPricesClient

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket()]


def test_market_prices_client_live():
    rows = MarketPricesClient().fetch_rows()

    assert rows["Gold"].current_price > 0
    assert rows["WTI Crude"].current_price > 0
    assert rows["Brent Crude"].current_price > 0
    assert rows["Bitcoin"].current_price > 0


def test_gold_price_tool_live():
    result = get_gold_price.invoke({})
    assert result.startswith("# Gold Price Snapshot")
    assert "GC=F" in result


def test_oil_prices_tool_live():
    result = get_oil_prices.invoke({})
    assert result.startswith("# Oil Price Snapshot")
    assert "WTI Crude" in result
    assert "Brent Crude" in result


def test_bitcoin_price_tool_live():
    result = get_bitcoin_price.invoke({})
    assert result.startswith("# Bitcoin Price Snapshot")
    assert "BTC-USD" in result
