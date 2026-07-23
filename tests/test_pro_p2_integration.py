"""P2 end-to-end integration (track T3): the optimizer AND walk-forward
fitting composed over the REAL trend_following_v1 strategy through the engine
adapter — proving validation + optimize + walkforward + engine + strategy all
fit together on a live strategy, not just synthetic backtest_fns."""

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
    Param,
    ParamSpace,
    engine_backtest_fn,
    run_optimization,
    run_walk_forward_optimization,
)

CONFIG = ProConfig(asset=AssetClass.GOLD, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1)

# a narrowed search space (the full TREND_V1_PARAMS donchian range would be a
# 90-point grid); build_strategy fills the untouched params from defaults
SEARCH = ParamSpace(
    Param("donchian_period", "int", 15, 25, step=5, default=20),
    Param("trail_pct", "float", 0.03, 0.05, step=0.02, default=0.05),
)


def _bars(n, drift):
    bars, price = [], 1000.0
    for i in range(n):
        price += drift
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=price, high=price + 0.5, low=price - 0.5, close=price,
            volume=1_000_000.0))
    return bars


def _factory(min_history):
    def make(bar_slice):
        return engine_backtest_fn(
            "trend_following_v1", CONFIG,
            lambda: BarReplay("XAUUSD", AssetClass.GOLD, bar_slice,
                              window=min_history, precompute_indicators=True),
            min_history=min_history, objective_name="total_return")
    return make


class TestOptimizeRealStrategy:
    def test_grid_over_trend_following_attaches_guards(self):
        bars = _bars(160, drift=2.0)  # steady uptrend → breakouts + trades
        fn = _factory(40)(bars)
        result = run_optimization(SEARCH, fn, search="grid",
                                  objective_name="total_return")
        assert result.n_trials == 3 * 2  # 3 donchian × 2 trail
        assert result.best_params["donchian_period"] in (15, 20, 25)
        # guards computed over the real trials + a verdict rendered
        assert result.deflated_sharpe is not None
        assert result.pbo is not None
        assert isinstance(result.verdict(), str) and result.verdict()


class TestWalkForwardRealStrategy:
    def test_walk_forward_optimizes_trend_following_out_of_sample(self):
        bars = _bars(360, drift=2.0)
        result = run_walk_forward_optimization(
            SEARCH, bars, _factory(30),
            train=80, test=40, step=40, embargo=5,
            search="grid", objective_name="total_return")
        assert len(result.windows) >= 2
        # every window chose params from the declared search space
        for params in result.chosen_params:
            assert params["donchian_period"] in (15, 20, 25)
            assert params["trail_pct"] in (0.03, 0.05)
        s = result.summary()
        assert s["windows"] == len(result.windows)
        assert "oos_sharpe" in s and "distinct_param_sets" in s
        # the fitted strategy actually traded out-of-sample in an uptrend
        assert any(o != 0.0 for o in result.oos_objective)
