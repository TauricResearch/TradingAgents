"""The stock-data tool must not hand the agent a bar with no prices.

yfinance can return the newest bar with blank OHLC but a volume (an unsettled or
glitched session). The indicator loader already drops such rows (#1201); the
stock-data CSV kept them, so the latest "session" read as blank. Now the rows are
dropped and named in the header, and a range with no close anywhere is no data.
"""
from unittest import mock

import numpy as np
import pandas as pd
import pytest

import tradingagents.dataflows.vendors.yahoo.market as yahoo_market
from tradingagents.dataflows.errors import NoMarketDataError


def _ticker(frame):
    class DummyTicker:
        def __init__(self, symbol):
            pass

        def history(self, start, end):
            return frame.copy()

    return DummyTicker


def _frame(closes):
    dates = pd.bdate_range("2026-11-16", periods=len(closes), name="Date")
    return pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes,
         "Volume": [1_000_000] * len(closes)},
        index=dates,
    )


@pytest.mark.unit
def test_trailing_bar_without_close_is_dropped_and_named():
    frame = _frame([11.02, 10.798, np.nan])
    with mock.patch.object(yahoo_market.yf, "Ticker", _ticker(frame)):
        out = yahoo_market.get_YFin_data_online("SAN.MC", "2026-11-16", "2026-11-18")
    assert "# Total records: 2" in out
    assert "# Omitted rows with no close price: 2026-11-18" in out
    rows = [line for line in out.splitlines() if line.startswith("2026-")]
    assert [r.split(",")[0] for r in rows] == ["2026-11-16", "2026-11-17"]
    assert rows[-1].split(",")[4] == "10.798"


@pytest.mark.unit
def test_complete_frame_has_no_omitted_note():
    frame = _frame([11.02, 10.798])
    with mock.patch.object(yahoo_market.yf, "Ticker", _ticker(frame)):
        out = yahoo_market.get_YFin_data_online("SAN.MC", "2026-11-16", "2026-11-17")
    assert "Omitted" not in out
    assert "# Total records: 2" in out


@pytest.mark.unit
def test_range_with_no_close_anywhere_is_no_data():
    frame = _frame([np.nan, np.nan])
    with mock.patch.object(yahoo_market.yf, "Ticker", _ticker(frame)), \
            mock.patch("tradingagents.dataflows.vendors.yahoo.common.vendor_reachable", return_value=True), \
            pytest.raises(NoMarketDataError):
        yahoo_market.get_YFin_data_online("SAN.MC", "2026-11-16", "2026-11-17")
