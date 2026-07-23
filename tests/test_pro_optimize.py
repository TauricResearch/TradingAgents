"""Parameter optimizer (roadmap P2 / track T3): grid + random search over a
ParamSpace, best-by-objective selection, and the overfitting guards attached
to every result. Pure driver tested with a synthetic backtest_fn; the engine
adapter tested with a real trend_following_v1 grid."""

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
    BarReplay,
    Param,
    ParamSpace,
    engine_backtest_fn,
    run_optimization,
)

CONFIG = ProConfig(asset=AssetClass.GOLD, mode=TradingMode.BACKTEST,
                   max_debate_rounds=1)


# --- pure driver (synthetic backtest_fn) -------------------------------------


class TestDriver:
    def _space(self):
        return ParamSpace(Param("x", "int", 1, 5, default=3))

    def _fn(self, params):
        # objective peaks at x=3; returns vary a little so guards can compute
        x = params["x"]
        objective = -((x - 3) ** 2)
        returns = [0.001 * x + (0.004 if i % 2 else -0.004) for i in range(60)]
        return objective, returns

    def test_grid_selects_the_best(self):
        result = run_optimization(self._space(), self._fn, search="grid")
        assert result.n_trials == 5
        assert result.best_params == {"x": 3}
        assert result.best_objective == 0
        assert result.search == "grid"

    def test_guards_attached(self):
        result = run_optimization(self._space(), self._fn, search="grid")
        assert result.deflated_sharpe is not None
        assert result.pbo is not None
        assert isinstance(result.verdict(), str)

    def test_random_search_is_seeded_deterministic(self):
        space = ParamSpace(Param("x", "int", 1, 100))
        a = run_optimization(space, self._fn, search="random", n_trials=8, seed=3)
        b = run_optimization(space, self._fn, search="random", n_trials=8, seed=3)
        assert [t.params for t in a.trials] == [t.params for t in b.trials]

    def test_random_requires_n_trials(self):
        with pytest.raises(ValueError, match="n_trials"):
            run_optimization(self._space(), self._fn, search="random")

    def test_single_trial_skips_guards(self):
        space = ParamSpace(Param("only", "categorical", choices=("a",), default="a"))
        result = run_optimization(
            space, lambda p: (1.0, [0.01, -0.01, 0.02]), search="grid")
        assert result.n_trials == 1
        assert result.deflated_sharpe is None and result.pbo is None
        assert "single trial" in result.guard_note

    def test_guards_can_be_disabled(self):
        result = run_optimization(self._space(), self._fn, search="grid",
                                  compute_guards=False)
        assert result.deflated_sharpe is None and "disabled" in result.guard_note


# --- engine adapter (real trend_following_v1 grid) ---------------------------


def _uptrend(n=120):
    bars, price = [], 1000.0
    for i in range(n):
        price += 2.0
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=price, high=price + 0.5, low=price - 0.5, close=price,
            volume=1_000_000.0))
    return bars


class TestEngineAdapter:
    def test_grid_over_trend_following_runs_and_ranks(self):
        bars = _uptrend()
        fn = engine_backtest_fn(
            "trend_following_v1", CONFIG,
            lambda: BarReplay("XAUUSD", AssetClass.GOLD, bars, window=60,
                              precompute_indicators=True),
            min_history=60, objective_name="total_return")
        space = ParamSpace(Param("donchian_period", "int", 15, 25, step=5,
                                 default=20))
        result = run_optimization(space, fn, search="grid",
                                  objective_name="total_return")
        assert result.n_trials == 3  # 15, 20, 25
        assert result.best_params["donchian_period"] in (15, 20, 25)
        # a real objective was produced for the winner
        assert isinstance(result.best_objective, float)
