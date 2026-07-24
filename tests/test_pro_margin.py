"""Leverage / margin / forced liquidation (track T5): leverage lifts the gross
cap, a maintenance breach at the adverse extreme force-liquidates, a reachable
protective stop pre-empts it, and the neutral model is a no-op."""

from datetime import timedelta

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.backtest import MarginModel, SimBroker
from tradingagents.pro.backtest.broker import PendingOrder
from tradingagents.pro.backtest.costs import CommissionModel, SlippageModel


def _bar(o: float, h: float, low: float, c: float, i: int = 0) -> OHLCVBar:
    return OHLCVBar(timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
                    open=o, high=h, low=low, close=c, volume=1_000_000.0)


def _broker(**kw) -> SimBroker:
    return SimBroker(initial_equity=100_000.0,
                     slippage=SlippageModel(bps=0, spread_bps=0, impact_bps=0),
                     commission=CommissionModel(rate_bps=0), **kw)


def test_leverage_lifts_the_gross_cap():
    # base cap 30% of 100k = 30k; a 50k-notional order is refused unleveraged
    base = _broker()
    base.submit(PendingOrder(id="e", kind="market", side="BUY", quantity=500,
                             stop_loss=90.0, symbol="X"))
    base.match_pending(_bar(100.0, 101.0, 99.0, 100.0), 0)
    assert base.open_count == 0  # 50k > 30k cap → refused

    lev = _broker(margin=MarginModel(leverage=2.0))
    lev.submit(PendingOrder(id="e", kind="market", side="BUY", quantity=500,
                            stop_loss=90.0, symbol="X"))
    lev.match_pending(_bar(100.0, 101.0, 99.0, 100.0), 0)
    assert lev.open_count == 1  # cap lifted to 60k → admitted


def test_liquidation_fires_when_maintenance_breached():
    b = SimBroker(initial_equity=10_000.0, max_gross_exposure_pct=100.0,
                  slippage=SlippageModel(bps=0, spread_bps=0, impact_bps=0),
                  commission=CommissionModel(rate_bps=0),
                  margin=MarginModel(leverage=5.0, maintenance_margin_pct=10.0))
    # 400 @ 100 = 40k notional on 10k equity (4×) — allowed under 5× cap
    b.submit(PendingOrder(id="e", kind="market", side="BUY", quantity=400,
                          stop_loss=1.0, symbol="X"))  # stop far away
    b.match_pending(_bar(100.0, 101.0, 99.0, 100.0), 0)
    assert b.open_count == 1
    # crash: adverse low 80 → marked equity 10k−8k=2k < maintenance 0.10·80·400=3200
    closed = b.check_liquidation(_bar(85.0, 86.0, 80.0, 82.0, 1))
    assert len(closed) == 1 and closed[0].reason == "liquidation"
    assert b.open_count == 0


def test_protective_stop_preempts_liquidation():
    b = SimBroker(initial_equity=10_000.0, max_gross_exposure_pct=100.0,
                  slippage=SlippageModel(bps=0, spread_bps=0, impact_bps=0),
                  commission=CommissionModel(rate_bps=0),
                  margin=MarginModel(leverage=5.0, maintenance_margin_pct=10.0))
    b.submit(PendingOrder(id="e", kind="market", side="BUY", quantity=400,
                          stop_loss=95.0, symbol="X"))  # reachable stop
    b.match_pending(_bar(100.0, 101.0, 99.0, 100.0), 0)
    crash = _bar(98.0, 99.0, 80.0, 82.0, 1)
    managed = b.process_bar(crash)
    assert managed and managed[0].reason == "stop"  # stop fires first
    assert b.check_liquidation(crash) == []  # nothing left to liquidate


def test_neutral_margin_is_a_noop():
    def run(margin):
        b = SimBroker(initial_equity=100_000.0,
                      slippage=SlippageModel(bps=0, spread_bps=0, impact_bps=0),
                      commission=CommissionModel(rate_bps=0), margin=margin)
        b.submit(PendingOrder(id="e", kind="market", side="BUY", quantity=100,
                              stop_loss=90.0, symbol="X"))
        b.match_pending(_bar(100.0, 101.0, 99.0, 100.0), 0)
        b.process_bar(_bar(105.0, 106.0, 104.0, 105.0, 1))
        b.check_liquidation(_bar(105.0, 106.0, 104.0, 105.0, 1))
        return (b.cash_pnl, b.open_count,
                [(t.reason, t.pnl) for t in b.closed])

    assert run(None) == run(MarginModel(leverage=1.0, maintenance_margin_pct=0.0))
