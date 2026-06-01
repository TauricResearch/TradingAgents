# TradingAgents Live Dashboard — Design

**Date:** 2026-06-01
**Status:** Draft, pending user review
**Author:** Brainstorming session output

## 1. Purpose

Add a web dashboard to the existing TradingAgents framework so a user can
monitor a watchlist of tickers while the multi-agent pipeline (analysts →
researchers → trader → risk → portfolio manager) runs. The dashboard
replaces the current terminal-only experience with a live, glanceable
surface that streams every agent event as it happens, and keeps a
replayable history of every past run.

The framework itself is untouched: `tradingagents/` continues to be a
pip-installable package, `main.py` and the CLI keep working exactly as
today, and the dashboard is a new sibling code path that imports the
same `TradingAgentsGraph`.

## 2. Goals & non-goals

### Goals

- Run multiple analyses in parallel from a single web UI.
- Stream every event in the LangGraph execution to the browser in real
  time.
- Persist every run and every event so the user can come back later and
  re-read yesterday's analysis.
- Show a live price tick for every watchlist ticker (YFinance, polled
  every 15s).
- One-command startup: `uvicorn web.server.app:app` and visit
  `http://localhost:8000`.
- Local, single-user. No login flow. No auth.

### Non-goals

- Multi-tenant auth, RBAC, or per-user isolation.
- Live trading / order execution. The framework's existing
  `propagate()` only produces a decision; we display it, we don't act on
  it.
- A general-purpose LLM chat UI. The dashboard is purpose-built for
  TradingAgents output.
- Replacing the CLI. The CLI keeps working for scripted / headless use.
- Mobile / responsive layout. Target is desktop (≥1280px wide).
- Replacing `~/.tradingagents/` memory log. The dashboard reads from it
  on demand but doesn't take ownership of the format.

## 3. Architecture overview

**One Python process.** FastAPI + uvicorn on port 8000 serves:

- HTTP API under `/api/*`
- WebSocket under `/ws/*`
- The built React app as static files under `/`

In dev, the React dev server runs separately on :5173 and proxies
`/api` and `/ws` to :8000. In production, Vite builds the React app
into `web/frontend/dist` and FastAPI mounts it as static files. No
CORS, no nginx, no second service to manage.

### File layout

```
TradingAgents/
  tradingagents/                 # existing package (unchanged)
  cli/                           # existing CLI (unchanged)
  main.py                        # existing demo (unchanged)
  web/                           # NEW
    server/
      __init__.py
      app.py                     # FastAPI app factory, routes, static mount
      events.py                  # WebSocket event types & protocol
      runner.py                  # wraps TradingAgentsGraph, emits events
      price_feed.py              # YFinance poller (15s)
      db.py                      # SQLite (sqlmodel), schema + queries
      settings.py                # env-var config
      tests/                     # pytest suite
    frontend/
      src/                       # React + Vite + TypeScript
        main.tsx
        App.tsx
        components/              # WatchlistRail, StageGrid, etc.
        hooks/                   # useRunStream, usePrices
        lib/                     # ws client, event types
        __tests__/               # vitest suite
      package.json
      vite.config.ts
      index.html
    README.md
  docs/superpowers/specs/2026-06-01-trading-dashboard-design.md
```

### Existing code changes (minimal)

One small change to `tradingagents/graph/trading_graph.py` is required:
add an optional `event_callback` parameter to `propagate()` (or a
module-level hook) so the runner can receive a typed event for each
LangGraph node. The signature stays backwards compatible — existing
callers that don't pass a callback behave exactly as today. The
change is ~20 lines and does not alter runtime behavior of any
existing code path.

## 4. Backend modules

### 4.1 `db.py` — SQLite + sqlmodel

- **Library:** `sqlmodel` (Pydantic + SQLAlchemy). Single file, ~150
  lines. No Alembic — schema is created at startup via
  `SQLModel.metadata.create_all()`.
- **Location:** `~/.tradingagents/dashboard.db` by default;
  `TRADINGAGENTS_DASHBOARD_DB` env var overrides.
- **Connection model:** one connection per request, returned via a
  FastAPI dependency. The price_feed and runner use their own
  short-lived connections (they aren't request-scoped).

**Schema:**

```python
class Watchlist(SQLModel, table=True):
    ticker: str = Field(primary_key=True)  # e.g. "NVDA"
    company_name: str
    exchange: str
    added_at: datetime
    last_run_id: Optional[int] = None
    last_decision: Optional[str] = None  # "BUY @ 260"
    last_decision_at: Optional[datetime] = None

class Run(SQLModel, table=True):
    id: Optional[int] = Field(primary_key=True)
    ticker: str  # FK conceptually, but no enforced constraint
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str  # queued | running | done | failed | cancelled
    cancel_requested: bool = False
    decision_action: Optional[str] = None
    decision_target: Optional[float] = None
    decision_rationale: Optional[str] = None
    decision_confidence: Optional[float] = None
    unpersisted: bool = False  # set if event write failed mid-run
    idempotency_key: str       # ticker + started_at day

class Event(SQLModel, table=True):
    id: Optional[int] = Field(primary_key=True)
    run_id: int
    ts: datetime
    type: str
    payload_json: str  # serialized data dict
```

**Queries:** `add_ticker`, `remove_ticker`, `list_watchlist`,
`get_run`, `list_runs(limit)`, `append_event`, `events_for_run(run_id, since_id=None)`,
`mark_run_done`, `mark_run_failed`, `request_cancellation`,
`reap_stale_runs(timeout)`.

### 4.2 `price_feed.py` — YFinance poller

- One `asyncio` task started in the FastAPI app lifespan.
- Every 15 seconds (configurable): calls
  `yf.download(tickers, period="1d", interval="1m", group_by="ticker")`
  in a single batched request and updates an in-memory
  `dict[str, PriceSnapshot]`.
- Each `PriceSnapshot`: `{price, prev_close, change_pct, sparkline: list[float] (last 30 minutes)}`.
- On success: emits a `price_update` event to all connected WS
  clients.
- On partial failure (some tickers fail): the failing ones keep their
  previous snapshot, get a `stale: true` flag, and the rest update
  normally.
- On total failure: logs, skips, retries next tick. Never raises.
- Started/stopped cleanly with the app lifespan so tests can
  short-circuit the real poller.

### 4.3 `runner.py` — analysis orchestrator

- Owns a single `asyncio.Semaphore(3)` and a FIFO
  `asyncio.Queue[RunJob]`.
- `enqueue(ticker) -> run_id`:
  1. Inserts a `Run` row with `status="queued"`,
     `idempotency_key=f"{ticker}:{today.isoformat()}"`.
  2. If a row with that idempotency key already exists and finished
     in the last hour, returns the existing `run_id` (idempotent
     re-trigger).
  3. Otherwise, enqueues the job and returns the new `run_id`.
- Queue worker loop (one task):
  1. `await semaphore.acquire()`.
  2. Build a `TradingAgentsGraph` from the user's `DEFAULT_CONFIG`
     (so the existing config mechanism keeps working).
  3. Wrap each LangGraph node invocation with an event emitter that
     calls `events.emit(...)` after each step.
  4. Run `propagate(ticker, today)` in
     `asyncio.get_event_loop().run_in_executor(...)` (it's blocking
     sync).
  5. Catch LLM 429 → exponential backoff with jitter, up to 3 retries.
  6. On any other exception → emit `run_failed`, mark the run row,
     release the semaphore, return.
  7. On normal completion → emit `run_finished`, mark the run row,
     update the watchlist's `last_decision*` columns, release the
     semaphore.
  8. Cancellation check between events: if `cancel_requested=True`,
     stop the graph via the LangGraph checkpointer, emit
     `run_failed {reason: "cancelled"}`.

### 4.4 `events.py` — protocol

- All event types are constants in a single Python Enum. The
  matching TypeScript mirror lives in
  `web/frontend/src/lib/events.ts` and is hand-synced (a tiny
  test in `test_events.py` and `events-protocol.test.ts` enforces
  parity).
- Wire format:

  ```json
  {
    "v": 1,
    "type": "analyst_thinking",
    "ts": "2026-06-01T14:32:18.123Z",
    "run_id": 42,
    "data": { "stage": "market", "message": "..." }
  }
  ```

- Event types (initial set):
  - `run_started`, `run_finished`, `run_failed`
  - `analyst_started`, `analyst_thinking`, `analyst_completed`
  - `tool_call`, `tool_result`, `tool_call_warning`
  - `debate_message`
  - `risk_message`
  - `decision`
  - `price_update`
  - `server_notice` (cancellation, restart, etc.)
- `emit(event)` does two things: (1) writes a row to the `event`
  table inside a try/except, (2) pushes the event to all WS
  subscribers of that `run_id`. The two are decoupled so a DB
  failure doesn't drop a live update.

### 4.5 `app.py` — FastAPI surface

**Routes:**

- `GET    /api/health` — `{status: "ok", uptime_s, watchlist_size, runs_in_queue, runs_running}`
- `GET    /api/watchlist` — list with last-decision chip
- `POST   /api/watchlist` — `{ticker, company_name?, exchange?}` → 201
  / 409 if already present
- `DELETE /api/watchlist/{ticker}` — 204
- `GET    /api/tickers/search?q=` — YFinance symbol search, max 8
- `GET    /api/prices` — current in-memory snapshot of all watchlist
  prices
- `POST   /api/runs` — `{ticker}` → `{run_id}` (idempotent per day)
- `GET    /api/runs?limit=20` — list past runs
- `GET    /api/runs/{id}` — full run + events
- `POST   /api/runs/{id}/cancel` — flips the cancellation flag
- `WS     /ws/runs/{run_id}?since={event_id}` — replays events with
  `id > since` then live-forwards. One WS per run; the same client
  may also subscribe to `price_update` events by including
  `?topics=prices` in the URL.

**Static mount** (after all API routes, so they take precedence):

```python
app.mount("/", StaticFiles(directory="web/frontend/dist", html=True))
```

In dev, `vite.config.ts` proxies `/api` and `/ws` to
`http://localhost:8000`. The dev server's URL is
`http://localhost:5173`.

**Lifespan:** starts `price_feed.start()` and `runner.start()` on
startup, stops them on shutdown. On startup, also calls
`db.reap_stale_runs(timeout=600)` to mark any `status=running` runs
as `failed {reason: "server_restart"}`.

## 5. Frontend components

**Stack:** Vite, React 18, TypeScript, Tailwind, shadcn/ui
(Radix-based headless primitives), TanStack Query for server state,
Zustand for ephemeral UI state, `ws` library wrapped in
`hooks/useRunStream.ts`. No router — single screen.

**Layout** (master/detail split):

```
┌─────────────────────────────────────────────────────────────┐
│ Header  TradingAgents · 3 running · 4 idle                  │
├──────────────┬──────────────────────────────────────────────┤
│  Watchlist   │  TickerHeader: NVDA · $112.40 · +1.36%       │
│  - NVDA  ●   │  ┌─────────┬─────────┬──────────┬────────┐   │
│  - AAPL  ◐   │  │ Market  │Sentiment│ News     │Fundmntl│   │
│  - TSLA  ✓   │  │  ✓ done │ ✓ done  │ ✓ done   │ ⏳ run │   │
│  - MSFT  ⏸   │  ├─────────┴─────────┴──────────┴────────┤   │
│  - + add     │  │ Live event stream (typed bubbles)      │   │
│              │  │ • 14:32  Bull: NVDA beat expect…       │   │
│              │  │ • 14:33  Bear: Multiple expansion…     │   │
│              │  │ • 14:35  Trader: BUY @ 260              │   │
│              │  └────────────────────────────────────────┘   │
└──────────────┴──────────────────────────────────────────────┘
```

**Components:**

- `WatchlistRail` — left pane. Renders `TickerRow` per watchlist
  entry. Each row: ticker, last price, change %, status dot
  (idle/queued/running/done/errored), 30-tick sparkline (~10px svg
  path). Click → set `focusedTicker`. `+ Add` opens a `cmdk`
  command palette with a YFinance-backed typeahead.
- `TickerHeader` — name, price, change %, day-range bar, "Run
  analysis" button (disabled if already running), cancel button
  (visible only while running).
- `StageGrid` — one card per pipeline stage (Market, Sentiment,
  News, Fundamentals, Research, Risk, Trader). Each card: name,
  status icon, last activity timestamp, short summary line. Cards
  animate in as stages complete.
- `LiveEventStream` — auto-scrolling list of typed event bubbles.
  Each type gets a small icon and a color: blue for analyst,
  amber for debate, green/red for decision, gray for tool calls.
  Auto-scroll pauses if the user scrolls up; a "Jump to live" pill
  appears at the bottom.
- `DecisionPanel` — appears when a `decision` event arrives. Shows
  action (BUY/SELL/HOLD), ticker, target price, confidence as a
  progress bar, rationale (markdown rendered via `react-markdown`).
- `RunHistoryDrawer` — slide-in drawer from the right, shows past
  runs grouped by ticker. Click a row → opens that run in read-only
  mode (no live stream, just the persisted events).

**State:**

- **TanStack Query:** `["watchlist"]`, `["runs", "list"]`,
  `["run", id]`, `["prices"]`, `["tickers", "search", q]`.
  Cache is mutated directly from WS events (no refetch storm).
- **Zustand:** `focusedTicker`, `connectedRunId`, `eventBuffer` (live
  events for the focused run; cleared on focus change).
- **No router.** Focus change is a state update.

**WebSocket lifecycle** (`hooks/useRunStream.ts`):
- Opens on focus change or new `run_id` arriving.
- Auto-reconnect with exponential backoff (1s → 30s cap).
- On reconnect, sends `?since={last_seen_event_id}` so the server
  replays only the gap.
- Closes on unmount or focus change.
- Errors surface as a small "reconnecting…" pill; no toast spam.

## 6. Data flow

A complete run, end-to-end:

- **T+0s**  User clicks "Run analysis" on NVDA.
  - React: `POST /api/runs {ticker: "NVDA"}` via TanStack Query
    mutation.
  - FastAPI: inserts `Run` row (`status="queued"`), calls
    `runner.enqueue()`, returns `{run_id}` immediately.
  - React: opens `WS /ws/runs/{run_id}`.
- **T+0.1s**  WS connects.
  - Server: replays persisted events for that run (none yet),
    then switches to live mode.
  - Client: appends replayed events to the buffer.
- **T+0.2s**  Queue worker picks up the job.
  - Server: emits `run_started` → broadcast + persisted.
  - React: StageGrid shows "Market Analyst: running", status dot
    on the rail → "running".
- **T+1–30s**  Per-stage events stream in.
  - For each LangGraph node, the patched callback fires:
    `analyst_started` → `analyst_thinking` (multiple) →
    `tool_call` → `tool_result` → `analyst_completed`.
  - Each event → write to `event` table + push to subscribers.
  - React: StageGrid fills in; LiveEventStream appends typed
    bubbles.
  - During debates, Bull/Bear alternate and each turn emits
    `debate_message {side, round, text}`. React renders these in
    alternating columns.
- **T+30–90s**  Trader + risk phases. Same pattern. Trader
  emits `decision {action, ticker, qty, target_price, rationale_markdown, confidence}`.
  React: DecisionPanel slides in.
- **T+90s**  Run complete.
  - Server: emits `run_finished`, updates `Run.status = "done"`,
    writes the decision to the run row, updates the watchlist's
    `last_decision*` columns.
  - WS stays open; client keeps the replay buffer.
  - TanStack Query invalidates `["runs", "list"]` and
    `["watchlist"]`.
  - Queue worker pulls the next job (if any).

**Cancellation:** `POST /api/runs/{id}/cancel` flips the flag.
Runner checks between events, aborts via the checkpointer, emits
`run_failed {reason: "cancelled"}`.

**Price feed** runs independently. Every 15s the poller updates
the in-memory dict and broadcasts `price_update` to all
connected clients. The TanStack Query cache for `["prices"]` is
updated directly from the WS message.

**First paint:** on app load, `GET /api/prices` returns the
in-memory snapshot so the rail shows current prices before the
first poll fires.

**Ticker typeahead:** `GET /api/tickers/search?q=NVI` calls
YFinance's symbol search, returns up to 8 matches. Used only by
the `+ Add` command palette.

## 7. Error handling

| Failure | Detection | Response |
|---|---|---|
| WS disconnects | `try/except` on the WS handler, `finally` removes subscriber | Server keeps running. Client auto-reconnects with backoff; server replays gap from `event` table using `?since=`. Visual cue: small "reconnecting…" pill. |
| LLM 429 (rate limit) | Caught in runner | Sleep with jitter, retry up to 3×. Emit `tool_call_warning` so the user sees "OpenRouter 429 — retrying" in the stream. Final failure → `run_failed`. |
| LLM other error (auth, timeout) | Caught in runner | Emit `run_failed {reason, exception_class, message}`. UI shows a red bar on the DecisionPanel with the exception class and a "View logs" link. |
| Per-stage analyst error | Caught per-node | Stage marked `errored` in the event log. Pipeline continues with partial input. Final decision is flagged `degraded` in the DB and shown with a warning in the UI. |
| YFinance partial failure | yfinance returns empty for some tickers | Those tickers keep their last snapshot with `stale: true`; rail shows dimmed price + "stale" badge. Others update normally. |
| YFinance total failure | yfinance raises | Log and skip. Next poll retries. WS clients keep last-known values. |
| TradingAgents framework error | Caught at runner boundary | `run_failed` emitted, run row updated. Other watchlist jobs unaffected. |
| SQLite write failure | Caught in `db.append_event` | Retry once, then `run.unpersisted = True`. WS still gets the event in-memory; a future reconciliation pass replays missed events. |
| Duplicate ticker add | Unique constraint on `watchlist.ticker` | API returns 409 with `{error: "already_in_watchlist"}`. UI shows "Already in watchlist" in the command palette. |
| Invalid ticker (no data, no events in 60s) | Runner timeout | `run_failed {reason: "no_data"}`. |
| Server crash / restart mid-run | Stale `status=running` row | On startup, `db.reap_stale_runs(timeout=600)` marks them `failed {reason: "server_restart"}`. Clients see a one-time `server_notice` on reconnect. |
| Cancellation | `cancel_requested` flag | Runner checks between events; aborts via checkpointer; emits `run_failed {reason: "cancelled"}`; frees semaphore slot. |
| Empty search query / overlong ticker | API validation | 400 with field-level error. |

**Philosophy:** never crash the dashboard, never lose persisted data,
always show a useful status. Errors are events, not exceptions, as far
as the UI is concerned.

## 8. Testing strategy

**Principle: test the boundaries, not the framework.** The
TradingAgents library has its own tests; we don't replicate them. We
test the dashboard's glue: event protocol, persistence, WS plumbing,
React state management.

**Backend (pytest, in `web/server/tests/`)**

- `test_db.py` — schema creation, watchlist CRUD, run insert + update,
  event append + ordered read, idempotency key collision.
- `test_events.py` — protocol shape (every event has `v`, `type`,
  `ts`, `run_id`, `data`); Python constants match the TS mirror.
- `test_price_feed.py` — YFinance mocked; on 1st poll snapshot
  updates, on partial failure stale flag set, on total failure no
  crash, next poll recovers.
- `test_runner.py` — fake `TradingAgentsGraph` that emits scripted
  events. Cases: enqueue → run_started → all events → run_finished;
  semaphore blocks 4th concurrent job, 4th runs after first finishes;
  cancel mid-run → `run_failed {reason: "cancelled"}`; LLM 429 →
  retry then succeed; 3 failures → `run_failed`; DB write failure
  mid-run → run marked unpersisted but WS still gets event.
- `test_ws.py` — client connects to `/ws/runs/{id}`, receives
  replayed events (run inserted before connect) then live events;
  disconnect + reconnect with `?since=` replays only the gap;
  multiple subscribers all get every event.
- `test_app.py` — FastAPI TestClient. Routes return correct shapes;
  static mount works after `npm run build`; CORS not needed (same
  origin).

**Frontend (vitest + @testing-library/react, in `web/frontend/src/__tests__/`)**

- `WatchlistRail.test.tsx` — renders rows from query, click fires
  onFocus, +Add opens palette, duplicate-add shows error toast.
- `StageGrid.test.tsx` — renders one card per stage, status icon
  reflects event type, updates when stream emits
  `analyst_completed`.
- `LiveEventStream.test.tsx` — bubbles appear in order, auto-scroll
  toggles on user scroll, decision bubble gets green/red styling.
- `useRunStream.test.ts` — mock `WebSocket`; on message pushes to
  event buffer, on disconnect schedules reconnect, on reconnect with
  `?since` filters out already-seen events.
- `events-protocol.test.ts` — every event constant has a matching
  TS type and serializer; mismatch fails the build.
- `DecisionPanel.test.tsx` — markdown renders, confidence is a
  progress bar, degraded flag shows warning.

**E2E (light)**

- `e2e/full_run.spec.ts` (Playwright) — single ticker (NVDA), mock
  LLM, click Run, watch all stages complete, assert decision
  appears, assert run shows in history. Slow test, runs in CI on
  demand.
- Manual checklist in `web/README.md`:
  - [ ] Add 3 tickers, kick off all at once, see queueing
  - [ ] Cancel a running analysis, see clean error
  - [ ] Restart server mid-run, verify WS reconnects and replays the
        gap
  - [ ] YFinance blocked → see stale badge, server keeps running
  - [ ] Open in 2 browser tabs → both get every event
  - [ ] Reload mid-run → see persisted events from DB

**Coverage target:** ~70% on the new `web/server/` code, ~60% on
the new `web/frontend/src/`. We don't gate on coverage, but CI fails
on any test that previously passed.

**Test infrastructure:**

- `web/server/tests/fixtures/` — fake LLM responses (canned JSON per
  analyst type), fake YFinance, in-memory SQLite.
- `web/frontend/src/__tests__/mocks/` — mock WS server (small Node
  helper that scripts events).
- `pyproject.toml` adds `[tool.pytest.ini_options]` with
  `testpaths = ["web/server/tests"]`.
- Frontend `package.json` adds `"test": "vitest run"`,
  `"test:watch": "vitest"`.

## 9. Configuration

The dashboard reads the same env vars the framework already uses
(`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GOOGLE_API_KEY`,
`ALPHA_VANTAGE_API_KEY`, `TRADINGAGENTS_*` overrides in
`default_config.py`). New env vars:

- `TRADINGAGENTS_DASHBOARD_DB` — SQLite path (default
  `~/.tradingagents/dashboard.db`).
- `TRADINGAGENTS_DASHBOARD_PORT` — uvicorn port (default 8000).
- `TRADINGAGENTS_DASHBOARD_MAX_CONCURRENT` — semaphore size (default
  3).
- `TRADINGAGENTS_DASHBOARD_PRICE_POLL_S` — YFinance poll interval
  (default 15).
- `TRADINGAGENTS_DASHBOARD_LOG_LEVEL` — default `INFO`.

## 10. Acceptance criteria

The design is "done" when:

1. `uvicorn web.server.app:app` starts the dashboard on :8000.
2. `npm run dev` in `web/frontend/` starts the React app on :5173,
   proxying to :8000.
3. `npm run build` outputs a static bundle that, when served by the
   same uvicorn process, renders the dashboard identically to the
   dev build.
4. The user can add a ticker, kick off a run, and watch every
   analyst / debate / risk event stream into the UI in real time.
5. The user can add 3 tickers at once; the first 3 run in parallel,
   the 4th queues.
6. Reloading the browser mid-run does not lose any events (the
   server replays from the `event` table).
7. Reloading the browser after a run lets the user re-open and
   re-read the full analysis.
8. The YFinance poller updates the rail's price + sparkline every
   15s.
9. Cancelling a run produces a clean `run_failed` event and frees
   the semaphore slot.
10. Killing and restarting the server mid-run marks the in-flight
    run as `failed {reason: "server_restart"}` on next startup and
    emits a `server_notice` to reconnecting clients.
11. The pytest suite passes; the vitest suite passes; the E2E
    Playwright spec passes.
12. Existing `main.py` and `cli/main.py` continue to work
    unchanged.

## 11. Open questions / future work

- **Authentication.** Single-user is fine for now. If exposed on a
  LAN later, add a shared-secret header check.
- **Docker compose.** A `docker-compose.yml` with the FastAPI
  process + a build of the React app is a likely follow-up but
  out of scope for the first cut.
- **Mobile / responsive.** The dashboard targets desktop
  (≥1280px). A future pass could collapse the rail into a
  hamburger menu.
- **Ticker-level config.** Today every ticker uses the global
  `DEFAULT_CONFIG`. A future pass could let the user override
  `max_debate_rounds` per ticker.
- **Charting.** The sparkline is enough for v1. Adding a real
  intraday chart (TradingView lightweight-charts) is a natural
  follow-up.
- **Backtesting.** A "rerun this analysis with a different date"
  button is a one-day add once the run replay UI is solid.
