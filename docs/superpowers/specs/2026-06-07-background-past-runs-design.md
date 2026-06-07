# Background Past Runs — Design

**Date:** 2026-06-07
**Status:** Draft (pending user review)
**Scope:** Backend background-runs orchestrator + CLI subcommand + bottom-slide dashboard drawer + per-run progress + ETA + auto-resume

## Goal

Let a user schedule a series of past-dated `propagate(ticker, past_date)` runs that execute in the background, with a live UI for monitoring, pause, resume, and cancel. The runs themselves are the artifact — they land in the existing per-ticker run storage, so the existing dashboard views (Run History, Historical Analysis Drawer, the price chart) pick them up automatically with no schema break.

Specifically:

1. **A "Past Runs" bottom-slide drawer** in the dashboard, opened by a button next to "History".
2. **A backend orchestrator** (`web/server/background_runs.py`) that holds the job queue, spawns worker threads, persists state, and survives a server restart.
3. **A CLI subcommand** (`tradingagents run-past ...`) with the same surface, for parity and headless operation.
4. **A new job form** inside the drawer: ticker (defaults to the focused ticker), from-date, to-date, cadence (default `1d`), parallelism (default `1`). Max parallelism capped at `4`.
5. **Per-job progress bar** showing `current_index / total` plus a **live ETA** computed as `(avg_duration_of_completed_iterations × remaining) / parallelism`.
6. **Cancel / pause / resume** semantics that work across a server restart (state is on disk).
7. **Auto-resume on server startup**: any job whose state on disk says `status: "running"` is re-spawned; iterations whose date already has a `done` run on disk are skipped.
8. **No new on-disk run schema**: each iteration lands in the same `~/.tradingagents/data/{TICKER}/{date}/{run_slug}/run.json` path, with two new metadata fields (`background_run_id`, `background_run_iteration_index`).

## Motivation

Today, a user can trigger a single past-dated run from the CLI, but cannot schedule a series, cannot monitor progress, and cannot tell a long-running backtest apart from a one-shot run. The data is there — `propagate()` already accepts a past `trade_date` and the data layer already filters at the requested date to prevent look-ahead — but the orchestration layer is missing.

This feature gives the user a way to: "for ticker NVDA, run an analysis for every business day from 2024-01-01 to 2024-06-30, in the background, while I keep using the dashboard." The runs then show up in the existing per-ticker run list and chart, and can be evaluated by the Historical Analysis Drawer the same way manually-triggered runs can.

## Non-Goals

- **Aggregated backtest report** with cumulative P&L, hit rates, or per-decision accuracy. Each iteration is a regular run; the user evaluates them with the existing chart drawer. A separate feature.
- **Verdict aggregation across iterations.** The Historical Analysis Drawer already does this for whatever runs exist on disk.
- **Scheduling** (cron-style recurring runs). The user kicks off jobs manually.
- **Multi-ticker jobs** in a single run. The form is for one ticker at a time. (Easy follow-up: extend `start()` to accept a list of tickers.)
- **Distributed execution.** Single-process, multi-thread. No Celery / Redis / RQ.
- **WebSocket push for iteration updates.** Polling at 2s while a job is running is enough for the UX we want; no need for a socket layer.
- **Resumable iteration-level retries with backoff.** If a single iteration fails, it logs an error and the loop continues. The user can `cancel` and `start` a new job to retry.
- **Streaming LLM output to the dashboard.** The drawer shows job-level progress, not per-stage progress of a single run. (Per-stage progress already exists in the main pane for a focused run.)
- **Forward-dated runs** (running an analysis for *tomorrow*'s date). The form rejects `date_to > today`. This is purely a "run the analysis for past dates" feature.
- **Ticker validation against the watchlist.** The form is a dropdown populated from the watchlist; the API validates ticker format (regex) but does not gate against the watchlist, so a custom ticker sent via CLI or curl is accepted. If `propagate()` can't find data for the ticker, the per-iteration error surfaces in the drawer's feed.
- **Deletion of past jobs** from the drawer UI. Files persist on disk; the user can `rm -rf` the directory. (CLI subcommand `run-past delete` is a trivial follow-up.)
- **Encryption of `iteration_errors`** in `state.json`. The file is local, just like the existing per-run files.

## Approach

A new backend module holds job state, spawns Python threads to run iterations, and persists state to disk on every meaningful transition. A new FastAPI router exposes six endpoints. A new frontend drawer (mirroring the existing right-side drawer's slide pattern) calls those endpoints and renders jobs with TanStack Query polling. A new CLI subcommand under `tradingagents run-past ...` shares the orchestrator module's public surface so headless and dashboard use cases are driven by the same code path.

Iteration runs are normal `TradingAgentsGraph().propagate(ticker, date)` calls. After each call returns, the orchestrator opens the resulting `run.json`, tags it with `background_run_id` + `background_run_iteration_index`, and writes it back atomically. Everything else is unchanged.

## Storage Schema

### New on-disk shape

```
~/.tradingagents/data/background_runs/
  {job_id}/
    state.json            # job metadata + status
    iteration_dates.txt   # one ISO date per line, the resolved date list
    iteration_errors.json # dict: {date_iso: error_str}; absent when no errors
```

`job_id` format: `bgr_{ISO8601_compact}_{TICKER}` — e.g. `bgr_2026-06-07T19-30-00Z_NVDA`. Human-greppable, no collision risk.

### `state.json` shape

```json
{
  "job_id": "bgr_2026-06-07T19-30-00Z_NVDA",
  "ticker": "NVDA",
  "date_from": "2024-01-01",
  "date_to": "2024-06-30",
  "every": "1d",
  "parallel": 2,
  "total": 130,
  "current_index": 12,
  "avg_duration_s": 47.3,
  "eta_s": 2851,
  "started_at": "2026-06-07T19:30:00Z",
  "finished_at": null,
  "status": "running",
  "durations_s": [50.1, 48.7, 46.0, 51.2, 49.5, 45.0, 48.0, 47.1, 46.5, 48.0, 47.0, 45.5]
}
```

- `status` ∈ `{running, paused, done, cancelled, error}`.
- `durations_s` is the per-iteration wall-clock seconds for completed iterations only. Its mean is the rolling `avg_duration_s`. The full list is kept (not just the mean) so the UI can show a histogram in a future iteration; the cap is bounded by `total` so disk use is O(total) per job.
- `eta_s` is recomputed on every `state.json` write; the formula is below.

### Per-iteration tagging

Each iteration's existing `run.json` gets two new fields, written via a post-hoc atomic rewrite:

```json
{
  "background_run_id": "bgr_2026-06-07T19-30-00Z_NVDA",
  "background_run_iteration_index": 12
}
```

The `run_to_dict()` helper in `web/server/` already serializes unknown fields as part of the run payload (per the 2026-06-04 enrichment spec), so this is a non-breaking change for the API and dashboard.

### Persistence semantics

- `state.json` is written via `tempfile.NamedTemporaryFile` + `os.replace()` to avoid torn writes.
- The write happens after every iteration completes (success or error) and immediately on `pause` / `cancel` / `resume` so the disk state is always close to in-memory.
- On startup, the module scans `~/.tradingagents/data/background_runs/*/state.json` and re-spawns threads for any job in `status: "running"`. Iterations whose date already has a `done` `run.json` on disk are skipped (resume-safety).

## API

### `POST /api/background-runs`

**Request body**
```json
{
  "ticker": "NVDA",
  "date_from": "2024-01-01",
  "date_to":   "2024-06-30",
  "every":     "1d",
  "parallel":  1
}
```

**Response 201**
```json
{ "job_id": "bgr_2026-06-07T19-30-00Z_NVDA" }
```

**Validation (returns 422 on failure)**
- `ticker`: non-empty string, ≤ 16 chars, uppercase, regex `^[A-Z0-9.\-]+$`.
- `date_from`, `date_to`: ISO `YYYY-MM-DD`.
- `date_from <= date_to`.
- `date_to <= today` (UTC). Past-dated runs only.
- `every` ∈ `{1d, 1w, 2w, 1mo}`.
- `parallel` integer, 1 ≤ parallel ≤ 4.

If `date_to < today` and `every` is 1d, the resolved date list excludes weekends by default — see `dates()` below. (No `include_weekends` knob in v1.)

### `GET /api/background-runs`

Returns the most recent 50 jobs (any status), sorted by `started_at` desc. Used to populate the drawer's "Past jobs" section on first open.

**Response 200**
```json
{
  "jobs": [
    {
      "job_id": "...",
      "ticker": "NVDA",
      "date_from": "2024-01-01",
      "date_to": "2024-06-30",
      "every": "1d",
      "parallel": 2,
      "total": 130,
      "current_index": 12,
      "avg_duration_s": 47.3,
      "eta_s": 2851,
      "started_at": "2026-06-07T19:30:00Z",
      "finished_at": null,
      "status": "running"
    },
    ...
  ]
}
```

### `GET /api/background-runs/{job_id}`

Returns one job (same shape as above, single object). Polled at 2s while any job is `running`.

### `POST /api/background-runs/{job_id}/cancel`

Sets the cancel event. The current iteration (if any) finishes; the loop exits; `status = "cancelled"`, `finished_at = now()`. Idempotent (calling on a `done` / `cancelled` job returns 200 with no effect).

### `POST /api/background-runs/{job_id}/pause`

Sets the pause event. The current iteration (if any) finishes; the loop parks; `status = "paused"`. `eta_s` is recomputed as `ceil(avg_duration_s × (total - current_index) / parallel)` at the moment of pausing.

### `POST /api/background-runs/{job_id}/resume`

If `status == "paused"`, clears the pause event and re-spawns the worker thread (the old one exited cleanly on pause). `status = "running"`.

### Error responses

| Code | Body | When |
|---|---|---|
| 404 | `{"error": "job_not_found", "detail": "{job_id}"}` | Unknown `job_id` |
| 422 | `{"error": "validation", "detail": "..."}` | Bad input |
| 409 | `{"error": "invalid_state", "detail": "..."}` | `resume` on a `done` job, `cancel` / `pause` on a terminal job, etc. |

## Date Generator

```python
def dates(date_from: str, date_to: str, every: str) -> list[str]:
    """Return ISO date strings, inclusive on both ends, weekends excluded for 1d/1w."""
    f = date.fromisoformat(date_from)
    t = date.fromisoformat(date_to)
    if f > t: raise ValueError(...)
    match every:
        case "1d":  step = timedelta(days=1); skip_weekends = True
        case "1w":  step = timedelta(weeks=1); skip_weekends = True
        case "2w":  step = timedelta(weeks=2); skip_weekends = True
        case "1mo": step = relativedelta(months=1); skip_weekends = False
    ...
```

- For `1d`, the resolution is **business days** (Mon–Fri). NYSE holidays are not skipped in v1 (would require an external holiday calendar; documented limitation).
- For `1w`, the step lands on Mondays when possible.
- For `1mo`, the step lands on the same day-of-month of the from date. If that day-of-month doesn't exist in a month (e.g., 31st in Feb), the step lands on the last day of that month. Weekends are not skipped for monthly cadence.
- The function is **deterministic and pure** — same inputs always produce the same output. Tested as a unit.

## Orchestration Loop

### Module-level state (`web/server/background_runs.py`)

```python
_jobs: dict[str, _JobHandle] = {}

@dataclass
class _JobHandle:
    job_id: str
    cancel_event: threading.Event
    pause_event:  threading.Event
    thread:       threading.Thread | None
    state:        BackgroundRunState
    lock:         threading.Lock
```

A per-job `lock` guards writes to `state` and to `durations_s`. The cancel/pause events are checked at iteration boundaries (not mid-iteration) so a `propagate()` call always runs to completion.

### `start(ticker, date_from, date_to, every, parallel) -> str`

1. Validate inputs (raises on failure, surfaces as 422 in the API).
2. Resolve `dates(date_from, date_to, every)` → `date_list`.
3. Create the job directory: `~/.tradingagents/data/background_runs/{job_id}/`.
4. Write `iteration_dates.txt`.
5. Build `BackgroundRunState`, write `state.json` (`status: "running"`).
6. Insert `_JobHandle` into `_jobs`.
7. Spawn a `threading.Thread(target=_run, args=(job_id,))`, set `daemon=True`, start.
8. Return `job_id`.

### `_run(job_id)` (the worker)

```python
def _run(job_id: str) -> None:
    handle = _jobs[job_id]
    state  = handle.state
    executor = ThreadPoolExecutor(max_workers=state.parallel)
    futures: dict[Future, str] = {}
    next_idx = state.current_index
    date_list = read_iteration_dates(job_id)

    while next_idx < len(date_list):
        if handle.cancel_event.is_set(): break
        while handle.pause_event.is_set():
            time.sleep(0.5)
            if handle.cancel_event.is_set(): break
        if handle.cancel_event.is_set(): break

        # Fill the pool up to `parallel` futures
        while len(futures) < state.parallel and next_idx < len(date_list):
            date_iso = date_list[next_idx]
            if _has_done_run(state.ticker, date_iso):
                next_idx += 1
                continue   # resume-safety
            fut = executor.submit(_run_one, state.ticker, date_iso)
            futures[fut] = date_iso

        if not futures:
            break

        done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)
        for fut in done:
            date_iso = futures.pop(fut)
            t0 = time.monotonic() - t_start_for_this_iteration  # measured in _run_one
            try:
                result = fut.result()  # raises on failure
            except Exception as exc:
                _record_iteration_error(state, date_iso, str(exc))
            else:
                _tag_run(state, date_iso, next_idx_for_this_date)  # post-hoc rewrite
                _record_completion(state, result.duration_s)
            next_idx += 1

    # Drain remaining futures on cancel
    if handle.cancel_event.is_set():
        for fut in list(futures):
            fut.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

    state.current_index = min(next_idx, len(date_list))
    state.finished_at  = _now_iso()
    state.status       = "cancelled" if handle.cancel_event.is_set() else "done"
    state._persist()
    executor.shutdown(wait=True)
```

### `_run_one(ticker, date_iso) -> _IterationResult`

Wraps `TradingAgentsGraph().propagate(ticker, date_iso)`. Returns a result with `duration_s`; raises on failure. Uses the existing per-ticker run storage path; doesn't know about background jobs.

### `_tag_run(state, date_iso, iteration_index)`

Locates the most recent `run.json` for `(state.ticker, date_iso)`, opens it, sets the two background-run fields, and writes it back atomically. If no `run.json` exists (the iteration produced nothing), this is a no-op + a warning log (shouldn't happen if `propagate()` succeeded, but defensive).

### `_has_done_run(ticker, date_iso) -> bool`

Resume-safety check. Returns `True` if any `run.json` in `~/.tradingagents/data/{TICKER}/{date_iso}/*/` has `status: "done"`. Used to skip already-completed dates on resume.

### `_load_existing_jobs() -> None`

Called once at server startup. Scans `background_runs/*/state.json`; for each `status: "running"`, builds a `_JobHandle`, spawns a thread, returns. For `status: "paused"`, builds the handle but does not spawn (waits for explicit `resume` via API or CLI).

## Auto-Resume

On `web/server/app.py` startup (in the `lifespan` context manager, after the existing `run_to_dict` warmup):

1. Call `background_runs._load_existing_jobs()`.
2. Log: `Resuming N background run(s): {job_ids}`.
3. No threads are spawned for `paused` jobs.
4. No blocking — startup continues immediately.

The drawer's polling picks up the resumed jobs within 2s of the server coming up.

## CLI

New subcommand under the existing `tradingagents` CLI (entry point: `cli/main.py`):

```
tradingagents run-past TICKER --from 2024-01-01 --to 2024-06-30 [--every 1d] [--parallel 1]
tradingagents run-past list
tradingagents run-past status JOB_ID
tradingagents run-past cancel JOB_ID
tradingagents run-past pause JOB_ID
tradingagents run-past resume JOB_ID
```

`run-past` (no subcommand) defaults to `start`. All subcommands call into `web/server/background_runs.py` directly — the CLI shares the orchestrator, doesn't go through the HTTP API. Output is plain text (not JSON), formatted for terminal use:

```
$ tradingagents run-past status bgr_2026-06-07T19-30-00Z_NVDA
job_id:    bgr_2026-06-07T19-30-00Z_NVDA
ticker:    NVDA
range:     2024-01-01 → 2024-06-30 (1d, parallel=2)
status:    running
progress:  12 / 130  (9.2%)
avg:       47.3s
eta:       38m 21s
started:   2026-06-07 19:30:00Z
errors:    0
```

The CLI subcommand imports `web.server.background_runs` directly. This means the CLI and the dashboard share the same in-process state when both are running, but the CLI is typically used to seed jobs and exit; it doesn't keep the threads alive after the command returns. (Threads are daemon threads; they die with the Python process. The orchestrator is designed to run inside the FastAPI server's process.)

**Caveat to document**: if the user starts a job via the CLI and the CLI exits, the job dies. The CLI is for **one-shot kicking off**, not for long-running hosting. To host a job, the user runs the dashboard server (`tradingagents dashboard`) which calls `start()` via the HTTP API and stays up. The CLI's `start` writes the same `state.json` to disk; if the dashboard server is also running, the dashboard's poll will pick up the CLI-spawned job and display it (the in-memory `_jobs` dict is **not** shared across processes, so the CLI's threads are independent — but for a single user, this is fine; they can either use the CLI OR the dashboard to host jobs).

For the v1, document this clearly: **use the dashboard server to host background jobs**. The CLI's `start` exists primarily so the user can verify the date generator from a terminal.

## UI Display

### Drawer trigger

A new button "Past Runs" in the header (in `web/frontend/src/App.tsx`) immediately to the right of the "History" button. Same styling as the existing History button. Click → opens `BackgroundRunsDrawer` (slides up from the bottom; see below).

### Drawer placement

**Bottom slide**, not right slide. The Historical Analysis Drawer already owns the right edge. Past Runs slides up from the bottom edge, ~45% of the viewport height. Same animation pattern as the right-side drawer (fixed positioning + translate transition), with `translate-y-full` ↔ `translate-y-0` toggled by the existing `ui.ts` boolean `backgroundRunsOpen`. The drawer casts a subtle shadow upward (`shadow-[0_-8px_24px_-12px_rgba(0,0,0,0.15)]`).

### Drawer layout (top to bottom)

```
┌──────────────────────────────────────────────────────────────────┐
│ Background Past Runs                                        [×] │  ← Header
├──────────────────────────────────────────────────────────────────┤
│  ▼ New job                                                        │
│  Ticker:  [NVDA       ▾]   From:  [2024-01-01]   To:  [2024-06-30]│
│  Every:   [1d ▾]   Parallel: [1 ▾]              [ Start ]         │
├──────────────────────────────────────────────────────────────────┤
│  Active jobs (1)                                                  │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ NVDA · 2024-01-01 → 2024-06-30 · 1d                        │   │
│  │ ███████████░░░░░░░░░░░░  12 / 130  (9.2%)                 │   │
│  │ ETA: 38m 21s  ·  parallel: 2                               │   │
│  │                                                            │   │
│  │ 2024-01-15 11:30:02  done  · 47.1s  ·  BUY @ $148.20      │   │
│  │ 2024-01-16 11:31:18  done  · 49.5s  ·  HOLD               │   │  ← Live
│  │ 2024-01-17 11:29:55  done  · 46.0s  ·  SELL @ $152.00      │   │     iteration
│  │ 2024-01-18 11:30:40  error  ·  propagate() raised: ...     │   │     feed
│  │ ...                                                        │   │     (last 20)
│  │                                                            │   │
│  │ [ Pause ]  [ Cancel ]                                      │   │
│  └────────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│  ▼ Past jobs (last 10)                                            │
│  NVDA  2024-01-01 → 2024-03-31  1d  ✓ done  61/61 in 47m 12s   >  │
│  MU    2024-04-01 → 2024-04-30  1d  ✗ cancelled  8/22 in 6m 4s  >│
│  ...                                                              │
└──────────────────────────────────────────────────────────────────┘
```

### New job form

- **Ticker**: dropdown populated from the existing watchlist. Defaults to the currently focused ticker (read from `ui.focusedTicker`).
- **From / To**: `<input type="date">`. To defaults to today. From defaults to 30 days before To.
- **Every**: dropdown of `{1d, 1w, 2w, 1mo}`. Default `1d`.
- **Parallel**: dropdown of `{1, 2, 4}`. Default `1`.
- **Start** button. Disabled while a request is in flight.

On click → calls `startBackgroundRun(...)` → on 201 success, optimistically adds the new job to the "Active jobs" list and immediately starts polling. On 422, displays the validation error inline below the form (red text, dismisses when the form changes).

### Active job row

- Ticker + range + cadence + parallel shown as a one-line header.
- **Progress bar** — div with `bg-slate-200` track and `bg-blue-500` fill, width = `current_index / total * 100%`. `aria-valuenow={current_index}` `aria-valuemax={total}` for accessibility.
- **Stats line** — `current_index / total  (pct%)`.
- **ETA** — `Xm Ys` or `Hh Mm`; see formatter below. Hidden when `current_index == 0` (no completed iterations yet) — replaced with `Calculating…`. Hidden when `status != "running"`.
- **Status pill** — color-coded: `running` (blue), `paused` (amber), `done` (green), `cancelled` (gray), `error` (red).
- **Live iteration feed** — list of the last 20 completed iterations. Each row: date (formatted), status badge (done/error), duration in seconds, action + start price (if the run produced a decision). Updates with each poll.
- **Action buttons** — Pause (only when `status == "running"`), Resume (only when `status == "paused"`), Cancel (only when `status` ∈ {`running`, `paused`}).

### Past jobs section

- Collapsible. Shows the most recent 10 non-active jobs (`status` ∈ {`done`, `cancelled`, `error`}), sorted by `started_at` desc.
- Each row: ticker, range, cadence, status pill, `current_index / total`, and the **actual** total wall-clock duration (`finished_at - started_at`). Click → opens a side panel (or expanded inline) listing the per-iteration dates with their statuses.
- Clicking an iteration date opens that run in the main pane, same as clicking a date in the Historical Analysis Drawer.

### ETA formatter

```ts
function fmtEta(etaS: number | null): string {
  if (etaS == null) return "Calculating…";
  if (etaS < 60)    return `${Math.ceil(etaS)}s`;
  if (etaS < 3600)  return `${Math.floor(etaS/60)}m ${Math.ceil(etaS%60)}s`;
  return `${Math.floor(etaS/3600)}h ${Math.floor((etaS%3600)/60)}m`;
}
```

### Polling

- `GET /api/background-runs` is polled at 2s while any job is `running` or `paused`. When all jobs are in a terminal state, polling pauses (interval = `false`).
- `GET /api/background-runs/{job_id}` is polled for the focused active job, also at 2s.
- TanStack Query's `enabled` flag on the per-job query is `false` when the drawer is closed.

## Progress Bar + ETA Math

### `avg_duration_s`

Computed by the orchestrator after each completed iteration:

```python
with state.lock:
    state.durations_s.append(duration_s)
    state.avg_duration_s = sum(state.durations_s) / len(state.durations_s)
```

Only **successful** iterations are appended to `durations_s` — failed iterations are excluded from the average because they fail fast (no LLM call, just an exception in setup) and would skew the average low. The "Past jobs" section reports the actual wall-clock duration of the whole job for reference.

### `eta_s`

```python
remaining = state.total - state.current_index
eta_s = max(0, ceil(state.avg_duration_s * remaining / state.parallel))
```

- `remaining = 0` → `eta_s = 0` → the UI hides the ETA line.
- `state.avg_duration_s == 0` (no completed iterations yet) → `eta_s` is computed but the UI shows `Calculating…` until at least one iteration completes.
- `state.parallel == 0` (shouldn't happen — guarded by validation) → falls back to 1 to avoid division by zero. Defensive only.

### Concurrency caveat (documented)

The formula assumes ideal parallelism. In practice, LLM rate-limits and varying per-iteration latency mean the actual wall-clock time is often closer to `(avg × remaining) / (parallel × 0.7)`. The rolling average self-corrects as the job runs. The simpler formula matches the user's spec and keeps the math transparent.

## Error Handling

| Failure | Where caught | UX |
|---|---|---|
| `propagate()` raises on a single iteration | `_run_one` raises, caught in `_run` loop | Recorded in `iteration_errors.json` for the date; the loop continues. The iteration feed shows the error row with a red badge. The job's `status` stays `running`. |
| All iterations fail | Loop completes, all errors | `status = "error"`, `finished_at` set. Drawer shows a red error banner above the job card. |
| `date_from > date_to` | `start()` raises | API → 422. Drawer shows inline validation error. |
| `date_to > today` | `start()` raises | API → 422. Drawer shows inline validation error. |
| `every` not in allowed set | `start()` raises | API → 422. Drawer shows inline validation error. |
| `parallel > 4` or `< 1` | `start()` raises | API → 422. Drawer shows inline validation error. |
| Server restart mid-job | `_load_existing_jobs()` on startup | Threads re-spawn for `running` jobs. `_has_done_run` skips already-completed dates. |
| Crash mid-iteration | `current_index` not incremented until the iteration finishes; iteration result not tagged | The post-restart resume retries the date. Idempotent: if the previous attempt actually wrote a `run.json`, `_has_done_run` returns True and the retry is skipped. |
| `_tag_run` fails (e.g., `run.json` was deleted between the `propagate` call and the tag) | Caught in `_run` loop, logged at WARN | Iteration is counted as completed (duration appended) but is not tagged. The user can inspect the run manually. |
| User clicks Cancel | Sets `cancel_event` | Current iteration finishes; loop exits; `status = "cancelled"`. |
| User clicks Pause | Sets `pause_event` | Current iteration finishes; loop parks; `status = "paused"`. |
| User clicks Resume | Clears `pause_event`, re-spawns thread | `status = "running"`. |
| LLM rate-limit on an iteration | `propagate()` raises (existing rate-aware-retry logic from 2026-06-02 spec); the retry is internal to propagate; if it ultimately fails, the iteration is recorded as an error | Same as the first row. |
| Two CLI processes / two servers starting jobs at once | Not guarded in v1 | Both write to `_jobs`; threads are independent. If two processes try to write to the same `state.json`, last-write-wins on the atomic `os.replace()`. Documented as a v2 concern (PID file lock). |
| `_jobs` dict grows unbounded across many jobs | `_load_existing_jobs()` is called once at startup; threads are not removed from `_jobs` when they finish | Bounded by the number of `running` / `paused` jobs at any time. Terminal jobs stay in `_jobs` but their threads are `None` and their events are set; the next `_load_existing_jobs` call (on next startup) prunes entries whose `status` is terminal. For v1, a background sweep every 5 minutes removes terminal jobs from `_jobs`. |
| Drawer polls during a long server-side iteration write | TanStack Query's `staleTime: 0` ensures the poll always re-fetches | No conflict: server writes are atomic; client always sees a consistent `state.json`. |
| User starts two jobs for the same ticker in parallel | Not blocked in v1 | Both jobs run independently. Their iterations interleave on disk but each `run.json` is tagged with its own `background_run_id`, so attribution is preserved. |

## Testing

### Backend unit (`web/server/tests/test_background_runs.py` — new)

- `dates("2024-01-01", "2024-01-05", "1d")` → `["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]`.
- `dates("2024-01-05", "2024-01-08", "1d")` skips the weekend → `["2024-01-05", "2024-01-08"]`.
- `dates("2024-01-01", "2024-02-01", "1w")` lands on Mondays.
- `dates("2024-01-01", "2024-06-01", "2w")` lands every other Monday.
- `dates("2024-01-31", "2024-04-30", "1mo")` → `["2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30"]` (Feb caps at 29 in leap year).
- `start()` rejects: `date_from > date_to`, `date_to > today`, `every` not in enum, `parallel > 4` or `< 1`, empty / malformed ticker.
- `start()` writes `state.json` and `iteration_dates.txt`.
- `start()` with `parallel=2` and a `fake_propagate` that sleeps 100ms: total wall-clock time is roughly `(N / 2) × 100ms` (with a loose upper bound to avoid CI flakiness).
- `cancel()` flips status to `cancelled` and the worker exits within one iteration boundary.
- `pause()` then `resume()`: the worker parks, then resumes; no iterations are skipped.
- Auto-resume on startup: pre-seed a `state.json` with `status: "running"` and a stub `_has_done_run` that returns False; call `_load_existing_jobs()`; assert a thread is spawned and the loop processes all remaining dates.
- Auto-resume skips completed dates: pre-seed with a `run.json` for one date; assert that date is skipped on resume.
- `_tag_run` adds the two fields to the most recent `run.json` for the `(ticker, date)` pair.
- `_tag_run` is a no-op + WARN log if no `run.json` exists.
- `eta_s` formula: with `avg_duration_s = 50`, `total = 100`, `current_index = 20`, `parallel = 2` → `eta_s = ceil(50 × 80 / 2) = 2000`.
- `avg_duration_s` updates on every completed iteration (rolling mean).

### Backend API integration (`web/server/tests/test_api.py` — extend)

- `POST /api/background-runs` returns 201 with a `job_id`.
- `GET /api/background-runs` returns up to 50 jobs.
- `GET /api/background-runs/{job_id}` returns the state.
- 404 for unknown `job_id`.
- 422 for bad input (each validation path).
- 409 for `resume` on a `done` job, `cancel` on a `cancelled` job, etc.
- `cancel` / `pause` / `resume` happy paths return 200 and update the state.

### Backend test seam (`web/server/tests/fixtures/fake_propagate.py` — new)

A monkey-patchable `propagate` that:
- Records every call in a list.
- Sleeps for a configurable duration (default 50ms).
- Writes a fake `run.json` to the standard path (so `_has_done_run` and `_tag_run` can be exercised).
- Optionally raises (controlled per-test via a list of "fail on these indices").

The seam is wired up in `conftest.py` and replaces `TradingAgentsGraph.propagate` for the duration of any test that requests the `fake_propagate` fixture.

### Frontend (`web/frontend/src/components/BackgroundRunsDrawer.test.tsx` — new, Vitest + Testing Library)

- Renders the form with the focused ticker preselected.
- Submitting the form calls `startBackgroundRun` and shows the new job in the "Active" section (using a mocked TanStack Query client).
- 422 from the API is displayed inline below the form.
- Clicking Pause calls the pause endpoint and updates the job's status pill.
- Renders empty state when there are no jobs.
- ETA formatter: `fmtEta(null)` → `Calculating…`; `fmtEta(45)` → `45s`; `fmtEta(125)` → `2m 5s`; `fmtEta(3700)` → `1h 1m`.
- Progress bar width reflects `current_index / total`.
- `fmtEta(0)` hides the ETA line (component test: assert the element is not in the DOM when `eta_s == 0`).

### Frontend (`web/frontend/src/backgroundRuns.test.ts` — new, Vitest)

- The polling query's `refetchInterval` is `2000` when any job is `running` and `false` otherwise.

### Manual / integration checklist (executed pre-merge)

- Start a job with `parallel=1`, watch the progress bar advance and ETA tick down.
- Start a job with `parallel=4`, watch 4 iterations finish in roughly the same wall-clock window.
- Start a job, click Pause, wait 5s, click Resume — confirm the thread resumed, no iterations were skipped, ETA is recomputed.
- Start a job, click Cancel mid-flight — confirm the worker exits within one iteration, `status` flips to `cancelled`.
- Start a job, `kill -9` the server, restart it — confirm the job is re-spawned and continues from where it left off.
- Start a job, let it finish, click the row in "Past jobs" — confirm the per-iteration list shows the expected dates and statuses.
- Start two jobs for different tickers in parallel — confirm both progress independently.
- Try to submit a form with `date_to > today` — confirm the 422 error renders inline.
- Try to submit a form with `parallel=8` (not in dropdown, but the API should also guard it) — confirm 422.
- Resize the drawer on a small screen — confirm the layout doesn't break (responsive sanity check; the drawer is bottom-anchored and the form wraps).
- The Historical Analysis Drawer (right-side) continues to work while the bottom drawer is open — confirm no z-index conflict.
- Polling stops (or drops to background) when the browser tab is hidden — TanStack Query default behavior, but verify.

## Files Touched

### Backend

| File | Action |
|---|---|
| `web/server/background_runs.py` | **new** — orchestrator, state, threads, date generator |
| `web/server/app.py` | extend — register 6 endpoints + call `_load_existing_jobs()` in `lifespan` startup |
| `cli/main.py` | extend — add `run-past` subcommand with start / list / status / cancel / pause / resume |
| `web/server/tests/test_background_runs.py` | **new** |
| `web/server/tests/test_api.py` | extend with 6 endpoint integration cases |
| `web/server/tests/fixtures/fake_propagate.py` | **new** |
| `web/server/tests/conftest.py` | extend — wire up the `fake_propagate` fixture |

### Frontend

| File | Action |
|---|---|
| `web/frontend/src/components/BackgroundRunsDrawer.tsx` | **new** — bottom-slide drawer |
| `web/frontend/src/components/BackgroundRunsDrawer.test.tsx` | **new** |
| `web/frontend/src/lib/api.ts` | extend — types + fetchers: `startBackgroundRun`, `getBackgroundRuns`, `getBackgroundRun`, `cancelBackgroundRun`, `pauseBackgroundRun`, `resumeBackgroundRun`; types `BackgroundRunState`, `BackgroundRunSummary`, `StartBackgroundRunRequest` |
| `web/frontend/src/store/ui.ts` | extend — `backgroundRunsOpen` boolean + setter, persisted via existing `persist` middleware |
| `web/frontend/src/App.tsx` | extend — add "Past Runs" button + mount `BackgroundRunsDrawer` |
| `web/frontend/src/backgroundRuns.test.ts` | **new** — polling-interval unit test |

### Docs

| File | Action |
|---|---|
| `docs/superpowers/specs/2026-06-07-background-past-runs-design.md` | **this file** |
| `docs/superpowers/plans/2026-06-07-background-past-runs-plan.md` | new (created via writing-plans skill) |
| `README.md` | extend — add a "Background past runs" section under Usage with a CLI example and a screenshot pointer |

## Out-of-Scope Follow-Ups (for a future spec)

- **Multi-ticker jobs** in a single `start()` call. The form would gain a "Ticker list" mode.
- **Aggregation across jobs** (hit rate of model decisions across all dates of a backtest). A read-only endpoint that takes a `job_id` and returns stats.
- **P&L simulation** based on the verdicts. A pure function on top of `verdicts.ts` (Historical Analysis Drawer spec).
- **Process-wide mutex** for multi-process safety. A PID file in `~/.tradingagents/data/background_runs/.lock`; checked on `start()` and acquired on `_load_existing_jobs()`.
- **Holiday calendar** for business-day cadence (NYSE closed dates). A small JSON file shipped with the package; `dates()` filters them out.
- **Per-iteration retry with backoff**. Right now, a failure means the date is logged and the loop moves on. A `retry` config could retry N times with exponential backoff before recording the error.
- **Notification on job completion**. A webhook / OS notification when a long-running job finishes.
- **CLI `run-past delete`** to remove a job's directory. Trivial — `rm -rf` of the directory.
- **CLI `run-past wait JOB_ID`** that blocks until the job finishes (polling the state file). Useful for scripted pipelines.
- **Per-iteration tags in the run list UI** — a badge in the Historical Analysis Drawer that highlights runs whose `background_run_id` matches the focused job. Visual only.
- **Graph view** of the iteration feed (a tiny sparkline of `duration_s` per iteration). Already have the data; trivial to add to the live feed card.
