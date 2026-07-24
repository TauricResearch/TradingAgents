"""Iceberg orders + scale-in averaging (track T2): an iceberg fills at most
display_qty (and the liquidity cap) per bar, building one size-weighted
position, until the full quantity is done."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.backtest import SimBroker
from tradingagents.pro.backtest.broker import PendingOrder
from tradingagents.pro.backtest.costs import CommissionModel, SlippageModel


def _bar(o: float, i: int, vol: float = 1_000_000.0) -> OHLCVBar:
    return OHLCVBar(timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
                    open=o, high=o + 1, low=o - 1, close=o, volume=vol)


def _broker() -> SimBroker:
    # zero costs so slice fills land exactly on the bar open (clean averaging)
    return SimBroker(initial_equity=10_000_000.0,
                     slippage=SlippageModel(bps=0, spread_bps=0, impact_bps=0),
                     commission=CommissionModel(rate_bps=0))


def test_iceberg_fills_in_slices_and_averages_the_entry():
    b = _broker()
    b.submit(PendingOrder(id="ice", kind="market", side="BUY", quantity=10,
                          display_qty=3, stop_loss=50.0, symbol="X"))
    opens = [100.0, 110.0, 120.0, 130.0]  # 3 + 3 + 3 + 1 = 10 over 4 bars
    for i, o in enumerate(opens):
        filled = b.match_pending(_bar(o, i), i)
        assert filled == (["ice"] if i == 0 else [])  # on_fill fires once

    assert "ice" not in b.pending  # fully filled, order retired
    pos = b.positions["ice"]
    assert pos.quantity == pytest.approx(10.0)
    assert pos.original_quantity == pytest.approx(10.0)  # R unit grew with size
    # size-weighted entry: (3·100 + 3·110 + 3·120 + 1·130) / 10 = 112
    assert pos.entry_price == pytest.approx(112.0)


def test_iceberg_slice_capped_by_liquidity():
    b = _broker()
    b.submit(PendingOrder(id="ice", kind="market", side="BUY", quantity=10,
                          display_qty=5, stop_loss=50.0, symbol="X"))
    # tiny bar volume → the 10%-participation cap trims the slice below display
    b.match_pending(_bar(100.0, 0, vol=20.0), 0)
    assert b.positions["ice"].quantity == pytest.approx(2.0)  # 0.1 × 20
    assert "ice" in b.pending  # not done — keeps resting


def test_non_iceberg_order_still_single_fills():
    b = _broker()
    b.submit(PendingOrder(id="e1", kind="market", side="BUY", quantity=4,
                          stop_loss=50.0, symbol="X"))
    filled = b.match_pending(_bar(100.0, 0), 0)
    assert filled == ["e1"]
    assert "e1" not in b.pending
    assert b.positions["e1"].quantity == pytest.approx(4.0)
