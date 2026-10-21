"""Deterministic tests: no AI provider, network, or real brokerage used."""

from datetime import date, timedelta

import pytest

from tradingagents.paper.engine import Bar, Book
from tradingagents.paper.cli import forward_sync, forex_for_day


DAY0 = "2026-10-19"
DAY1 = "2026-10-20"
DAY2 = "2026-10-21"


def candle(open_, low=None, close=None, high=None):
    return Bar(open_, high if high is not None else open_ + 5,
               low if low is not None else open_ - 5,
               close if close is not None else open_)


def marked(book=None, day=DAY0, spy=600):
    return (book or Book.new(day)).step(day, {}, .75, .75, spy)


def test_initial_balance_and_signal_only_queues():
    b = marked()
    assert b.equity() == pytest.approx(10000)
    assert b.submit_signal("AAPL", "Buy", 100, DAY0)
    assert len(b.orders) == 1 and not b.positions
    assert b.equity() == pytest.approx(10000)


def test_next_open_fill_and_position_risk_limits():
    b = marked()
    b.submit_signal("AAPL", "Buy", 100, DAY0)
    next_b = b.step(DAY1, {"AAPL": candle(101, low=100, close=103)}, .75, .75, 601)
    assert not b.positions  # steps are immutable unless caller persists result
    p = next_b.positions["AAPL"]
    assert p["planned_risk_gbp"] <= 200.001
    assert p["cost_gbp"] <= 3000.01
    assert len(next_b.orders) == 0
    assert next_b.equity() > 0


def test_gap_through_stop_sells_at_worse_open():
    b = marked()
    b.submit_signal("AAPL", "Buy", 100, DAY0)
    b = b.step(DAY1, {"AAPL": candle(100, low=96, close=100)}, .75, .75, 601)
    assert "AAPL" in b.positions
    b = b.step(DAY2, {"AAPL": candle(80, low=75, close=79, high=82)}, .75, .75, 600)
    assert "AAPL" not in b.positions
    closed = b.completed[0]
    assert closed["reason"] == "STOP"
    assert closed["exit_usd"] < 80  # exit slippage on the gap, never assume stop fill
    assert closed["pnl_gbp"] < -200  # 2% planned risk is NOT a gap loss guarantee


def test_no_same_day_execution_even_for_queued_order():
    b = marked()
    b.submit_signal("AAPL", "Buy", 100, DAY0)
    with pytest.raises(ValueError):
        b.step(DAY0, {"AAPL": candle(100)}, .75, .75, 600)
    assert not b.positions


def test_missing_bar_fails_closed_without_mutation():
    b = marked()
    b.submit_signal("AAPL", "Buy", 100, DAY0)
    with pytest.raises(ValueError, match="Missing"):
        b.step(DAY1, {}, .75, .75, 600)
    assert b.orders and not b.positions and b.last_session == DAY0


def test_duplicate_and_hold_do_not_queue():
    b = marked()
    assert not b.submit_signal("AAPL", "Hold", 100, DAY0)
    assert b.submit_signal("AAPL", "Buy", 100, DAY0)
    assert not b.submit_signal("AAPL", "Buy", 100, DAY0)
    assert len(b.orders) == 1


def test_cash_and_name_allocation_caps_with_multiple_buys():
    b = marked()
    for t in ("AAPL", "MSFT", "NVDA", "META", "AMZN", "GOOGL"):
        b.submit_signal(t, "Buy", 100, DAY0)
    bars = {t: candle(100, low=99, close=100) for t in
            ("AAPL", "MSFT", "NVDA", "META", "AMZN", "GOOGL")}
    b = b.step(DAY1, bars, .75, .75, 600)
    assert len(b.positions) <= 5
    assert b.cash_gbp >= -0.00001
    assert sum(p["planned_risk_gbp"] for p in b.positions.values()) <= 600.01
    assert sum(p["cost_gbp"] for p in b.positions.values()) <= 10000.01


def test_drawdown_halt_is_sticky_and_blocks_new_buys():
    b = marked()
    b.submit_signal("AAPL", "Buy", 100, DAY0)
    b = b.step(DAY1, {"AAPL": candle(100, low=99, close=120, high=121)}, .75, .75, 601)
    # Directly simulate an *actual portfolio* >10% decline from peak using a
    # strong adverse FX move. The USD stop is not an FX hedge.
    b = b.step(DAY2, {"AAPL": candle(118, low=117, close=118, high=119)}, .30, .30, 600)
    assert b.halted
    assert not b.submit_signal("MSFT", "Buy", 100, DAY2)


def test_close_signal_uses_next_open():
    b = marked()
    b.submit_signal("AAPL", "Buy", 100, DAY0)
    b = b.step(DAY1, {"AAPL": candle(100, low=99, close=105, high=106)}, .75, .75, 600)
    assert b.submit_signal("AAPL", "Sell", 105, DAY1)
    assert "AAPL" in b.positions
    b = b.step(DAY2, {"AAPL": candle(103, low=100, close=101)}, .75, .75, 600)
    assert "AAPL" not in b.positions and b.completed[-1]["reason"] == "SIGNAL"


def test_forward_sync_processes_all_sessions_including_stop_day():
    b = marked()
    b.submit_signal("AAPL", "Buy", 100, DAY0)
    quotes = {
        "SPY": {DAY1: candle(600, low=590), DAY2: candle(610, low=600)},
        "GBPUSD=X": {DAY1: candle(1.33, low=1.3, high=1.35), DAY2: candle(1.33, low=1.3, high=1.35)},
        "AAPL": {DAY1: candle(100, low=99), DAY2: candle(90, low=85, close=90)},
    }
    b = forward_sync(b, quotes, DAY2)
    assert b.completed and b.completed[-1]["reason"] == "STOP"
    assert b.last_session == DAY2


def test_bad_fx_is_rejected():
    with pytest.raises(ValueError, match="recent GBPUSD"):
        forex_for_day({"2026-10-01": candle(1.3)}, DAY1)


def test_rule_tampering_is_rejected():
    b = marked()
    raw = vars(b).copy()
    raw["rules"] = {**raw["rules"], "risk_fraction": 1.0}
    with pytest.raises(ValueError, match="Unrecognized"):
        Book.load(raw)
