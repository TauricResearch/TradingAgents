"""ATR + chandelier trailing stops (track T2 risk realism): ratchet-only, and
the trailing-bar window is inert unless an ATR/chandelier position is open."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.backtest import SimBroker
from tradingagents.pro.backtest.broker import PendingOrder


def _bar(price: float, i: int) -> OHLCVBar:
    return OHLCVBar(timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
                    open=price, high=price + 2, low=price - 2, close=price,
                    volume=1_000_000)


def _long_with_trailing(mode: str) -> tuple[SimBroker, object]:
    b = SimBroker(initial_equity=1_000_000.0)
    b.submit(PendingOrder(id="e1", kind="market", side="BUY", quantity=1,
                          stop_loss=90.0, trailing_mode=mode, trailing_mult=2.0,
                          trailing_period=3, symbol="X"))
    b.match_pending(_bar(100.0, 0), 0)
    return b, b.positions["e1"]


@pytest.mark.parametrize("mode", ["atr", "chandelier"])
def test_trailing_ratchets_up_and_never_loosens(mode):
    b, pos = _long_with_trailing(mode)
    assert pos.stop == 90.0  # starts at the protective stop
    stops = []
    price = 100.0
    for i in range(1, 9):
        price += 5.0  # steady uptrend, well clear of the trailing stop
        b.process_bar(_bar(price, i))
        assert "e1" in b.positions, "should not have stopped out in an uptrend"
        stops.append(pos.stop)
    assert pos.stop > 90.0  # ratcheted up off the initial stop
    assert all(stops[j] <= stops[j + 1] for j in range(len(stops) - 1))


def test_trailing_window_is_inert_without_an_atr_position():
    # a plain (non-trailing) position must not populate the trailing window —
    # this is what keeps the default path byte-identical
    b = SimBroker(initial_equity=1_000_000.0)
    b.submit(PendingOrder(id="e1", kind="market", side="BUY", quantity=1,
                          stop_loss=90.0, symbol="X"))
    b.match_pending(_bar(100.0, 0), 0)
    for i in range(1, 5):
        b.process_bar(_bar(100.0 + i, i))
    assert b._trail_bars == {}


def test_pct_trailing_needs_no_window():
    # the pct mode must keep working without touching the ATR window
    b = SimBroker(initial_equity=1_000_000.0)
    b.submit(PendingOrder(id="e1", kind="market", side="BUY", quantity=1,
                          stop_loss=90.0, trailing_mode="pct", trailing_mult=0.05,
                          symbol="X"))
    b.match_pending(_bar(100.0, 0), 0)
    pos = b.positions["e1"]
    for i in range(1, 5):
        b.process_bar(_bar(100.0 + 5 * i, i))
    assert pos.stop > 90.0
    assert b._trail_bars == {}  # pct never feeds the ATR window
