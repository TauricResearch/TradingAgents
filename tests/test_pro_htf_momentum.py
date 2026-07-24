"""htf_momentum_v1 (SDK strategy library) — the first consumer of the
multi-timeframe context. Momentum entries gated by the higher-timeframe
trend; the HTF filter must actually block counter-trend entries."""

import math
from datetime import timedelta

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import (
    AssetClass,
    OHLCVBar,
    ProConfig,
    Timeframe,
    TradingMode,
)
from tradingagents.pro.backtest import BarReplay, build_strategy, is_registered
from tradingagents.pro.backtest.engine import BacktestEngine
from tradingagents.pro.backtest.registry import strategy_param_space

CONFIG = ProConfig(asset=AssetClass.BITCOIN, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1)


def _downtrend_with_bounces(n=360):
    """Hourly bars: a steady DOWN drift (→ the aggregated daily trend is down)
    with sharp ~12h up-bounces large relative to price (→ short-term ROC turns
    clearly positive at bounce tops). Unconfirmed momentum buys those bounces;
    the HTF filter should not."""
    bars = []
    for i in range(n):
        close = 200.0 - 0.15 * i + 15.0 * math.sin(2 * math.pi * i / 12)
        bars.append(OHLCVBar(
            timeframe=Timeframe.H1, start=BASE_TS + timedelta(hours=i),
            open=close, high=close + 0.5, low=close - 0.5, close=close,
            volume=1_000_000.0))
    return bars


def _strategy(**overrides):
    params = {"roc_period": 6, "roc_threshold": 1.0, "stop_atr_mult": 2.0,
              "target_atr_mult": 3.0, "risk_pct": 1.0, "allow_short": "yes"}
    params.update(overrides)
    return build_strategy("htf_momentum_v1", params)


def _run(htf):
    replay = BarReplay("BTC-USD", AssetClass.BITCOIN, _downtrend_with_bounces(),
                       window=40, precompute_indicators=True)
    return BacktestEngine(None, CONFIG, replay, strategy=_strategy(),
                          min_history=40, htf_timeframes=htf).run()


class TestRegistration:
    def test_registered_with_declared_htf(self):
        assert is_registered("htf_momentum_v1")
        assert "roc_period" in [p.name for p in strategy_param_space("htf_momentum_v1")]
        strat = build_strategy("htf_momentum_v1", strategy_param_space(
            "htf_momentum_v1").resolve({}))
        assert Timeframe.D1 in strat.htf_timeframes  # declares its HTF need


class TestHtfFilter:
    def test_htf_downtrend_blocks_counter_trend_longs(self):
        confirmed = _run(htf=[Timeframe.D1])   # daily trend down → longs gated
        unconfirmed = _run(htf=None)           # no HTF → buys every bounce
        longs_confirmed = sum(t.side == "BUY" for t in confirmed.trades)
        longs_unconfirmed = sum(t.side == "BUY" for t in unconfirmed.trades)
        # the HTF filter strictly cuts counter-trend longs (a few slip through
        # only during warm-up, before 3 daily bars have closed)
        assert longs_unconfirmed > 0
        assert longs_confirmed < longs_unconfirmed
        # shorts (with the HTF down-trend) are still taken when confirmed
        assert any(t.side == "SELL" for t in confirmed.trades)

    def test_deterministic(self):
        a, b = _run(htf=[Timeframe.D1]), _run(htf=[Timeframe.D1])
        assert [(t.side, t.pnl) for t in a.trades] == [(t.side, t.pnl) for t in b.trades]
