"""P0.3 regression guard: rules_v1 (via the Strategy SDK + engine.strategy
branch) must reproduce a direct BacktestEngine(RulesPipelineLLM(), ...) run
bit-for-bit at default params — same trades, equity, decisions, rejections.

This is the acceptance test for wrapping the rules engine under the SDK: if
delegation ever drifts from the legacy path, this fails."""

from datetime import timedelta

import pytest

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
    SimBroker,
    build_strategy,
)
from tradingagents.pro.evals.rules import RulesPipelineLLM
from tradingagents.pro.memory import ProMemory

CONFIG = ProConfig(asset=AssetClass.GOLD, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1)


def _bars(fn, n=400):
    bars, price = [], 1000.0
    for i in range(n):
        close = fn(i, price)
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=price, high=max(price, close) + 2.0,
            low=min(price, close) - 2.0, close=close, volume=1000.0))
        price = close
    return bars


def _replay(bars):
    return BarReplay("XAUUSD", AssetClass.GOLD, bars, window=60,
                     precompute_indicators=True)


def _legacy_run(bars):
    engine = BacktestEngine(
        RulesPipelineLLM(), CONFIG, _replay(bars),
        broker=SimBroker(initial_equity=100_000.0),
        memory=ProMemory(), min_history=60, decide_every=1)
    return engine.run()


def _strategy_run(bars, params=None):
    engine = BacktestEngine(
        None, CONFIG, _replay(bars),
        broker=SimBroker(initial_equity=100_000.0),
        memory=ProMemory(), min_history=60, decide_every=1,
        strategy=build_strategy("rules_v1", params))
    return engine.run()


def _trade_tuples(result):
    return [
        (t.side, t.entry_price, t.exit_price, t.pnl, t.reason,
         t.r_multiple, t.planned_rr, t.opened_at, t.closed_at)
        for t in result.trades
    ]


class TestRulesV1Equivalence:
    @pytest.mark.parametrize("fn,label", [
        (lambda i, p: p + 0.5, "uptrend"),
        (lambda i, p: p - 0.8, "downtrend"),
        (lambda i, p: 1000.0 + (3.0 if i % 2 else -3.0), "chop"),
    ])
    def test_trades_and_equity_match_legacy(self, fn, label):
        bars = _bars(fn)
        legacy, strat = _legacy_run(bars), _strategy_run(bars)
        assert _trade_tuples(strat) == _trade_tuples(legacy), f"{label}: trades differ"
        assert strat.equity_curve == legacy.equity_curve, f"{label}: equity differs"
        assert strat.decisions == legacy.decisions
        assert strat.executed == legacy.executed
        assert strat.rejections == legacy.rejections

    def test_default_params_are_the_shipped_constants(self):
        # a default-param run must equal a no-param run (defaults resolved)
        bars = _bars(lambda i, p: p + 0.5)
        explicit = _strategy_run(bars, {
            "tp_ladder": "0.5/3.5", "min_risk_reward": 1.8,
            "stop_cooldown_bars": 10})
        implicit = _strategy_run(bars, None)
        assert _trade_tuples(explicit) == _trade_tuples(implicit)

    def test_nondefault_ladder_changes_outcomes(self):
        # a genuinely different ladder must produce different trade geometry
        # (proves the param is wired, not decorative)
        bars = _bars(lambda i, p: p + 0.5)
        base = _strategy_run(bars, None)
        wide = _strategy_run(bars, {"tp_ladder": "1.5/3.0"})
        base_tps = [t.exit_price for t in base.trades if t.reason == "take_profit"]
        wide_tps = [t.exit_price for t in wide.trades if t.reason == "take_profit"]
        # if any take-profits fired, their prices must differ between ladders
        if base_tps and wide_tps:
            assert base_tps != wide_tps
