"""momentum_v1 native strategy (SDK strategy library): rate-of-change momentum
with fixed-R ATR stop/target. Registered + engine-runnable like the others."""

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


def _uptrend(n=140, p0=1000.0, drift=3.0):
    bars, price = [], p0
    for i in range(n):
        price += drift
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=price, high=price + 0.5, low=price - 0.5, close=price,
            volume=1_000_000.0))
    return bars


def _strategy(**overrides):
    params = {"roc_period": 14, "roc_threshold": 1.0, "stop_atr_mult": 2.0,
              "target_atr_mult": 3.0, "risk_pct": 1.0, "allow_short": "yes"}
    params.update(overrides)
    return build_strategy("momentum_v1", params)


class TestRegistration:
    def test_registered_and_discoverable(self):
        assert is_registered("momentum_v1")
        assert "momentum_v1" in [s.id for s in list_strategies()]
        names = [p.name for p in strategy_param_space("momentum_v1")]
        assert "roc_period" in names and "roc_threshold" in names

    def test_defaults_resolve(self):
        resolved = strategy_param_space("momentum_v1").resolve({})
        assert resolved["roc_period"] == 14 and resolved["roc_threshold"] == 5.0


class TestEngineRun:
    def _run(self, bars, **overrides):
        replay = BarReplay("BTC-USD", AssetClass.BITCOIN, bars, window=40,
                           precompute_indicators=True)
        return BacktestEngine(None, CONFIG, replay, strategy=_strategy(**overrides),
                              min_history=40).run()

    def test_enters_long_on_strong_up_momentum(self):
        res = self._run(_uptrend())
        assert len(res.trades) >= 1
        assert any(t.side == "BUY" for t in res.trades)

    def test_high_threshold_suppresses_weak_momentum(self):
        # a gentle drift can't clear a 15% ROC bar → no entries
        gentle = _uptrend(drift=0.2)
        res = self._run(gentle, roc_threshold=15.0)
        assert res.trades == []

    def test_deterministic(self):
        a, b = self._run(_uptrend()), self._run(_uptrend())
        assert [(t.side, t.pnl) for t in a.trades] == [(t.side, t.pnl) for t in b.trades]
