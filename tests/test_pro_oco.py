"""OCO order groups (track T2): filling one leg cancels its siblings, and a
same-bar dual trigger resolves to the adverse (stop) leg (pessimistic)."""

from datetime import timedelta

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.backtest import SimBroker
from tradingagents.pro.backtest.broker import PendingOrder


def _bar(o: float, h: float, low: float, c: float, i: int = 0) -> OHLCVBar:
    return OHLCVBar(timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
                    open=o, high=h, low=low, close=c, volume=1_000_000)


def _broker() -> SimBroker:
    return SimBroker(initial_equity=1_000_000.0)


def test_filled_leg_cancels_its_sibling():
    b = _broker()
    b.submit(PendingOrder(id="buy", kind="stop_entry", side="BUY", quantity=1,
                          stop_price=110.0, stop_loss=105.0, oco_group="g1",
                          symbol="X"))
    b.submit(PendingOrder(id="sell", kind="limit", side="SELL", quantity=1,
                          limit_price=120.0, stop_loss=125.0, oco_group="g1",
                          symbol="X"))
    # only the buy stop triggers (high 112 ≥ 110; the sell limit needs ≥ 120)
    filled = b.match_pending(_bar(100.0, 112.0, 99.0, 105.0), 0)
    assert filled == ["buy"]
    assert b.open_count == 1
    assert next(iter(b.positions.values())).side == "BUY"
    assert "sell" not in b.pending  # sibling cancelled
    assert b._orders["sell"]["state"] == "cancelled:oco"


def test_same_bar_dual_trigger_resolves_to_the_stop_leg():
    b = _broker()
    # both would trigger this bar; the adverse stop leg must win over the limit
    b.submit(PendingOrder(id="buy_stop", kind="stop_entry", side="BUY",
                          quantity=1, stop_price=110.0, stop_loss=105.0,
                          oco_group="g1", symbol="X"))
    b.submit(PendingOrder(id="sell_limit", kind="limit", side="SELL",
                          quantity=1, limit_price=108.0, stop_loss=113.0,
                          oco_group="g1", symbol="X"))
    filled = b.match_pending(_bar(100.0, 112.0, 99.0, 105.0), 0)
    assert filled == ["buy_stop"]  # stop (rank 0) beats limit (rank 2)
    assert b.open_count == 1
    assert next(iter(b.positions.values())).side == "BUY"
    assert b._orders["sell_limit"]["state"] == "cancelled:oco"


def test_neither_leg_triggers_both_rest():
    b = _broker()
    b.submit(PendingOrder(id="buy", kind="stop_entry", side="BUY", quantity=1,
                          stop_price=110.0, stop_loss=105.0, oco_group="g1",
                          symbol="X"))
    b.submit(PendingOrder(id="sell", kind="limit", side="SELL", quantity=1,
                          limit_price=120.0, stop_loss=125.0, oco_group="g1",
                          symbol="X"))
    filled = b.match_pending(_bar(100.0, 105.0, 98.0, 102.0), 0)
    assert filled == []
    assert b.open_count == 0
    assert set(b.pending) == {"buy", "sell"}  # both still working
