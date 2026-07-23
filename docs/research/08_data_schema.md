# 08 — Data & Artifact Schema Deltas

Deliverable 8. What the six tracks change in the persisted shapes: the per-run **artifacts** (`RunArtifacts` — equity/trades/decisions JSON), the **run record/view** (`summary_from_view` + `build_view` in backtest_job.py), and the **Firestore/file run store**. Principle: **additive and versioned** — every old record and artifact must still load.

## Current persisted shapes (baseline)

- **Artifacts** (`backtest_artifacts.py`): `equity.json` = `[[iso_ts, equity], …]` (one row/decision); `trades.json` = list of `closed_trade_view` dicts; `decisions.json` = per-decision funnel rows.
- **Run view** (`build_view`, backtest_job.py): `{provider, symbol, timeframe, duration, window, window_truncated, bars, indicator_mode, initial_equity, risk_per_trade_pct, max_position_pct, artifacts, report, …}`.
- **Summary** (`summary_from_view`): the compact run-list row + Firestore doc.
- **Run record:** `{id, created_at, params, status, summary, view}`.

## Schema version marker (new, enables safe evolution)

Add `schema_version: int` to the run record (absent ⇒ treat as version 0, the current shape). Readers switch on it; writers always emit the current version. This is the one change that must land *first* so every subsequent delta is detectable.

## T1 — Strategy identity

Run view + summary gain:
```
strategy_id: str        # "rules_v1" | "pipeline_llm" | …
strategy_params: dict   # the resolved parameter values that ran
```
Old records (no field) ⇒ infer `provider=="rules"` → `rules_v1`, `provider=="llm"/deterministic` accordingly; `strategy_params` defaults `{}`. Reproducibility: a run can be replayed exactly from `strategy_id` + `strategy_params` + `window`.

## T2 — Orders artifact (new)

New artifact `orders.json` = the full order lifecycle, one row per order:
```json
{"id","kind","side","qty","limit_price","stop_price","bracket":{...},
 "submitted_at","state","filled_at","fill_price","expired_at","tag","parent_id"}
```
`parent_id` links pyramid add-ons and bracket children. The existing `trades.json` (closed trades) is unchanged; `orders.json` is the new sibling and is listed in `view["artifacts"]`. Trades gain optional `entry_order_id` + `pyramid_group` to join back to orders.

## T3 — Optimization job records (new record type)

An optimization run is a parent over N child backtests:
```json
{"id","schema_version","type":"optimization","created_at","status",
 "spec":{"strategy_id","param_space","search","n_trials","walk_forward","objective"},
 "trials":[{"params","objective_value","in_sample","out_of_sample","child_run_id"}],
 "guards":{"deflated_sharpe","pbo","n_trials","best_params"},
 "summary":{...}}
```
Child runs are ordinary run records (reuse everything above) with `parent_optimization_id` set. The store's prune-to-25 ring must treat an optimization + its children as one unit (don't orphan children) — a `parent_optimization_id` index handles this.

## T4 — Portfolio / multi-symbol

- Run view: `symbol: str` → also `symbols: list[str]` (single-symbol runs set `symbols=[symbol]` for back-compat); add `timeframes: list[str]` (HTF views) alongside the primary `timeframe`.
- Artifacts: `equity.json` stays the *portfolio* curve; add `equity_by_symbol.json` = `{symbol: [[ts, equity], …]}` for per-symbol decomposition. `trades.json` rows already carry `symbol`, so no change there.
- Summary gains `n_symbols`.

## T5 — Cost model provenance

Run view gains `cost_models: {slippage, spread, impact, funding, commission, liquidity}` recording which model + params ran (e.g. `{"slippage":"flat_2bps","impact":"sqrt_k0.1","funding":"binance_perp"}`). Trades gain optional `funding_paid` and `impact_bps` so per-trade cost attribution is auditable. Defaults reproduce today's flat numbers and label them `"flat_2bps"` etc.

## T6 — Analytics fields

`report` object (inside the view + `metrics.json` if separately persisted) gains the new metric keys from [07](07_lld.md) T6 (`omega`, `mar`, `ulcer_index`, `upi`, `tail_ratio`, `gain_to_pain`, `cvar_95`), all optional, all defaulting `null`. Rolling series (`rolling_sharpe`, …) go in a new `rolling.json` artifact (they're arrays, keep them out of the compact record).

## Firestore / file store impact

- `FirestoreRunStore` and the file store persist the record as-is — the deltas are all additive dict keys, so no store code changes beyond the ring-unit fix for optimization parents (T3).
- The `backtest_state/current` checkpoint doc gains `schema_version` and, for optimization jobs, `trials_completed` / `n_trials` for progress.
- Legacy JSON import (the one-time migration path) sets `schema_version=0` on imported records.

## Migration & compatibility rules

1. **Never remove or repurpose a field.** New capability = new key.
2. **Every new field is optional with a null/empty default** so pre-existing artifacts and Firestore docs deserialize unchanged (the frontend Zod schemas already use `.optional()`/`.passthrough()` — extend the same way).
3. **`schema_version` gates only *interpretation*, never load success.** A version-0 record renders as a single-symbol market-only run; a version-1+ record renders orders/portfolio/optimization detail.
4. **Reproducibility invariant:** any run record + its artifacts must contain enough to re-run it deterministically (`strategy_id`, params, window, cost models, seed). This is the acceptance test for the schema work.
