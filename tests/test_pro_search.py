"""Iterative parameter search (track T3): genetic + Bayesian (TPE) samplers.

Covers seed-determinism, byte-identical serial==parallel (the load-bearing
property the equivalence suite relies on), guard population over EVERY
evaluated trial, convergence toward the known optimum, and walk-forward
inheritance of the new modes."""

import pytest

from tradingagents.pro.backtest import Param, ParamSpace, run_optimization
from tradingagents.pro.backtest.search import (
    GeneticSampler,
    TPESampler,
    build_sampler,
)


def _quadratic(params):
    """Module-level (picklable) synthetic trial: objective peaks at x=3, with a
    little return variation so the guards can compute."""
    x = params["x"]
    objective = -((x - 3) ** 2)
    returns = [0.001 * x + (0.004 if i % 2 else -0.004) for i in range(60)]
    return objective, returns


def _space():
    return ParamSpace(Param("x", "int", 0, 6, default=3))


# --- determinism -------------------------------------------------------------


@pytest.mark.parametrize("search", ["genetic", "bayesian"])
def test_seeded_search_is_deterministic(search):
    a = run_optimization(_space(), _quadratic, search=search, seed=7)
    b = run_optimization(_space(), _quadratic, search=search, seed=7)
    assert [t.params for t in a.trials] == [t.params for t in b.trials]
    assert [t.objective for t in a.trials] == [t.objective for t in b.trials]
    assert a.best_params == b.best_params


@pytest.mark.parametrize("search", ["genetic", "bayesian"])
def test_serial_equals_parallel_byte_identical(search):
    serial = run_optimization(_space(), _quadratic, search=search, seed=11,
                              max_workers=1)
    parallel = run_optimization(_space(), _quadratic, search=search, seed=11,
                                max_workers=4)
    assert [t.params for t in serial.trials] == [t.params for t in parallel.trials]
    assert [t.objective for t in serial.trials] == [t.objective for t in parallel.trials]
    assert serial.best_objective == parallel.best_objective
    assert serial.deflated_sharpe == parallel.deflated_sharpe
    assert serial.pbo == parallel.pbo


# --- guards + selection ------------------------------------------------------


@pytest.mark.parametrize("search", ["genetic", "bayesian"])
def test_guards_see_every_trial(search):
    result = run_optimization(_space(), _quadratic, search=search, seed=1)
    # the whole search budget is evaluated, not just a surviving population
    _, total = build_sampler(_space(), search, 1, {})
    assert result.n_trials == total
    assert result.deflated_sharpe is not None and result.pbo is not None
    assert isinstance(result.verdict(), str)


@pytest.mark.parametrize("search", ["genetic", "bayesian"])
def test_search_finds_the_optimum(search):
    # objective peaks at x=3; both samplers should land on it over a wide range
    space = ParamSpace(Param("x", "int", 0, 40, default=0))
    cfg = ({"population": 16, "generations": 8} if search == "genetic"
           else {"n_trials": 80, "n_startup": 12})
    result = run_optimization(space, _quadratic, search=search, seed=5,
                              search_config=cfg)
    assert abs(result.best_params["x"] - 3) <= 1


def test_search_config_sizes_the_budget():
    g = run_optimization(_space(), _quadratic, search="genetic", seed=0,
                         search_config={"population": 6, "generations": 3})
    assert g.n_trials == 18
    b = run_optimization(_space(), _quadratic, search="bayesian", seed=0,
                         search_config={"n_trials": 20, "n_startup": 5})
    assert b.n_trials == 20


# --- sampler units -----------------------------------------------------------


def test_genetic_sampler_ask_tell_lifecycle():
    s = GeneticSampler(_space(), population=4, generations=3, seed=0)
    seen = 0
    while True:
        batch = s.ask()
        if not batch:
            break
        assert len(batch) == 4
        s.tell(batch, [-abs(p["x"] - 3) for p in batch])
        seen += 1
    assert seen == 3  # exactly `generations` generations


def test_tpe_warmup_then_model():
    s = TPESampler(_space(), n_trials=10, n_startup=4, batch=2, seed=0)
    asked = []
    while True:
        batch = s.ask()
        if not batch:
            break
        asked.extend(batch)
        s.tell(batch, [-((p["x"] - 3) ** 2) for p in batch])
    assert len(asked) == 10


def test_build_sampler_rejects_unknown():
    with pytest.raises(ValueError, match="unknown iterative search"):
        build_sampler(_space(), "grid", 0, {})


# --- walk-forward inheritance ------------------------------------------------


def test_walk_forward_inherits_new_search_modes():
    from tradingagents.pro.backtest.walkforward import run_walk_forward_optimization

    # the factory ignores the slice (this is a wiring smoke test), so bars only
    # need to len()/slice — no real OHLCV construction required
    bars = list(range(60))

    def factory(_slice):
        return _quadratic

    result = run_walk_forward_optimization(
        _space(), bars, factory, train=20, test=10, search="bayesian")
    assert result.chosen_params  # windows fit + scored OOS without error
