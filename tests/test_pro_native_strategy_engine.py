"""Engine execution of native OrderIntents via the order book (roadmap P1 /
architecture track T2): a strategy that emits OrderIntents from on_bar has
them submitted, matched, filled, and managed — with recommendation-path
timing (decision → next-bar-open → managed)."""

from datetime import timedelta

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import (
    AssetClass,
    OHLCVBar,
    ProConfig,
    Timeframe,
    TradingMode,
)
from tradingagents.pro.backtest import (
    BacktestEngine,
    BarReplay,
    BracketIntent,
    OrderIntent,
    ParamSpace,
    SimBroker,
)

CONFIG = ProConfig(asset=AssetClass.GOLD, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1)


def _bars(n=80):
    bars, price = [], 1000.0
    for i in range(n):
        price += 1.0  # steady uptrend so a breakout stop-entry triggers
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=price, high=price + 2.0, low=price - 2.0, close=price + 1.0,
            volume=1_000_000.0))
    return bars


class _OneShotBreakout:
    """Native strategy: on the first decision bar, submit a single long
    stop-entry breakout with a bracket (stop + TP + trailing), then hold."""

    id = "test_breakout"
    params = ParamSpace()

    def __init__(self):
        self.started = self.stopped = False
        self.fills = []
        self._submitted = False

    def on_start(self, ctx):
        self.started = True

    def on_bar(self, ctx):
        if self._submitted:
            return []
        self._submitted = True
        px = ctx.snapshot.bars[-1].close
        return [OrderIntent(
            kind="stop_entry", side="BUY", risk_pct=1.0,
            stop_price=px + 1.0,  # just above → triggers next bar in an uptrend
            bracket=BracketIntent(
                stop_loss=px - 20.0,
                take_profits=((px + 500.0, 1.0),),  # far → rides the trail
                trailing="pct", trailing_mult=0.02),
            tag="breakout")]

    def on_fill(self, fill):
        self.fills.append(fill)

    def on_stop(self, ctx):
        self.stopped = True


class TestNativeStrategyExecution:
    def _run(self, strategy):
        engine = BacktestEngine(
            None, CONFIG,
            BarReplay("XAUUSD", AssetClass.GOLD, _bars(), window=30,
                      precompute_indicators=True),
            broker=SimBroker(initial_equity=100_000.0),
            memory=None, min_history=30, decide_every=1, strategy=strategy)
        return engine.run()

    def test_lifecycle_hooks_fire(self):
        strat = _OneShotBreakout()
        self._run(strat)
        assert strat.started and strat.stopped

    def test_intent_fills_and_trade_records(self):
        strat = _OneShotBreakout()
        result = self._run(strat)
        # the breakout order filled → exactly one trade, on the BUY side
        assert result.executed == 1
        assert len(result.trades) == 1
        assert result.trades[0].side == "BUY"
        assert strat.fills and strat.fills[0].is_entry

    def test_trailing_bracket_produces_a_win_in_an_uptrend(self):
        # steady uptrend + 2% trailing stop → the trade exits green
        strat = _OneShotBreakout()
        result = self._run(strat)
        trade = result.trades[0]
        assert trade.reason in ("stop", "end_of_data")
        assert trade.pnl > 0

    def test_hold_emits_no_orders(self):
        class _AlwaysHold:
            id = "hold"
            params = ParamSpace()
            def on_start(self, ctx): ...
            def on_bar(self, ctx):
                return []
            def on_fill(self, fill): ...
            def on_stop(self, ctx): ...

        result = self._run(_AlwaysHold())
        assert result.executed == 0 and not result.trades
        assert result.decisions > 0  # decisions still counted per eligible bar
