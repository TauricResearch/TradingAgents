"""mean_reversion_v1 native strategy (post-roadmap: building real strategies
on the SDK). Registered + optimizable + engine-runnable, like
trend_following_v1 — it fades stretches from the SMA and targets the mean."""

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


def _series(n=240, base=100.0):
    """Flat around a stable mean (tiny noise → small σ) with periodic 3-bar
    excursions that PERSIST into the next bar (so the market entry fills while
    still stretched) and then revert to the mean — dips (→ long) and spikes
    (→ short) alternate each 24-bar cycle."""
    bars = []
    for i in range(n):
        phase = i % 24
        if phase in (10, 11, 12):
            close = base - 5.0        # stretched below → fade long
        elif phase in (20, 21, 22):
            close = base + 5.0        # stretched above → fade short
        else:
            close = base + (0.3 if i % 2 else -0.3)  # flat, small σ
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=close, high=close + 0.4, low=close - 0.4, close=close,
            volume=1_000_000.0))
    return bars


def _strategy(**overrides):
    params = {"lookback": 20, "entry_std": 1.5, "stop_atr_mult": 3.0,
              "risk_pct": 1.0, "allow_short": "yes"}
    params.update(overrides)
    return build_strategy("mean_reversion_v1", params)


class TestRegistration:
    def test_registered_and_discoverable(self):
        assert is_registered("mean_reversion_v1")
        assert "mean_reversion_v1" in [s.id for s in list_strategies()]
        names = [p.name for p in strategy_param_space("mean_reversion_v1")]
        assert "entry_std" in names and "lookback" in names

    def test_param_space_resolves_defaults(self):
        resolved = strategy_param_space("mean_reversion_v1").resolve({})
        assert resolved["lookback"] == 20 and resolved["entry_std"] == 2.0


class TestEngineRun:
    def _run(self, **overrides):
        replay = BarReplay("BTC-USD", AssetClass.BITCOIN, _series(), window=40,
                           precompute_indicators=True)
        return BacktestEngine(None, CONFIG, replay, strategy=_strategy(**overrides),
                              min_history=40).run()

    def test_fades_extremes_and_trades(self):
        res = self._run()
        assert len(res.trades) >= 1
        # it took at least one long (faded a trough back toward the mean)
        assert any(t.side == "BUY" for t in res.trades)

    def test_long_only_takes_no_shorts(self):
        res = self._run(allow_short="no")
        assert all(t.side == "BUY" for t in res.trades)

    def test_deterministic(self):
        a, b = self._run(), self._run()
        assert [(t.side, t.pnl) for t in a.trades] == [(t.side, t.pnl) for t in b.trades]
