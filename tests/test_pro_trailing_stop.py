"""Percentage trailing stop on SimBroker (roadmap P1 / architecture track T2):
ratchet-only toward the favorable extreme, conservative next-bar application,
composes with breakeven, initial_stop (the R unit) never mutates."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.backtest import PendingOrder, SimBroker
from tradingagents.pro.backtest.costs import CommissionModel, LiquidityModel, SlippageModel


def bar(open_, high, low, close, day=0) -> OHLCVBar:
    return OHLCVBar(timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=day),
                    open=open_, high=high, low=low, close=close, volume=1_000_000.0)


def broker() -> SimBroker:
    return SimBroker(initial_equity=1_000_000.0, slippage=SlippageModel(bps=0),
                     commission=CommissionModel(rate_bps=0),
                     liquidity=LiquidityModel(max_participation=1.0),
                     breakeven_after_tp1=False)


def _open_long_with_trail(b, trail_pct, entry_bar):
    b.submit(PendingOrder(
        id="o1", kind="market", side="BUY", quantity=10.0,
        stop_loss=90.0, take_profits=[(200.0, 1.0)],  # far TP so it won't fire
        trailing_mode="pct", trailing_mult=trail_pct, symbol="BTC-USD"))
    b.match_pending(entry_bar, index=1)
    return next(iter(b.positions.values()))


class TestTrailingStop:
    def test_ratchets_up_on_favorable_move_and_holds(self):
        b = broker()
        pos = _open_long_with_trail(b, 0.10, bar(100, 100, 99, 100, day=1))
        assert pos.stop == 90.0  # initial
        # bar rises to 120 → trail = 120*0.9 = 108 (applies from next bar)
        b.process_bar(bar(100, 120, 100, 118, day=2))
        assert pos.stop == pytest.approx(108.0)
        # bar pulls back (high 115) → extreme stays 120, stop does NOT lower
        b.process_bar(bar(115, 115, 110, 112, day=3))
        assert pos.stop == pytest.approx(108.0)
        assert pos.initial_stop == 90.0  # R unit never moved

    def test_trailed_stop_closes_the_trade(self):
        b = broker()
        _open_long_with_trail(b, 0.10, bar(100, 100, 99, 100, day=1))
        b.process_bar(bar(100, 120, 100, 118, day=2))  # stop → 108
        trades = b.process_bar(bar(112, 113, 105, 106, day=3))  # low 105 < 108
        assert len(trades) == 1
        assert trades[0].reason == "stop"
        # exited at the trailed stop (108), well above entry → a WIN
        assert trades[0].exit_price == pytest.approx(108.0)
        assert trades[0].pnl > 0

    def test_current_bar_high_does_not_stop_out_the_same_bar(self):
        # the bar that raises the trail must not also be used to claim its own
        # low hit the freshly-raised stop (no intrabar look-ahead)
        b = broker()
        _open_long_with_trail(b, 0.10, bar(100, 100, 99, 100, day=1))
        trades = b.process_bar(bar(110, 120, 107, 118, day=2))
        # trail computes to 108, but this bar's low (107) must NOT trigger it
        assert trades == []
        assert next(iter(b.positions.values())).stop == pytest.approx(108.0)

    def test_short_trails_downward(self):
        b = broker()
        b.submit(PendingOrder(
            id="s1", kind="market", side="SELL", quantity=10.0,
            stop_loss=110.0, take_profits=[(10.0, 1.0)],
            trailing_mode="pct", trailing_mult=0.10, symbol="BTC-USD"))
        b.match_pending(bar(100, 101, 99, 100, day=1), index=1)
        pos = next(iter(b.positions.values()))
        b.process_bar(bar(100, 100, 80, 82, day=2))  # low 80 → trail = 80*1.1 = 88
        assert pos.stop == pytest.approx(88.0)
        b.process_bar(bar(85, 90, 84, 86, day=3))  # extreme stays 80, no loosen
        assert pos.stop == pytest.approx(88.0)

    def test_no_trailing_leaves_stop_fixed(self):
        b = broker()
        b.submit(PendingOrder(id="o1", kind="market", side="BUY", quantity=10.0,
                              stop_loss=90.0, take_profits=[(200.0, 1.0)],
                              symbol="BTC-USD"))
        b.match_pending(bar(100, 100, 99, 100, day=1), index=1)
        pos = next(iter(b.positions.values()))
        b.process_bar(bar(100, 150, 100, 148, day=2))
        assert pos.stop == 90.0  # unchanged without a trailing spec
