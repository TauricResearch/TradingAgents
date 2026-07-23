# 09 — API Specification

Deliverable 9. Endpoint contracts the six tracks add or change. Grounded in the current router (app.py): `GET /api/backtest`, `POST /api/backtest/run`, `POST /api/backtest/cancel`, `GET /api/backtest/job`, `GET /api/backtest/runs`, `GET /api/backtest/runs/{id}`, `GET /api/backtest/runs/{id}/artifacts/{name}`, `DELETE /api/backtest/runs/{id}`. Principle: **extend request/response bodies additively; add new endpoints for genuinely new job types.** All existing clients keep working.

## Compatibility contract

- New request fields are **optional with today's behavior as the default** (the `BacktestRunRequest` model already does this for `risk_per_trade_pct`/`max_position_pct` — same pattern).
- New response fields are additive; the frontend Zod schemas use `.passthrough()` + `.optional()`, so unknown/absent keys don't break parsing.
- `extra="forbid"` stays on request models → unknown request fields still 422 (prevents silent typos), so every new field must be declared.

## Changed: `POST /api/backtest/run`

`BacktestRunRequest` (backtest_job.py) gains:
```
strategy_id: str = "rules_v1"          # or "pipeline_llm"; validated against registry → 422 if unknown
strategy_params: dict = {}             # validated against the strategy's ParamSpace → 422 on out-of-range
symbols: list[str] = []                # empty ⇒ [symbol] (back-compat single-symbol)
timeframes: list[str] = []             # additional HTF views; empty ⇒ [timeframe]
cost_profile: str = "flat"             # "flat" (today) | "realistic" (spread+impact+funding)
```
- `use_llm` is retained and mapped: `use_llm=true` ⇒ `strategy_id="pipeline_llm"` unless `strategy_id` is set explicitly (explicit wins). This keeps the current toggle working.
- Multi-symbol runs still return `202 {job_id}`; the cost-confirmation (400 + estimate) and busy (409) flows are unchanged.
- Validation errors are specific: unknown `strategy_id` → 422 `{error:"unknown_strategy"}`; out-of-range param → 422 `{error:"param_out_of_range", param, allowed}`.

## New: optimization endpoints (T3)

```
POST /api/backtest/optimize        → 202 {optimization_id}
  body: {strategy_id, param_space (subset+overrides), search:"grid"|"random"|"bayesian",
         n_trials, symbols[], timeframes[], duration, walk_forward?:{train,test,step,embargo},
         objective:"sharpe"|"expectancy_r"|"mar"|…, confirm_cost:bool}
  - large trial counts require confirm_cost (mirrors the existing large-run gate):
    400 {error:"cost_confirmation_required", estimate:{trials, est_minutes}}
  - 409 if a backtest/optimization is already running (single-runner invariant kept)

GET  /api/backtest/optimize/job    → live optimization progress
     {optimization_id, status, trials_done, n_trials, best:{params, objective_value}, running_trial}

GET  /api/backtest/optimizations           → list (compact rows, like /runs)
GET  /api/backtest/optimizations/{id}      → full OptResult (spec, trials, guards)
GET  /api/backtest/optimizations/{id}/artifacts/{name}   → trials.csv, surface.json (heatmap)
DELETE /api/backtest/optimizations/{id}    → removes parent + all child runs (ring-unit, [08](08_data_schema.md) T3)
```
Progress streams over the **existing SSE broadcaster** with new event kinds `optimization_progress` / `optimization_done` (same pattern as `backtest_progress`) — no new stream endpoint, consistent with the current design note that the SPA holds one EventSource.

## New: strategy discovery (T1)

```
GET /api/backtest/strategies  → [{id, description, params:[{name,kind,low,high,step,choices,default}]}]
```
Lets the frontend render the strategy picker + parameter inputs dynamically from the registry (`list_strategies()`), instead of hard-coding the Deterministic/LLM toggle. The current toggle becomes two registry entries.

## Changed: run views/artifacts (read paths)

- `GET /api/backtest/runs` rows gain `strategy_id`, `n_symbols` (optional).
- `GET /api/backtest/runs/{id}` view carries the [08](08_data_schema.md) additive fields (`strategy_params`, `symbols`, `cost_models`, new metrics).
- `GET …/artifacts/{name}` accepts the new artifact names `orders`, `equity_by_symbol`, `rolling` (still a `FileResponse`; unknown name → 404, unchanged).

## New SSE event kinds (over the existing broadcaster)

| Event | Payload | Producer |
|---|---|---|
| `backtest_progress` (existing) | + optional `symbols_done`, `orders_working` | portfolio/order tracks |
| `optimization_progress` (new) | `{trials_done, n_trials, best}` | optimizer |
| `optimization_done` (new) | `{status, summary}` slim, like `backtest_done` | optimizer |

## Endpoints that do NOT change

`POST /api/backtest/cancel` (cancels whichever job runs — backtest or optimization), `GET /api/backtest/job`, and the artifact `FileResponse` mechanism are unchanged in shape. Cancel semantics extend to optimization: cancelling mid-sweep saves completed trials as a labeled-partial `OptResult` (mirrors the existing partial-save-on-cancel behavior for single runs).

## Auth / safety

No change to the auth posture: all endpoints stay behind the existing Google-sign-in gate + `X-API-Key` for direct access; optimization is compute, not capital, so it needs no new authorization tier. The single-runner 409 invariant prevents an optimization and a backtest from contending for the one worker.
