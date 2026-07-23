"""Walk-forward fitting (roadmap P2.2 / track T3): windows with an embargo
gap, fit-on-train / score-OOS-on-test, and an out-of-sample-concatenated
summary with parameter-stability reporting. Driver tested with a synthetic
backtest_fn_factory (no engine needed → fast, deterministic)."""

import pytest

from tradingagents.pro.backtest import (
    Param,
    ParamSpace,
    run_walk_forward_optimization,
    walk_forward_opt_windows,
)


class TestWindows:
    def test_embargo_gap_and_no_overlap(self):
        w = walk_forward_opt_windows(n_bars=100, train=40, test=20, step=20, embargo=5)
        assert w  # at least one
        for win in w:
            assert win.test_start == win.train_end + 5  # embargo gap
            assert win.train_start < win.train_end <= win.test_start < win.test_end
        # rolling by step, non-overlapping test ranges at step==test
        assert w[1].train_start - w[0].train_start == 20

    def test_stops_before_running_off_the_end(self):
        w = walk_forward_opt_windows(n_bars=70, train=40, test=20, embargo=5)
        # 40 + 5 + 20 = 65 <= 70 → one window; next would need 85
        assert len(w) == 1

    def test_rejects_bad_sizes(self):
        with pytest.raises(ValueError):
            walk_forward_opt_windows(100, train=0, test=10)
        with pytest.raises(ValueError):
            walk_forward_opt_windows(100, train=10, test=10, embargo=-1)


# a bar stand-in the factory can read to make the "best" param regime-dependent
class _Bar:
    def __init__(self, close):
        self.close = close


def _bars(n):
    # a slow ramp so different windows sit in different "regimes"
    return [_Bar(1000.0 + i) for i in range(n)]


def _regime_target(close: float) -> int:
    # changes every 20 bars so consecutive windows sit in different regimes
    return (int(close) // 20) % 5 + 1


def _factory(bar_slice):
    # objective peaks when x matches this slice's regime, so fitted params
    # differ across windows
    target = _regime_target(bar_slice[0].close)

    def fn(params):
        x = params["x"]
        objective = -((x - target) ** 2) / 10.0  # <=0, best (0) at x==target
        returns = [0.001 * (x == target) + (0.003 if i % 2 else -0.003)
                   for i in range(30)]
        return objective, returns

    return fn


class TestFitting:
    def _space(self):
        return ParamSpace(Param("x", "int", 1, 5, default=3))

    def test_fits_per_window_and_scores_oos(self):
        bars = _bars(300)
        result = run_walk_forward_optimization(
            self._space(), bars, _factory, train=40, test=20, step=20,
            embargo=5, objective_name="return")
        assert len(result.windows) == len(result.chosen_params) > 1
        assert len(result.oos_objective) == len(result.windows)
        # each window fitted the x matching its own train regime
        for win, params in zip(result.windows, result.chosen_params, strict=True):
            assert params["x"] == _regime_target(bars[win.train_start].close)

    def test_summary_reports_oos_and_param_stability(self):
        bars = _bars(300)
        result = run_walk_forward_optimization(
            self._space(), bars, _factory, train=40, test=20, step=20, embargo=5)
        s = result.summary()
        assert s["windows"] == len(result.windows)
        assert "oos_sharpe" in s and "mean_oos_objective" in s
        # the ramp visits several regimes → more than one distinct param set
        assert s["distinct_param_sets"] > 1
        assert 0 < s["most_common_share"] <= 1.0

    def test_empty_when_window_too_large(self):
        result = run_walk_forward_optimization(
            self._space(), _bars(30), _factory, train=40, test=20)
        assert result.windows == [] and result.summary() == {"windows": 0}
