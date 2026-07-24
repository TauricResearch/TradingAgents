"""reduce_only orders (track T2 risk realism): a reduce_only fill only shrinks
opposing same-symbol exposure — it never opens or flips a position, and it is
rejected (terminal) when there is nothing to reduce."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.backtest import SimBroker
from tradingagents.pro.backtest.broker import PendingOrder


def _bar(px: float, i: int = 0) -> OHLCVBar:
    return OHLCVBar(timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
                    open=px, high=px + 1, low=px - 1, close=px, volume=1_000_000)


def _long_broker() -> SimBroker:
    b = SimBroker(initial_equity=100_000.0)
    b.submit(PendingOrder(id="e1", kind="market", side="BUY", quantity=10,
                          stop_loss=90.0, symbol="BTC"))
    b.match_pending(_bar(100.0, 0), 0)
    return b


def test_reduce_only_closes_the_long_without_flipping():
    b = _long_broker()
    assert b.open_count == 1
    b.submit(PendingOrder(id="r1", kind="market", side="SELL", quantity=999,
                          reduce_only=True, symbol="BTC"))
    filled = b.match_pending(_bar(110.0, 1), 1)
    assert "r1" in filled
    assert b.open_count == 0  # the long is fully closed
    # oversize reduce (999 >> 10) never flips into a short
    assert all(p.side != "SELL" for p in b.positions.values())
    assert b.closed[-1].reason == "reduce_only"


def test_reduce_only_partial_shrinks_the_position():
    b = _long_broker()
    b.submit(PendingOrder(id="r1", kind="market", side="SELL", quantity=4,
                          reduce_only=True, symbol="BTC"))
    b.match_pending(_bar(110.0, 1), 1)
    assert b.open_count == 1
    pos = next(iter(b.positions.values()))
    assert pos.quantity == pytest.approx(6.0)


def test_reduce_only_with_no_opposing_position_is_rejected():
    b = SimBroker(initial_equity=100_000.0)
    b.submit(PendingOrder(id="r1", kind="market", side="SELL", quantity=5,
                          reduce_only=True, symbol="BTC"))
    filled = b.match_pending(_bar(100.0, 0), 0)
    assert filled == []           # nothing filled
    assert b.open_count == 0      # and no position opened (never a fresh short)
    assert not b.pending          # terminal, not left resting


def test_reduce_only_does_not_reduce_a_same_side_position():
    # a BUY reduce_only must not touch an existing long (same side)
    b = _long_broker()
    b.submit(PendingOrder(id="r1", kind="market", side="BUY", quantity=5,
                          reduce_only=True, symbol="BTC"))
    filled = b.match_pending(_bar(110.0, 1), 1)
    assert filled == []
    assert b.open_count == 1
    assert next(iter(b.positions.values())).quantity == pytest.approx(10.0)
