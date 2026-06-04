# Run Metadata Enrichment — Design

**Date:** 2026-06-04
**Status:** Approved
**Scope:** Backend storage + API + frontend display

## Goal

Every analysis run should persist and surface, alongside the existing run fields,
three additional pieces of context that today are either unrecorded or
invisible in the UI:

1. **Model used** — provider, deep-thinking model, quick-thinking model.
2. **Ticker price at run start** — snapshot from the live price poller.
3. **Run status** — already persisted; this work ensures it stays visible
   alongside the new fields and that failed runs are clearly distinguished.
4. **Per-stage duration** — already in `stages/{stage}.json`; this work
   surfaces it in the UI.
5. **Total run duration** — wall-clock seconds from start to terminal state;
   new persistence + display.

## Motivation

A user reviewing a historical run today has no way to know which model
produced the decision, what the price context was, or how long the run took
without opening log files. Decision rationale is often price- and
model-sensitive; recording these at run time makes historical runs
self-explanatory and supports future comparison (e.g. "did the model
upgrade change decision quality?").

## Non-Goals

- Backfilling existing runs (the 4 runs from 2026-06-04 will have nulls
  for the new fields).
- Capturing price *changes* during a run (only the start price is recorded).
- Per-LLM-call model attribution on `run.json` (already in `llm_calls.jsonl`).
- Sum-of-stages vs. wall-clock reconciliation reporting.

## Approach

Extend `run.json` additively with new nullable fields. Keep per-stage data in
`stages/{stage}.json` where it already lives — no duplication. Shape a stable
wire format through `run_to_dict()`. Display the new fields in the run
dropdown, history drawer, and timeline.

## Storage Schema

### `run.json` (additions only)

| Field                | Type          | When written                  | Nullable |
|----------------------|---------------|-------------------------------|----------|
| `llm_provider`       | `string`      | `create_run_dir` time         | no       |
| `deep_think_model`   | `string`      | `create_run_dir` time         | no       |
| `quick_think_model`  | `string`      | `create_run_dir` time         | no       |
| `start_price`        | `number\|null`| `_run_one` after queue pickup | yes      |
| `start_price_at`     | `string\|null`| `_run_one` after queue pickup | yes      |
| `total_duration_s`   | `number\|null`| terminal `mark_run_status`    | yes      |

`status` is unchanged; existing values: `running | done | failed | superseded`.

### `stages/{stage}.json` (unchanged)

Already contains `duration_ms` (int) and `completed_at` (ISO). Surfaced
through `GET /api/runs/{run_id}` via the `stages` array.

## Capture Flow

### Models (at `create_run_dir` time)

`web/server/storage.py:create_run_dir()` gains three optional kwargs
defaulting to `DEFAULT_CONFIG` values. `web/server/runner.py:enqueue()`
passes `DEFAULT_CONFIG["llm_provider"]`, `["deep_think_llm"]`,
`["quick_think_llm"]` through. Fields are on disk from t=0 of every new run.

### Start price (after queue pickup)

In `web/server/runner.py:_run_one()`, immediately after the worker picks up
the job, read the live poller snapshot for the ticker from the shared
`PriceState.snapshots` cache (`web/server/price_feed.py`). Call
`storage.mark_run_status(run_id, start_price=..., start_price_at=...)`.
If no snapshot is available, both fields remain `null`.

### Total duration (at every terminal site)

The runner already computes `duration_s = round(time.monotonic() - t_start, 2)`
on the success path (line 456). Add a parallel `failure_duration_s` capture
at each failure site (lines 310, 389, 393, 415, 426). Pass
`total_duration_s=...` to each `mark_run_status(...)` call.

## API

### `run_to_dict()` (`web/server/queries.py`)

Add to the returned dict:

```python
"llm_provider": r.get("llm_provider"),
"deep_think_model": r.get("deep_think_model"),
"quick_think_model": r.get("quick_think_model"),
"start_price": r.get("start_price"),
"start_price_at": r.get("start_price_at"),
"total_duration_s": r.get("total_duration_s"),
```

Plus a **derived** field for live display:

```python
if r.get("status") == "running" and r.get("started_at"):
    out["elapsed_s"] = (now_utc() - parse_iso(r["started_at"])).total_seconds()
else:
    out["elapsed_s"] = None
```

### TypeScript types (`web/frontend/src/lib/api.ts`)

`RunRow` and `RunDetail` gain matching fields. `duration_ms` is already
present on each stage object.

## UI Display

### `TickerHeader.tsx` — `runLabel(r)`

Append segments conditionally; each piece hides itself cleanly when its
data is missing.

```
{started_at} — {decision_action?} · {deep_think_model?} · ${start_price?} · {total_duration_s?}
```

For the live (current) run, show `elapsed_s` ticking up.

### `RunHistoryDrawer.tsx` — each row

Append the model and duration to the existing sub-line so the drawer
matches the dropdown.

### `RunTimeline.tsx` — per-stage

Show `duration_ms` next to each stage name. Format: `2 ms`, `1.4s`,
`1m 23s` (auto-pick unit by magnitude).

## Error Handling & Edge Cases

- **Existing 4 runs** — no migration. New fields are null; UI shows `—`.
- **Poller snapshot unavailable** — `start_price`/`start_price_at` null;
  label omits the price segment.
- **Failed runs** — `total_duration_s` is captured at the failure site
  with the same wall-clock math; status is `failed` (cancellation is
  distinguished via the existing `error: "cancelled"` field, unchanged).
- **yfinance hiccup at startup** — `resolve_instrument_identity` already
  swallows exceptions; the new price-snapshot read is also non-fatal
  (try/except → log + leave null).
- **Concurrent writes** — `mark_run_status` and `write_stage` are already
  atomic; no new race surface.

## Testing

### Backend

- `test_storage.py` — `create_run_dir` writes the three model fields and
  leaves `start_price`/`start_price_at`/`total_duration_s` null.
- `test_storage.py` — `mark_run_status` patches `total_duration_s` and
  `start_price*` correctly.
- `test_queries.py` (or `test_app.py`) — `run_to_dict` includes the new
  fields; `elapsed_s` is computed only when `status == "running"`.
- `test_runner.py` — every terminal site (1 success + 5 failure paths)
  writes `total_duration_s`; success path passes through the
  `duration_s` it already computed.

### Frontend

- `TickerHeader.test.tsx` (or existing equivalent) — `runLabel` produces
  the expected string for: full data, partial data, no data.
- `RunTimeline.test.tsx` — each stage renders its `duration_ms` formatted.

### Manual / Integration

- Trigger an end-to-end run; confirm the new fields appear in the
  dropdown, drawer, and timeline.

## Files Touched

**Backend**
- `web/server/storage.py` — `create_run_dir` accepts model kwargs.
- `web/server/runner.py` — passes model kwargs; captures `start_price` in
  `_run_one`; writes `total_duration_s` at every terminal site.
- `web/server/queries.py` — `run_to_dict` exposes the new fields + derived
  `elapsed_s`.
- `web/server/price_feed.py` — possibly add a `snapshot(ticker) -> dict | None`
  helper to keep the runner read-site tidy.

**Frontend**
- `web/frontend/src/lib/api.ts` — `RunRow` / `RunDetail` types.
- `web/frontend/src/components/TickerHeader.tsx` — `runLabel` formatting;
  live `elapsed_s` for the current run.
- `web/frontend/src/components/RunHistoryDrawer.tsx` — append to each row.
- `web/frontend/src/components/RunTimeline.tsx` — per-stage duration
  display.

**Tests**
- `web/server/tests/test_storage.py`
- `web/server/tests/test_runner_pm_decision.py` (extend)
- `web/frontend/src/__tests__/TickerHeader.test.tsx` (or new)
- `web/frontend/src/__tests__/RunTimeline.test.tsx` (extend)

## Out-of-Scope Follow-Ups (for a future spec)

- Backfill helper to read prices from yfinance historical for old runs.
- Per-run model-version diffing view.
- Per-stage LLM-call attribution rollup on `run.json`.
