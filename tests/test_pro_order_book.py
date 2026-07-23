"""Pending-order book on SimBroker (roadmap P1 / architecture track T2):
per-kind conservative intrabar fills, bracket-on-fill, caps, expiry, cancel,
and market-order parity with the recommendation path."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tests.test_pro_memory_facade import make_recommendation
from tradingagents.contracts import OHLCVBar, TakeProfitLevel, Timeframe, TradeAction
from tradingagents.pro.backtest import PendingOrder, SimBroker
from tradingagents.pro.backtest.costs import CommissionModel, LiquidityModel, SlippageModel


def bar(open_, high, low, close, volume=1_000_000.0, day=0) -> OHLCVBar:
    return OHLCVBar(
        timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=day),
        open=open_, high=high, low=low, close=close, volume=volume)


def broker(**kw) -> SimBroker:
    defaults = {
        "slippage": SlippageModel(bps=0),
        "commission": CommissionModel(rate_bps=0),
        "liquidity": LiquidityModel(max_participation=1.0),
        "initial_equity": 1_000_000.0,
    }
    defaults.update(kw)
    return SimBroker(**defaults)


def order(kind, side, **kw) -> PendingOrder:
    base = {
        "id": kw.pop("id", "o1"), "kind": kind, "side": side,
        "quantity": kw.pop("quantity", 10.0),
        "stop_loss": kw.pop("stop_loss", None), "symbol": "BTC-USD",
    }
    base.update(kw)
    return PendingOrder(**base)


# --- market ------------------------------------------------------------------


class TestMarketOrder:
    def test_fills_at_next_bar_open(self):
        b = broker()
        b.submit(order("market", "BUY", stop_loss=95.0,
                       take_profits=[(110.0, 1.0)]))
        filled = b.match_pending(bar(100, 101, 99, 100, day=1), index=1)
        assert filled == ["o1"]
        pos = next(iter(b.positions.values()))
        assert pos.entry_price == 100.0 and pos.stop == 95.0
        assert pos.symbol == "BTC-USD" and pos.recommendation_id == "o1"
        assert not b.pending  # left the book

    def test_parity_with_recommendation_path(self):
        # a market order + bracket must open the SAME position the
        # recommendation path opens from the equivalent ticket
        fill_bar = bar(100, 101, 99, 100, day=1)
        rec = make_recommendation(action=TradeAction.BUY).model_copy(update={
            "entry_price": 100.0, "stop_loss": 95.0,
            "take_profits": [TakeProfitLevel(price=110.0, size_fraction=1.0)],
            "position_size": make_recommendation().position_size.model_copy(
                update={"quantity": 10.0}),
            "risk_reward": None,
        })
        a = broker()
        a.open_from_recommendation(rec, fill_bar)
        b = broker()
        b.submit(order("market", "BUY", stop_loss=95.0,
                       take_profits=[(110.0, 1.0)], quantity=10.0))
        b.match_pending(fill_bar, index=1)
        pa = next(iter(a.positions.values()))
        pb = next(iter(b.positions.values()))
        assert (pa.entry_price, pa.stop, pa.quantity, pa.initial_stop) == \
               (pb.entry_price, pb.stop, pb.quantity, pb.initial_stop)


# --- limit -------------------------------------------------------------------


class TestLimitOrder:
    def test_buy_limit_fills_only_on_touch(self):
        b = broker()
        b.submit(order("limit", "BUY", limit_price=98.0, stop_loss=94.0))
        # bar stays above the limit → no fill
        assert b.match_pending(bar(100, 101, 99, 100, day=1), 1) == []
        assert b.pending["o1"].state == "WORKING"
        # next bar dips to the limit → fills at the limit
        assert b.match_pending(bar(99, 100, 97, 99, day=2), 2) == ["o1"]
        assert next(iter(b.positions.values())).entry_price == 98.0

    def test_buy_limit_gap_through_fills_at_open(self):
        b = broker()
        b.submit(order("limit", "BUY", limit_price=98.0, stop_loss=94.0))
        # opens below the limit (favorable gap) → fill at the open, not the limit
        b.match_pending(bar(96, 97, 95, 96, day=1), 1)
        assert next(iter(b.positions.values())).entry_price == 96.0

    def test_sell_limit_fills_on_high_touch(self):
        b = broker()
        b.submit(order("limit", "SELL", limit_price=102.0, stop_loss=106.0))
        assert b.match_pending(bar(100, 103, 99, 101, day=1), 1) == ["o1"]
        assert next(iter(b.positions.values())).entry_price == 102.0


# --- stop-entry --------------------------------------------------------------


class TestStopEntry:
    def test_buy_stop_triggers_on_high(self):
        b = broker()
        b.submit(order("stop_entry", "BUY", stop_price=105.0, stop_loss=100.0))
        assert b.match_pending(bar(100, 104, 99, 103, day=1), 1) == []  # below stop
        assert b.match_pending(bar(103, 106, 102, 105, day=2), 2) == ["o1"]
        assert next(iter(b.positions.values())).entry_price == 105.0

    def test_buy_stop_gap_through_fills_at_open(self):
        b = broker()
        b.submit(order("stop_entry", "BUY", stop_price=105.0, stop_loss=100.0))
        # opens above the stop (gap up) → pessimistic fill at the open
        b.match_pending(bar(108, 110, 107, 109, day=1), 1)
        assert next(iter(b.positions.values())).entry_price == 108.0


# --- stop-limit --------------------------------------------------------------


class TestStopLimit:
    def test_triggers_then_fills_at_limit_within_range(self):
        b = broker()
        # break above 105, then buy the pullback to 104 (limit within the bar)
        b.submit(order("stop_limit", "BUY", stop_price=105.0, limit_price=104.0,
                       stop_loss=100.0))
        # stop touched (high 105.5) AND limit 104 within [103.5, 105.5] → fill at 104
        assert b.match_pending(bar(105, 105.5, 103.5, 104, day=1), 1) == ["o1"]
        assert next(iter(b.positions.values())).entry_price == 104.0

    def test_triggered_flag_persists_until_limit_met(self):
        b = broker()
        b.submit(order("stop_limit", "BUY", stop_price=105.0, limit_price=103.0,
                       stop_loss=99.0))
        # stop touched but the (lower) limit 103 is not within this bar's range
        assert b.match_pending(bar(104.5, 105.5, 104.2, 105.4, day=1), 1) == []
        assert b.pending["o1"].triggered is True
        # later bar's range includes the limit → now fills as a resting limit
        assert b.match_pending(bar(105, 105, 102.5, 103.5, day=2), 2) == ["o1"]
        assert next(iter(b.positions.values())).entry_price == 103.0


# --- lifecycle: caps, expiry, cancel -----------------------------------------


class TestLifecycle:
    def test_expiry(self):
        b = broker()
        b.submit(order("limit", "BUY", limit_price=90.0, stop_loss=85.0,
                       submitted_index=0, expires_after=2))
        b.match_pending(bar(100, 101, 99, 100, day=1), 1)  # no touch
        assert b.pending["o1"].state == "WORKING"
        b.match_pending(bar(100, 101, 99, 100, day=2), 2)  # index-submitted>=2
        assert "o1" not in b.pending  # expired off the book

    def test_cancel(self):
        b = broker()
        b.submit(order("limit", "BUY", limit_price=90.0, stop_loss=85.0))
        assert b.cancel("o1") is True
        assert not b.pending and b.cancel("o1") is False

    def test_no_stop_is_rejected(self):
        b = broker()
        b.submit(order("market", "BUY"))  # no stop_loss
        assert b.match_pending(bar(100, 101, 99, 100, day=1), 1) == []
        assert not b.positions  # rejected, not opened

    def test_exposure_cap_rejects_oversized_fill(self):
        b = broker(initial_equity=10_000.0, max_gross_exposure_pct=30.0)
        # 100 units × ~100 = 10000 notional ≫ 30% of 10k equity
        b.submit(order("market", "BUY", quantity=100.0, stop_loss=95.0))
        assert b.match_pending(bar(100, 101, 99, 100, day=1), 1) == []
        assert not b.positions

    def test_max_open_positions_cap(self):
        b = broker(max_open_positions=1)
        b.submit(order("market", "BUY", id="a", stop_loss=95.0,
                       take_profits=[(110.0, 1.0)]))
        b.submit(order("market", "BUY", id="b", stop_loss=95.0,
                       take_profits=[(110.0, 1.0)]))
        filled = b.match_pending(bar(100, 101, 99, 100, day=1), 1)
        assert len(filled) == 1 and b.open_count == 1


# --- fill → managed exit round trip ------------------------------------------


class TestFilledPositionManaged:
    def test_filled_order_then_stops_out(self):
        b = broker()
        b.submit(order("market", "BUY", stop_loss=95.0, take_profits=[(110.0, 1.0)]))
        b.match_pending(bar(100, 101, 99, 100, day=1), 1)
        # price collapses through the stop → managed exit closes the position
        trades = b.process_bar(bar(97, 98, 94, 94, day=2))
        assert len(trades) == 1
        assert trades[0].reason == "stop"
        assert trades[0].r_multiple == pytest.approx(-1.0)
