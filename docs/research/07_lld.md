# 07 — Low-Level Design (per track)

Deliverable 7 (LLD half). Concrete seams for each track in [06_hld.md](06_hld.md): touched files, new modules, type-signature sketches, invariants preserved, migration notes, test strategy. Signatures are grounded in the current source (broker.py, engine.py, data.py, backtest_job.py, app.py) as read during S6 — they name real methods, not imagined ones.

Sketches show intent and shape; exact names settle at implementation. "**New**" = new module; "**Extend**" = additive change to an existing class.

---

## T1 — Strategy SDK & registry

**New:** `strategy.py` (protocol, `StrategyContext`, `OrderIntent`, `ParamSpace`), `registry.py`. Full design in [10_strategy_sdk.md](10_strategy_sdk.md).
**Extend:** `BacktestEngine.__init__` gains `strategy: Strategy | None = None`; `run()` branches: if `strategy`, call `strategy.on_bar(ctx)` and translate intents; else the existing `self._pipeline.invoke(...)` path (engine.py:88) unchanged.
**Invariants:** `on_bar` sees `StrategyContext` built from `snapshot_at(i)` (bars ≤ i) + `broker.equity(mark=bar.close)` — identical inputs to today's `pipeline.invoke({snapshot, equity})`. No new data reaches the strategy that the pipeline didn't already have.
**Migration:** `use_llm` maps to `pipeline_llm`; deterministic to `rules_v1`. `_build_llm` in backtest_job.py (line ~472) gains a `strategy_id`/`params` branch alongside its existing `RulesPipelineLLM()` return.
**Tests:** registry round-trip; `ParamSpace.grid()`/`sample()`; intent→broker translation; `rules_v1` reproduces current `test_pro_strategy_quality.py` outcomes bit-for-bit (regression guard).

---

## T2 — Order lifecycle / pending-order book

**Extend:** `SimBroker`. Today it holds `positions: dict[str, _OpenPosition]` and fills market-only at `fill_bar.open` (broker.py:130), ignoring `rec.entry_price`. Add a pending book:

```python
@dataclass
class PendingOrder:
    id: str; kind: str  # "market"|"limit"|"stop_entry"|"stop_limit"
    side: str; quantity: float
    limit_price: float | None; stop_price: float | None
    bracket: BracketSpec | None          # stop + TP ladder to attach on fill
    state: str = "WORKING"               # NEW→WORKING→FILLED|CANCELLED|EXPIRED
    expires_at: datetime | None; tag: str = ""

@dataclass
class BracketSpec:
    stop_loss: float; take_profits: list[tuple[float, float]]
    trailing: TrailingSpec | None = None   # T2 trailing stop

class SimBroker:
    pending: dict[str, PendingOrder]       # new
    def submit(self, order: PendingOrder) -> None: ...
    def cancel(self, order_id: str) -> None: ...
    def _match_pending(self, bar: OHLCVBar) -> list[Fill]: ...   # new, called first in process_bar
```

**Fill rules (extend the conservative touch policy at broker.py:159 `_manage`):**
- `limit` buy fills if `bar.low <= limit` (touch), at `min(limit, bar.open)`; symmetric for sells. Conservative: no price improvement beyond the limit.
- `stop_entry` buy triggers if `bar.high >= stop`, fills at `max(stop, bar.open)` + slippage (gap-through fills at the open, pessimistic).
- On fill, attach the bracket's stop + TP ladder exactly as `open_from_recommendation` does today (the current TP-ladder + `breakeven_after_tp1` logic becomes the default bracket).
- **Stop-before-TP pessimism preserved** (broker.py:161–166 order of checks unchanged).

**Pyramiding:** a strategy submits additional entry intents while a position is open; each fill adds an `_OpenPosition` keyed by a distinct id (the dict already supports N positions/symbol). The aggregate stop trails the combined position via a `TrailingSpec` evaluated in `_manage`. The `max_same_direction`/`max_open_positions` caps (broker.py:117–121) bound pyramid depth.

**Trailing stop:** `TrailingSpec{mode: "atr"|"pct"|"chandelier", mult}` ratchets `pos.stop` in `_manage` after each bar in the favorable direction only (never loosens). `pos.initial_stop` stays fixed (R-unit integrity, broker.py:213).
**Invariants:** `initial_stop` never mutates; R-accounting in `_finalize` (broker.py:211) unchanged; market path is `submit(kind="market")` and behaves exactly as today.
**Tests:** each order kind's touch/gap fill; bracket OCO (stop fill cancels TPs and vice versa); pyramid stop trailing; regression that a market bracket == today's `open_from_recommendation` result.

---

## T3 — Optimization + validation guards

**New:** `optimize.py` (search drivers), `validation.py` (guards). **Extend:** `walkforward.py` (currently stability-only — its window generator is reused for fitting).

```python
def run_optimization(spec: OptSpec, backtest_fn: Callable[[dict], BacktestResult]
                     ) -> OptResult:
    # spec: strategy_id, ParamSpace subset, search=grid|random|bayesian,
    #       n_trials, walk_forward=WFSpec|None, objective="sharpe"|"expectancy_r"|...
    # each trial is an ordinary deterministic BacktestEngine.run() (child job)
```

- **Search:** grid (`ParamSpace.grid()`), random (`sample`), optional Bayesian (skopt/Optuna if available; degrade to random if not — no hard dep).
- **Walk-forward *fitting*:** reuse `walkforward.py`'s rolling train/test window generator; fit params on each train window, evaluate on the immediately following test window, report out-of-sample concatenated performance. This is the honest upgrade of today's "no fitted parameters" stability check.
- **Guards** (`validation.py`, detail in [12](12_validation_methodology.md)): purged/embargoed K-fold split helper; `deflated_sharpe(sharpe, n_trials, skew, kurt, n_obs)`; `pbo(in_sample_ranks, oos_ranks)` (combinatorially-symmetric CV).
**Parallelism:** trials are embarrassingly parallel → `concurrent.futures.ProcessPoolExecutor`; this is the GIL relief for C4 (each child is its own process), not an engine rewrite.
**Invariants:** a trial cannot see test-window data during fitting (purge/embargo enforced in the split helper); trial count is logged so the deflated Sharpe denominator is honest.
**Tests:** grid enumerates the declared space; walk-forward split has no train/test overlap after embargo; deflated Sharpe and PBO match textbook worked examples (Bailey & López de Prado).

---

## T4 — Portfolio layer + multi-timeframe

**New:** `portfolio.py` (`PortfolioReplay`, capital allocator). **Extend:** `BarReplay` currently raises on >1 timeframe (data.py:113–115) — that guard stays for a *single* replay; the multi-TF/multi-symbol merge lives one level up.

```python
class PortfolioReplay:
    def __init__(self, replays: dict[str, BarReplay],       # symbol -> replay
                 htf: dict[str, dict[Timeframe, BarReplay]] = {}): ...
    def timeline(self) -> Iterator[tuple[datetime, dict[str, int]]]:
        # k-way merge of bar timestamps; yields (ts, {symbol: bar_index})
    def context_at(self, ts) -> dict[str, StrategyContext]: ...
```

- **HTF aggregation:** a higher-TF bar is visible only *after its close* — the merge exposes the last *completed* HTF bar at `ts`, never the forming one (look-ahead-safe, mirrors `snapshot_at`'s ≤ i rule).
- **Capital allocator:** `equal_weight | vol_normalized | fixed`; sits between strategy intents and `SimBroker.submit`, scaling per-symbol risk to a portfolio budget.
- **Risk engine extension:** `max_gross_exposure_pct` (broker.py:69) generalizes to a portfolio-heat cap across symbols; add a correlation-exposure cap (reject an entry that would push correlated-cluster exposure over a limit — the Donchian+correlation pattern from [02](02_pattern_report.md)).
**Invariants:** single-symbol/single-TF is the degenerate case (`PortfolioReplay({sym: replay})`); determinism preserved by sorting the merge by `(ts, symbol)`.
**Tests:** k-way merge ordering; HTF bar not visible before close (look-ahead assertion); allocator budget conservation; correlation cap rejects the right entry.

---

## T5 — Cost & financing realism

**Extend:** `costs.py`. Today `SlippageModel` is flat bps, `CommissionModel` is bps+min, `LiquidityModel` is a participation cap (all constructor-injected into `SimBroker`, broker.py:65–67).

```python
class SpreadModel:      # per-asset half-spread in bps, time-varying optional
    def half_spread_bps(self, bar, asset) -> float: ...
class ImpactModel:      # square-root: impact_bps = k * sqrt(qty / bar.volume)
    def impact_bps(self, qty, bar) -> float: ...
class FundingModel:     # perp funding accrual per holding interval
    def accrue(self, pos, bar) -> float: ...   # charged to cash_pnl in process_bar
```

**Invariants:** flat models remain the defaults (opt-in realism); every model is provenance-labeled in the run view so results are never silently mixed; funding accrual is deterministic from the (as-of-safe) funding series.
**Tests:** impact scales with participation; spread widens the effective fill; funding sign correct for long/short; defaults reproduce today's numbers exactly.

---

## T6 — Analytics additions

**Extend:** `metrics.py` (`PerformanceReport`) and `report.py` (`ExtendedReport`). Purely additive fields:

```python
# metrics.py PerformanceReport gains:
omega: float | None; mar: float | None
ulcer_index: float | None; upi: float | None
tail_ratio: float | None; gain_to_pain: float | None
cvar_95: float | None
# report.py adds rolling_sharpe/rolling_sortino/rolling_vol series (windowed)
```

**Invariants:** existing metrics unchanged (getattr-tolerant readers already in place from the R-metrics work); new fields default `None` so old artifacts/tests don't break.
**Tests:** each metric vs a hand-computed fixture; None-safety on degenerate (empty/one-trade) series.

---

## Cross-cutting: what does NOT change

`BarReplay.snapshot_at` look-ahead rule, the `for i in range(min_history, len(bars)-1)` decision/fill separation (engine.py:78), the conservative intrabar policy, R-accounting, full-fidelity artifacts, and the hard risk gates are invariant across all six tracks. Every track adds a module or an additive field; none rewrites the loop. See [08_data_schema.md](08_data_schema.md) for the artifact/record deltas and [09_api_spec.md](09_api_spec.md) for the endpoint changes these require.
