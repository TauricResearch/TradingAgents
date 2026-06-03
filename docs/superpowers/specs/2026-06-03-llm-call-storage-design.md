# LLM Call Storage & Run History

**Date:** 2026-06-03
**Status:** Approved

## Motivation

Save all LLM calls per run so users can: resume analysis of a ticker, exit and come back to a previous run, and rerun a ticker. The core lookup is `(ticker, datetime)` → run + its LLM calls.

## Design Overview (Approach 2)

A structured `llm_call` SQL table + per-ticker run selector in the frontend. The existing event protocol and WS streaming are unchanged — the new storage layer sits alongside them.

## Data Model

### New table: `llm_call`

```python
class LlmCall(SQLModel, table=True):
    __tablename__ = "llm_call"
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(index=True)
    ticker: str = Field(index=True)
    node_name: str                              # analyst stage
    started_at: datetime
    model: str
    prompt_text: str                            # full assembled prompt
    response_text: str                          # full LLM output
    tool_calls_json: str                        # JSON array of tool calls
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration_ms: int
```

Composite index on `(ticker, run_id)`.

### Existing `Run` table — add `force` support

The `idempotency_key` column already exists. A `force` flag on the POST endpoint skips the dedup check.

## Backend Changes

### 1. `callbacks.py` — New `CaptureCallbackHandler`

A second LangChain callback handler that accumulates the full interaction per LLM call:
- `on_chat_model_start` → store the full messages list
- `on_llm_end` → read response, count tokens, format tool calls, emit a structured event via `events.emit` which persists an `LlmCall` row

Runs alongside the existing `StreamingCallbackHandler` (live fragment emission is unchanged).

### 2. `db.py` — New functions

- `save_llm_call(...)` → creates `LlmCall` row
- `llm_calls_for_run(run_id)` → returns list of `LlmCall`
- `list_runs_for_ticker(ticker)` → returns runs filtered by ticker

### 3. `app.py` — New API endpoints

- `GET /api/tickers/{ticker}/runs` — all runs for a ticker (id, started_at, status, decision)
- `GET /api/runs/{run_id}` — add `llm_calls` to the existing response
- `POST /api/runs` — add optional `force: bool` body param to bypass daily idempotency

### 4. `runner.py` — `force` propagation

`enqueue()` accepts a `force` param. When `true`, `create_run` in `db.py` skips the idempotency check and always creates a new run.

## Frontend Changes

### Store (`ui.ts`)

Add:
- `historicalRunIdByTicker: Record<string, number | null>` — when set, overrides `lastRunIdByTicker` for display
- `setHistoricalRunForTicker(ticker, runId)` / `clearHistoricalRun(ticker)`

### TickerHeader — Run selector dropdown

- Fetch `GET /api/tickers/{ticker}/runs` on mount
- Render a small `<select>` showing `#run_id · date · status (decision)`
- When user picks a historical run → fetch run events via `GET /api/runs/{run_id}`, call `restoreEvents()` on store

### Rerun button

- Adjacent to "Run analysis" button
- Calls `POST /api/runs { ticker, force: true }`
- Clears buffer and starts fresh run

## Data Flow

```
Run analysis (force=true)
  → POST /api/runs { ticker, force: true }
  → Runner starts → Graph.propagate()
     → CaptureCallbackHandler accumulates LLM calls
     → on_llm_end → emit event → save LlmCall row
     → Fragment events fire as before (live WS stream)
  → WS broadcasts → eventBuffer → UI renders live

Load historical run
  → Select run from dropdown
  → GET /api/runs/{run_id} (events + llm_calls)
  → store.setHistoricalRunForTicker()
  → store.restoreEvents() → eventBuffer updated
  → All display components re-render from historical events
```

## Scope

- **Backend:** ~80 lines (table + DB helpers + callback + endpoints)
- **Frontend:** ~80 lines (store additions + selector + rerun button)
- **Total:** ~160 lines across ~8 files
- **No new dependencies**
