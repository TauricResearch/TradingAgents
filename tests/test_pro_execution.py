"""TWAP/VWAP execution algos (track T2): schedule builders + the broker
working a scheduled order over multiple bars into one averaged position."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.backtest import SimBroker
from tradingagents.pro.backtest.broker import PendingOrder
from tradingagents.pro.backtest.costs import CommissionModel, SlippageModel
from tradingagents.pro.backtest.execution import (
    build_schedule,
    schedule_for,
    twap_schedule,
    vwap_schedule,
)


def _bar(o: float, i: int) -> OHLCVBar:
    return OHLCVBar(timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
                    open=o, high=o + 1, low=o - 1, close=o, volume=1_000_000.0)


def _broker() -> SimBroker:
    return SimBroker(initial_equity=10_000_000.0,
                     slippage=SlippageModel(bps=0, spread_bps=0, impact_bps=0),
                     commission=CommissionModel(rate_bps=0))


# --- schedule builders (pure) ------------------------------------------------


def test_twap_is_equal_slices():
    assert twap_schedule(12, 4) == [3, 3, 3, 3]
    assert sum(twap_schedule(10, 3)) == pytest.approx(10)


def test_vwap_weights_by_volume_profile():
    # profile (1,2,1) sums to 4 → 12 splits 3/6/3
    assert vwap_schedule(12, [1, 2, 1]) == pytest.approx([3, 6, 3])
    # a flat/zero profile degrades to TWAP
    assert vwap_schedule(9, [0, 0, 0]) == pytest.approx([3, 3, 3])


def test_build_and_schedule_for():
    assert build_schedule("twap", 6, 3) == [2, 2, 2]
    assert schedule_for(None, 3, None, 10) is None
    assert schedule_for("vwap", 3, (1, 2, 1), 12) == (3, 6, 3)
    with pytest.raises(ValueError, match="unknown execution algo"):
        build_schedule("iceberg", 6, 3)


# --- broker works the schedule over bars -------------------------------------


def test_scheduled_order_builds_one_averaged_position():
    b = _broker()
    b.submit(PendingOrder(id="algo", kind="market", side="BUY", quantity=10,
                          schedule=(3.0, 3.0, 4.0), stop_loss=50.0, symbol="X"))
    fills = []
    for i, price in enumerate([100.0, 110.0, 120.0]):
        fills.append(b.match_pending(_bar(price, i), i))
    assert fills[0] == ["algo"] and fills[1] == [] and fills[2] == []
    assert "algo" not in b.pending  # schedule consumed → retired
    pos = b.positions["algo"]
    assert pos.quantity == pytest.approx(10.0)
    # size-weighted entry: (3·100 + 3·110 + 4·120) / 10 = 111
    assert pos.entry_price == pytest.approx(111.0)


def test_scheduled_order_retires_when_plan_ends_even_if_underfilled():
    # quantity 10 but only a 2-slot schedule of 3 each → 6 filled, then retired
    b = _broker()
    b.submit(PendingOrder(id="algo", kind="market", side="BUY", quantity=10,
                          schedule=(3.0, 3.0), stop_loss=50.0, symbol="X"))
    b.match_pending(_bar(100.0, 0), 0)
    b.match_pending(_bar(100.0, 1), 1)
    # third bar: schedule already spent → order retires, no further fill
    b.match_pending(_bar(100.0, 2), 2)
    assert "algo" not in b.pending
    assert b.positions["algo"].quantity == pytest.approx(6.0)
