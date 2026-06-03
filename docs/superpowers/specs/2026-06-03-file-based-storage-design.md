# File-Based Storage & Per-Day Resume

**Date:** 2026-06-03
**Status:** Approved
**Supersedes:** SQLite-based persistence in `web/server/db.py` (Watchlist/Run/Event/LlmCall tables). The SQLite DB is removed in this change.

## Motivation

Replace the SQLite storage layer with a file-based one so that:

1. A user can inspect any run by opening its directory — no DB browser, no SQL.
2. **Resume works for real** — if the server crashes or a run is cancelled mid-way, clicking "Run" on the same ticker the same day skips already-completed nodes and re-runs only the remaining ones. This is achieved by enabling LangGraph checkpointing, which the framework already supports but the runner doesn't opt into.
3. **Per-day runs are isolated by design** — a different UTC day is a different `thread_id`, so a partial run from yesterday is historical data, not something today's run resumes into.
4. **Watchlist removal cleans up everything** — removing a ticker from the watchlist deletes its entire analysis history (data dir + framework checkpoint DB) in one operation.

The dashboard's display bug ("SQLite data saves but doesn't display") is fixed as a side effect: there is no SQLite to debug; the frontend reads the same JSON files the runner writes.

## Design Overview

All persisted state lives under `~/.tradingagents/data/`, with one directory per ticker and one subdirectory per run. There is no index file, no DB — listing runs is a directory walk.

The framework's existing LangGraph checkpointing (`tradingagents/graph/checkpointer.py`, per-ticker `SqliteSaver` at `~/.tradingagents/cache/checkpoints/{TICKER}.db`) is enabled and becomes the source of truth for *which nodes have already executed*. The new data dir is the source of truth for *what the user sees*. They are intentionally separate.

All timestamps in the data dir are UTC ISO-8601 with `Z` suffix. The only Israel-local representation is the **directory slug** (e.g. `2026-06-03_14-30-00_IDT`), which is purely for human readability.

## Data Model

### Directory layout

```
~/.tradingagents/data/
  watchlist.json
  NVDA/
    2026-06-03_14-30-00_IDT/
      run.json
      events.jsonl
      llm_calls.jsonl
      stages/
        market.json
        sentiment.json
        news.json
        fundamentals.json
        research.json
        risk.json
        trader.json
        decision.json
  AAPL/
    2026-06-04_09-12-00_IDT/
      ...
```

`~/.tradingagents/cache/checkpoints/NVDA.db` — framework-managed, separate concern. Cleared on watchlist removal.

### `watchlist.json`

```json
{
  "version": 1,
  "tickers": [
    {
      "ticker": "NVDA",
      "company_name": "NVIDIA Corporation",
      "exchange": "NASDAQ",
      "added_at": "2026-06-01T08:12:33.123456Z",
      "last_run_slug": "2026-06-03_14-30-00_IDT",
      "last_decision": "BUY",
      "last_decision_at": "2026-06-03T11:35:10.000000Z"
    }
  ]
}
```

### `{TICKER}/{SLUG}/run.json`

```json
{
  "id": "NVDA:2026-06-03T11:30:00.123456Z",
  "ticker": "NVDA",
  "slug": "2026-06-03_14-30-00_IDT",
  "started_at": "2026-06-03T11:30:00.123456Z",
  "finished_at": "2026-06-03T11:35:12.456789Z",
  "status": "completed",
  "cancel_requested": false,
  "decision": "BUY",
  "decision_at": "2026-06-03T11:35:10.000000Z",
  "decision_rationale": "...",
  "idempotency_key": "NVDA:2026-06-03",
  "completed_stages": ["market", "sentiment", "news", "fundamentals", "research", "risk", "trader", "decision"]
}
```

`completed_stages` is a denormalized cache derived from the actual `stages/*.json` files at read time.

### `events.jsonl` and `llm_calls.jsonl`

Append-only, one JSON object per line. Event payloads mirror the existing 14 `EventType` shapes so the frontend's `lib/events.ts` types stay unchanged. `llm_calls.jsonl` mirrors today's `LlmCall` table schema.

### `stages/{name}.json`

Unified shape per stage, written only on stage completion:

```json
{
  "stage": "market",
  "node": "Market Analyst",
  "state_key": "market_report",
  "completed_at": "2026-06-03T11:30:05.123Z",
  "duration_ms": 4123,
  "value": "## Market Report\n..."
}
```

| File | `state_key` | `value` |
|---|---|---|
| `stages/market.json` | `market_report` | report string |
| `stages/sentiment.json` | `sentiment_report` | report string |
| `stages/news.json` | `news_report` | report string |
| `stages/fundamentals.json` | `fundamentals_report` | report string |
| `stages/research.json` | `investment_debate_state` | debate state object |
| `stages/risk.json` | `risk_debate_state` | debate state object |
| `stages/trader.json` | `trader_investment_plan` | plan string |
| `stages/decision.json` | `final_trade_decision` | decision object |

**Crash semantics:** a stage file's *existence* is the flag. Mid-stage crash → no file → on resume that stage re-runs. There is no "started but not finished" representation; the filesystem *is* the status.

## Atomicity & Concurrency

Single FastAPI process, single runner queue, `asyncio.Semaphore(3)`. No multi-process writes.

| File | Write pattern |
|---|---|
| `watchlist.json`, `run.json`, `stages/*.json` | Write to `*.tmp` in same dir, `os.replace()` (atomic on POSIX and NTFS) |
| `events.jsonl`, `llm_calls.jsonl` | One `write()` of the full JSON line; truncated last line on crash is invalid JSON, reader skips it |

All reads go through a helper that returns `None` on `FileNotFoundError` / `JSONDecodeError` — the UI never crashes because a file is missing.

On server startup, walk `data/`. If a dir has `run.json.status == "running"` it is treated as a **resumable partial run** for today (only if `started_at`'s UTC date is today). Orphans (dir with no `run.json`) are logged and deleted.

## Backend Changes

### New module: `web/server/storage.py`

- `write_json_atomic(path, data)` — tmp + `os.replace`
- `append_jsonl(path, obj)` — single-line `write` + `flush`
- `read_json(path)` / `read_jsonl(path)` — return `None` on missing/invalid
- `slug_for_now()` — returns `2026-06-03_14-30-00_IDT` (or `_IST` in winter), via `zoneinfo.ZoneInfo("Asia/Jerusalem")`
- `find_resumable_run(ticker, today_iso)` — walks `data/{ticker}/`, returns the partial run dir whose `started_at` is today and `status == "running"`
- `clear_ticker_data(ticker)` — `shutil.rmtree(data_dir/ticker)` + `unlink(cache_dir/checkpoints/{ticker}.db)`

### `web/server/runner.py`

Two changes:

1. `build_graph()` merges `{"checkpoint_enabled": True}` into the config it passes to `TradingAgentsGraph`. This is the only setting change needed to enable real stage-level skip.
2. `_run_one()` calls `find_resumable_run()` before creating a new run dir. If a partial run exists for today, reuse its dir; the framework's `thread_id = sha256(ticker:trade_date)[:16]` is the same as yesterday's, so `graph.propagate()` resumes from the last completed node.

`enqueue()`'s body switches from `db.create_run(...)` to: create the dir, write `run.json`, put on queue.

### `web/server/events.py`

`emit()`'s persistence side changes from "insert into Event table" to "append to `events.jsonl`". WS broadcast logic is unchanged.

### `web/server/app.py`

- `GET /api/watchlist` — read `watchlist.json`
- `POST /api/watchlist` — read → mutate → atomic write; create empty `data/{TICKER}/`
- `DELETE /api/watchlist/{ticker}` — remove from `watchlist.json` + `clear_ticker_data(ticker)`
- `POST /api/runs` — body unchanged; server-side resume detection added. With `force: true`, resume detection is bypassed and a fresh run dir is created (the partial run from today is left in place under a "superseded" marker in `run.json.status` for historical reference, but not auto-deleted).
- `GET /api/runs/{run_id}` — read `run.json` + `events.jsonl` + `llm_calls.jsonl`; `run_id = "TICKER:STARTED_AT_UTC"`
- `GET /api/tickers/{ticker}/runs` — walk `data/{TICKER}/`, list slug dirs newest first
- WS handlers — same protocol; on connect, replay `events.jsonl` from the top (full read is fine for v1; per-byte offset can be added later if needed)

### `web/server/db.py`

Deleted. Replaced by `web/server/storage.py` and `web/server/queries.py` (read-side helpers).

## Frontend Changes

Minimal — the event protocol, store shape, and component APIs are unchanged. Only updates needed:

- The `run_id` format is now a string like `"NVDA:2026-06-03T11:30:00.123456Z"` instead of an integer. Type update in `lib/api.ts` and `store/ui.ts`.
- A "Resume" button is enabled on the ticker header only when `GET /api/tickers/{ticker}/runs` reports a `status == "running"` run with `started_at` matching today (UTC). Old partial runs render as "incomplete — N days ago" and are not resumable.
- Ticker row shows a "new run per day" hint so users understand the per-day scoping.

## Resume Mechanics

The flow when a user clicks "Run" on a ticker:

1. `POST /api/runs { ticker }` (no `force`).
2. Server: `today_iso = datetime.now(timezone.utc).date().isoformat()`.
3. Server: `partial = find_resumable_run(ticker, today_iso)`.
4. If `partial`:
   - Reuse `partial.run_dir`
   - Set `run.json.status = "running"` (idempotent)
   - `graph.propagate(ticker, trade_date=today_iso, event_callback=cb)`
   - Framework's `thread_id = sha256(f"{ticker}:{today_iso}")` matches the prior partial run's thread → LangGraph's `SqliteSaver` resumes from the last completed node.
5. Else:
   - `slug = slug_for_now()`
   - Create `data/{ticker}/{slug}/`
   - Write `run.json` with `started_at = now(UTC)`, `status = "running"`
   - Same `graph.propagate(...)` call; framework sees a fresh thread, runs all nodes.

The `event_callback` still fires for every node, so live WS streaming and `events.jsonl` capture work identically in both cases. The runner does not need to know whether the framework skipped nodes — it just sees a sequence of `node_entered` events for the remaining nodes.

### Per-day isolation

`trade_date` is passed as `datetime.now(timezone.utc).date().isoformat()` (UTC). At the small daily window where Asia/Jerusalem is on day N but UTC is still on day N-1 (00:00–02:59 Israel), a run started in that window shares a `thread_id` with the previous UTC day's runs and would resume from there. In practice this is rare; `force=true` overrides. A future fix can pass Israel date as `trade_date` if this ever bites.

### Watchlist removal cleanup

`DELETE /api/watchlist/{ticker}`:

1. Remove from `watchlist.json` (atomic write).
2. `shutil.rmtree(data_dir/ticker)`.
3. `unlink(cache_dir/checkpoints/{ticker}.db)` (the framework's `clear_checkpoint` operates per thread, not per ticker, so deleting the DB file is the cleanest per-ticker reset).

After this, re-adding the ticker starts a clean slate.

## Data Flow

```
POST /api/runs { ticker }
  -> find_resumable_run(ticker, today_utc) ?
       yes -> reuse run_dir
       no  -> create run_dir + write run.json
  -> enqueue(run_id)
  -> runner worker picks up:
       graph = build_graph(config with checkpoint_enabled=True)
       graph.propagate(ticker, trade_date=today_utc, event_callback=cb)
         -> node_entered -> cb -> events.emit -> events.jsonl + WS
         -> framework SqliteSaver persists state after each node
       final_state, signal = ...
  -> update run.json: finished_at, status, decision
  -> events.emit(run_finished)

Refresh / reload
  -> GET /api/runs/{run_id} -> {run.json, events.jsonl, llm_calls.jsonl, stages/*}
  -> useRestoredRunEvents seeds eventBuffer
  -> UI renders timeline + decision

Watchlist remove
  -> DELETE /api/watchlist/NVDA
  -> mutate watchlist.json (atomic)
  -> shutil.rmtree(data/NVDA)
  -> unlink(checkpoints/NVDA.db)
```

## Testing Strategy

### `web/server/tests/test_storage.py` (new)

- `write_json_atomic` survives concurrent reader holding old fd
- `append_jsonl` produces valid JSONL; truncated last line is skipped on read
- `slug_for_now` returns `*_IDT` in summer, `*_IST` in winter (use `freezegun`)
- `find_resumable_run` returns today's partial only, not yesterday's
- `find_resumable_run` returns `None` when no partial exists
- `clear_ticker_data` removes both the data dir and the checkpoint DB

### `web/server/tests/test_resume.py` (new)

- **Same-day resume:** start a run, abort mid-graph (mock propagate to raise after N events), restart, verify propagate is called again and the events stream resumes at the right node
- **Per-day isolation:** start a run on "day 1" (incomplete), start another on "day 2", verify day-1 dir is untouched and a new dir is created
- **`force=true`:** start a run (incomplete), call `POST /api/runs` with `force=true`, verify a new dir replaces the old and `stages/` is cleared
- **No partial = fresh run:** complete a run, start another, verify two distinct dirs

### Existing test suites — adapt

- `test_runner.py`, `test_callbacks.py`, `test_app.py` — replace SQLite fixtures with `tmp_path`-based data dirs; the fake `ScriptedRun` graph in `fixtures/fake_graph.py` is reused.

### Frontend

- Run detail page renders from the new event shape (should be transparent)
- "Resume" button is enabled iff today's partial exists
- Ticker row shows "incomplete — N days ago" for old partials

### What we do not test

- LangGraph checkpointing internals (framework's responsibility)
- LLM cache behavior (separate spec)
- Multi-process concurrency (single-process by design)
- Exotic filesystem `os.replace` semantics (local FS only)

## Scope

- **Backend new:** `web/server/storage.py` (~120 lines), `web/server/queries.py` (~60 lines), one-off migration script (`scripts/migrate_sqlite_to_files.py`, ~80 lines)
- **Backend modified:** `runner.py`, `events.py`, `app.py`, `llm_calls.py` — all switch from SQLModel to file IO
- **Backend deleted:** `web/server/db.py`
- **Frontend:** type update for `run_id` string; small UI affordance for resume button (~30 lines)
- **Config:** one env var, `TRADINGAGENTS_DATA_DIR` (default `~/.tradingagents/data`), already partially in use as `TRADINGAGENTS_DASHBOARD_DB`
- **Dependencies:** none added (stdlib `json`, `shutil`, `zoneinfo` are sufficient)
