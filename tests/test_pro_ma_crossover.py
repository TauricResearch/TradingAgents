"""ma_crossover_v1 native strategy (SDK strategy library): dual moving-average
crossover entries with a trailing exit. Registered + engine-runnable."""

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
from tradingagents.pro.backtest import (
    BarReplay,
    build_strategy,
    is_registered,
    list_strategies,
)
from tradingagents.pro.backtest.engine import BacktestEngine
from tradingagents.pro.backtest.registry import strategy_param_space

CONFIG = ProConfig(asset=AssetClass.BITCOIN, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1)


def _sine(n=260, base=1000.0, amp=40.0, period=60):
    """Slow oscillation → the fast SMA repeatedly crosses the slow SMA at the
    turns (golden + death crosses), the crossover happy path."""
    bars = []
    for i in range(n):
        close = base + amp * math.sin(2 * math.pi * i / period)
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=close, high=close + 1.0, low=close - 1.0, close=close,
            volume=1_000_000.0))
    return bars


def _strategy(**overrides):
    params = {"fast_period": 10, "slow_period": 30, "stop_atr_mult": 2.0,
              "trail_pct": 0.05, "risk_pct": 1.0, "allow_short": "yes"}
    params.update(overrides)
    return build_strategy("ma_crossover_v1", params)


class TestRegistration:
    def test_registered_and_discoverable(self):
        assert is_registered("ma_crossover_v1")
        assert "ma_crossover_v1" in [s.id for s in list_strategies()]
        names = [p.name for p in strategy_param_space("ma_crossover_v1")]
        assert "fast_period" in names and "slow_period" in names

    def test_defaults_resolve(self):
        resolved = strategy_param_space("ma_crossover_v1").resolve({})
        assert resolved["fast_period"] == 10 and resolved["slow_period"] == 30


class TestEngineRun:
    def _run(self, **overrides):
        replay = BarReplay("BTC-USD", AssetClass.BITCOIN, _sine(), window=60,
                           precompute_indicators=True)
        return BacktestEngine(None, CONFIG, replay, strategy=_strategy(**overrides),
                              min_history=60).run()

    def test_crosses_trigger_trades_both_directions(self):
        res = self._run()
        assert len(res.trades) >= 1
        sides = {t.side for t in res.trades}
        assert "BUY" in sides  # at least the golden-cross longs fired

    def test_long_only_takes_no_shorts(self):
        res = self._run(allow_short="no")
        assert all(t.side == "BUY" for t in res.trades)

    def test_deterministic(self):
        a, b = self._run(), self._run()
        assert [(t.side, t.pnl) for t in a.trades] == [(t.side, t.pnl) for t in b.trades]
