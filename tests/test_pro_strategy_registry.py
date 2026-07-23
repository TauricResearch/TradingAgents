"""Strategy registry (roadmap P0.2 / architecture track T1): registration,
parameter-validated construction, discovery, and duplicate/unknown guards.

The registry is a module-global; each test snapshots and restores it so the
suite stays hermetic regardless of what registers strategies at import time."""

import pytest

from tradingagents.pro.backtest import (
    OrderIntent,
    Param,
    ParamSpace,
    Strategy,
    build_strategy,
    is_registered,
    list_strategies,
    register,
    registry as reg,
)


@pytest.fixture(autouse=True)
def _isolate_registry():
    saved = dict(reg._REGISTRY)
    reg._REGISTRY.clear()
    try:
        yield
    finally:
        reg._REGISTRY.clear()
        reg._REGISTRY.update(saved)


class _Strat:
    def __init__(self, params):
        self.id = "demo_v1"
        self.params = _SPACE
        self.resolved = params

    def on_start(self, ctx): ...
    def on_bar(self, ctx):
        return [OrderIntent(kind="market", side="BUY", risk_pct=self.resolved["risk"])]
    def on_fill(self, fill): ...
    def on_stop(self, ctx): ...


_SPACE = ParamSpace(
    Param("risk", "float", 0.1, 5.0, step=0.1, default=1.0),
    Param("mode", "categorical", choices=("a", "b"), default="a"),
)


def _register_demo():
    @register("demo_v1", _SPACE, description="demo strategy")
    def _factory(params):
        return _Strat(params)
    return _factory


class TestRegistry:
    def test_register_and_build_with_defaults(self):
        _register_demo()
        assert is_registered("demo_v1")
        strat = build_strategy("demo_v1")
        assert isinstance(strat, Strategy)
        assert strat.resolved == {"risk": 1.0, "mode": "a"}

    def test_build_merges_and_validates_overrides(self):
        _register_demo()
        strat = build_strategy("demo_v1", {"risk": 2.5})
        assert strat.resolved["risk"] == 2.5 and strat.resolved["mode"] == "a"

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="unknown strategy"):
            build_strategy("nope_v9")

    def test_out_of_domain_param_raises(self):
        _register_demo()
        with pytest.raises(ValueError, match="outside declared domain"):
            build_strategy("demo_v1", {"risk": 99.0})
        with pytest.raises(ValueError, match="unknown parameter"):
            build_strategy("demo_v1", {"typo": 1})

    def test_duplicate_registration_raises(self):
        _register_demo()
        with pytest.raises(ValueError, match="already registered"):
            _register_demo()

    def test_list_strategies_reports_schema_sorted(self):
        _register_demo()

        @register("aaa_v1", _SPACE, description="first")
        def _f(params):
            return _Strat(params)

        infos = list_strategies()
        assert [i.id for i in infos] == ["aaa_v1", "demo_v1"]  # id-sorted
        demo = next(i for i in infos if i.id == "demo_v1")
        assert demo.description == "demo strategy"
        assert [p["name"] for p in demo.params] == ["risk", "mode"]
        assert demo.params[1]["choices"] == ["a", "b"]

    def test_built_strategy_emits_intents_from_resolved_params(self):
        _register_demo()
        strat = build_strategy("demo_v1", {"risk": 0.5})
        intents = strat.on_bar(object())  # ctx unused by demo
        assert len(intents) == 1 and intents[0].risk_pct == 0.5
