from unittest.mock import patch

import pandas as pd

from tradingagents.dataflows.market_prices import (
    MarketPricesClient,
    get_bitcoin_price_snapshot,
    get_gold_price_snapshot,
    get_oil_prices_snapshot,
)


def _market_price_df() -> pd.DataFrame:
    symbols = ["GC=F", "CL=F", "BZ=F", "BTC-USD"]
    idx = pd.date_range("2026-03-28", periods=3, freq="D")
    close_data = {
        "GC=F": [3050.0, 3060.0, 3075.0],
        "CL=F": [69.0, 70.5, 71.0],
        "BZ=F": [72.0, 73.0, 73.8],
        "BTC-USD": [82500.0, 83200.0, 84150.0],
    }
    multi_df = pd.DataFrame(close_data, index=idx)
    multi_df.columns = pd.MultiIndex.from_product([["Close"], symbols])
    return multi_df


def test_market_prices_client_fetches_all_rows():
    with patch("tradingagents.dataflows.market_prices.safe_yf_download", return_value=_market_price_df()):
        rows = MarketPricesClient().fetch_rows()

    assert set(rows) == {"Gold", "WTI Crude", "Brent Crude", "Bitcoin"}
    assert rows["Gold"].current_price == 3075.0
    assert rows["Bitcoin"].current_price == 84150.0


def test_get_gold_price_snapshot_formats_markdown():
    with patch("tradingagents.dataflows.market_prices.safe_yf_download", return_value=_market_price_df()):
        result = get_gold_price_snapshot()

    assert result.startswith("# Gold Price Snapshot")
    assert "Gold" in result
    assert "GC=F" in result


def test_get_oil_prices_snapshot_formats_both_contracts():
    with patch("tradingagents.dataflows.market_prices.safe_yf_download", return_value=_market_price_df()):
        result = get_oil_prices_snapshot()

    assert result.startswith("# Oil Price Snapshot")
    assert "WTI Crude" in result
    assert "Brent Crude" in result


def test_get_bitcoin_price_snapshot_formats_markdown():
    with patch("tradingagents.dataflows.market_prices.safe_yf_download", return_value=_market_price_df()):
        result = get_bitcoin_price_snapshot()

    assert result.startswith("# Bitcoin Price Snapshot")
    assert "Bitcoin" in result
    assert "BTC-USD" in result
