# 10 — Strategy SDK Design

Deliverable 10. The keystone track (T1). Turns "the strategy is the LLM pipeline or its rules stand-in" into a **pluggable, declarative strategy unit** that the engine, optimizer, and portfolio layer can all drive. Grounded in the real seams: `BacktestEngine.run()` (engine.py:72), `BarReplay.snapshot_at(i)` (data.py:168), `SimBroker.open_from_recommendation` (broker.py:107).

## The problem it solves

Today `BacktestEngine.__init__` takes an `llm` and calls `build_pro_pipeline(...)`; `run()` does `state = self._pipeline.invoke({snapshot, equity})` and `_apply_decision` reads `state["recommendation"]`. A "strategy" is therefore either the full LLM graph or `RulesPipelineLLM`. There is no way to (a) register a named strategy, (b) declare its tunable parameters for the optimizer, or (c) run several strategies in a portfolio. T1 introduces that unit *without* removing the pipeline path.

## The `Strategy` protocol

```python
# tradingagents/pro/backtest/strategy.py  (new)
from typing import Protocol, runtime_checkable

@runtime_checkable
class Strategy(Protocol):
    id: str                      # registry key, e.g. "rules_v1"
    params: "ParamSpace"         # declared tunables (optimizer reads this)

    def on_start(self, ctx: "StrategyContext") -> None: ...
    def on_bar(self, ctx: "StrategyContext") -> "list[OrderIntent]": ...
    def on_fill(self, fill: "Fill") -> None: ...
    def on_stop(self, ctx: "StrategyContext") -> None: ...
```

- **`on_bar` returns order *intents*, not filled orders** — the broker decides fills next bar (preserves no-look-ahead). An intent is `{kind, side, qty_or_risk, limit/stop prices, bracket, tag}` (see [07_lld.md](07_lld.md) T2).
- Returning `[]` is HOLD. This maps cleanly onto today's `_apply_decision` returning `None`.
- `on_fill` lets a strategy track its own positions for pyramiding/scale-out decisions.

## `StrategyContext` — what a strategy sees

A read-only view assembled per bar from the replay + broker, so strategies never touch look-ahead-unsafe state:

```python
@dataclass(frozen=True)
class StrategyContext:
    snapshot: MarketSnapshot          # today's BarReplay.snapshot_at(i) — bars<=i
    htf: dict[Timeframe, MarketSnapshot]  # higher-TF views (T4), available only after HTF close
    equity: float                     # broker.equity(mark) — as today
    positions: tuple[PositionView, ...]  # open positions in this strategy's symbols
    account: AccountView              # cash, gross exposure, heat used
    params: Mapping[str, float|int|str]  # the resolved parameter values for this run
    regime: RegimeView | None         # T6: rule-based regime, look-ahead-safe
```

`snapshot` and `equity` are exactly what the engine already passes to `pipeline.invoke({...})` — so the context is a superset of today's inputs, not a new data path.

## Parameter declaration (enables the optimizer)

```python
@dataclass(frozen=True)
class Param:
    name: str
    kind: str            # "float" | "int" | "categorical"
    low: float = None; high: float = None; step: float = None
    choices: tuple = ()
    default: ... = None

class ParamSpace:
    def __init__(self, *params: Param): ...
    def grid(self) -> Iterator[dict]: ...       # T3 grid search
    def sample(self, rng) -> dict: ...          # T3 random/bayesian
    def defaults(self) -> dict: ...
```

`rules_v1` declares e.g. `neutral_band` (float 0.2–0.5), `chop_adx_threshold` (int 12–25), `tp_r_multiples` (categorical over a few ladders), `stop_atr_mult` (float 1.5–3.0). These already exist as constants in `signals.py`/`config.py`; T1 lifts them into a `ParamSpace` so they become tunable *and* stay a-priori-documented (the optimizer records which set ran — [12](12_validation_methodology.md)).

## The registry

```python
# tradingagents/pro/backtest/registry.py  (new)
_REGISTRY: dict[str, Callable[[dict], Strategy]] = {}

def register(strategy_id: str):
    def deco(factory): _REGISTRY[strategy_id] = factory; return factory
    return deco

def build_strategy(strategy_id: str, params: dict) -> Strategy: ...
def list_strategies() -> list[StrategyInfo]: ...   # id, params, description
```

No entry-points/plugin-loading magic (keeps determinism + auditability — consistent with the repo's "agents as configuration" ADR-0014). Strategies are registered in-process by importing their module.

## First citizen: the rules engine as `rules_v1`

The existing deterministic path (`signals.evaluate_refs` + `pipeline/gates.py` quality gates + the R-ladder geometry) is wrapped as the first registered strategy:

```python
@register("rules_v1")
class RulesStrategy:
    id = "rules_v1"
    params = ParamSpace(
        Param("neutral_band", "float", 0.2, 0.5, default=0.34),
        Param("chop_adx_threshold", "int", 12, 25, default=18),
        Param("stop_atr_mult", "float", 1.5, 3.0, step=0.25, default=2.0),
        Param("tp_ladder", "categorical",
              choices=("0.5/3.5", "1.0/3.0", "1.5/3.0"), default="0.5/3.5"),
    )
    def on_bar(self, ctx):
        refs = _refs_from(ctx.snapshot)                 # existing DataRef extraction
        vote = evaluate_refs(refs)                       # signals.py, unchanged
        if vote is None or adx_says_chop(...): return []  # unchanged chop filter
        # build entry+stop+TP bracket from the same risk.py geometry, but as
        # an OrderIntent bracket instead of a TradeRecommendation
        return [bracket_intent(...)]
```

This is a *refactor-behind-an-interface*, not new strategy logic — the votes, chop filter, gates, and ladder are the code that already ships and is already tested by `tests/test_pro_strategy_quality.py`. The LLM pipeline remains available as a second producer (wrapped as `pipeline_llm`), so `use_llm=true` runs keep working.

## How the engine drives it

`BacktestEngine` gains a `strategy: Strategy | None` param. When set, the loop calls `strategy.on_bar(ctx)` instead of `pipeline.invoke(...)`, translates returned intents into broker orders, and calls `on_fill` from `process_bar`'s results. When unset, the existing pipeline path runs unchanged. One branch, both paths deterministic.

## Backward compatibility

- Existing runs (`use_llm` true/false) map to `pipeline_llm` / `rules_v1` implicitly; the run record gains `strategy_id` + `params` ([08](08_data_schema.md)) so old records (no field) still load.
- `tests/test_pro_strategy_quality.py` and `test_pro_backtest_job.py` continue to exercise the rules path; new tests cover the registry, param enumeration, and intent translation.

## Why a protocol, not a base class

`runtime_checkable` `Protocol` lets the LLM pipeline wrapper and the rules strategy satisfy the same interface without a shared inheritance chain, and lets tests supply trivial fakes. It matches how `SimBroker`/`BarReplay` are already duck-typed in the engine constructor.
