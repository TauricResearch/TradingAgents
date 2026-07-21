---
id: 002
title: "Decide: backend stack, transport, and packaging"
labels: [wayfinder:grilling]
status: closed
assignee: JMAN730
blocked-by: [001]
---

## Question

Which backend framework, progress-stream transport, and packaging shape does the web UI use?

Sub-decisions:
- Framework: FastAPI + uvicorn vs Flask vs stdlib. (Recommended: FastAPI + uvicorn — async streaming support, typed, already the ecosystem default; `chainlit` banned per map Notes.)
- Transport for live progress: SSE vs WebSocket — take ticket 001 findings.
- Packaging: optional dependency group `web` in pyproject (mirroring `bedrock`), UI served from package data. (Recommended.)
- Entry point: `tradingagents web` subcommand on the existing typer app vs separate `tradingagents-web` script. (Recommended: subcommand — one CLI, discoverable.)
- Bind: 127.0.0.1 default, port flag. (Recommended.)

## Resolution

Decided via adversarial-verify workflow (3 skeptics, all verdicts "amended" — skeleton confirmed, corrections below). Full evidence in workflow `wf_bd527919-527` journal.

**Framework & transport**
- FastAPI + uvicorn. Marginal new wheels are exactly three (fastapi, starlette, uvicorn) — everything else already in the dependency closure. Flask (WSGI, no SSE) and starlette-alone (loses native SSE layer) rejected.
- SSE via **native FastAPI 0.135 SSE**, with the required idiom: the path operation is *itself a generator* declared with `response_class=EventSourceResponse`, yielding `fastapi.sse.ServerSentEvent(event=..., data=...)`. The sse-starlette-style "return EventSourceResponse(gen)" idiom silently produces a bare StreamingResponse — no event encoding, no 15 s keepalive, no Last-Event-ID (fastapi routing.py:966-972). sse-starlette rejected even as default fallback: it requires async generators.
- Stream `stream_mode=["updates","custom"]` (add `"messages"` for token streaming if wanted) as typed SSE events; `get_stream_writer()` for app-level progress.
- langgraph pin stays a floor at `>=0.4.8`; web path written against the 0.4.8 API surface ((mode, data) tuples only — no `version="v2"`, no `tasks`/`checkpoints` modes). Installed env is langgraph 1.2.9 anyway (no lock file). Bump to `>=1.1` only if node-lifecycle/checkpoint events become wanted.

**Packaging & entry point**
- New `[project.optional-dependencies] web = ["fastapi>=0.135", "uvicorn"]` extra, mirroring `bedrock`.
- Server code lives at `tradingagents/web/` — a top-level `web/` package would be silently dropped from wheels by `packages.find include = ["tradingagents*", "cli*"]` (pyproject.toml:52). `cli/web/` rejected (server ≠ terminal UI).
- Static UI as package data with recursive glob: `"tradingagents.web" = ["static/**/*"]` (existing `cli = ["static/*"]` pattern is single-level, won't pick up nested assets).
- Entry: `tradingagents web` subcommand on the existing typer app. All web imports (fastapi/uvicorn/server module) inside the command function body, wrapped in try/except ImportError with a `pip install "tradingagents[web]"` hint (repo pattern precedent: cli/main.py:1297-1298).
- Typer single→multi-command flip mitigation, **option (a) chosen**: add `@app.callback(invoke_without_command=True)` that runs analyze when `ctx.invoked_subcommand is None`, carrying the current top-level `--checkpoint`/`--clear-checkpoints` options. Preserves bare `tradingagents` (Dockerfile ENTRYPOINT, docker-compose quickstart, README:122/167) AND makes `tradingagents analyze` valid — fixing README:253-254, which documents a form that is broken today.

**Runtime, bind & security**
- Bind 127.0.0.1 default, `--port` flag, default port 8035. Exactly one uvicorn worker.
- Runs serialized in-process (max 1 active, lock/queue): TradingAgentsGraph is not concurrency-safe — `set_config` mutates module-global dataflows config, `propagate()` reassigns `self.graph`/mutates instance state, TradingMemoryLog does lockless read-modify-write (details in ticket 005).
- Web run path uses `graph.astream`. **Checkpoint-enabled runs must compile with `AsyncSqliteSaver`** (`langgraph.checkpoint.sqlite.aio`): the sync SqliteSaver hard-raises NotImplementedError from async checkpoint methods — guaranteed crash under astream. aiosqlite is already a transitive dep; zero new packages.
- `propagate()`'s sync non-graph phases (`_resolve_pending_entries` yfinance+reflection pre-work, `process_signal` post-work) must run via `anyio.to_thread`/executor or they block the event loop for minutes.
- Cancellation semantics: disconnect stops scheduling further nodes, but the in-flight sync node's LLM call finishes in an uninterruptible executor thread (still bills). Do not promise instant cancel in UI/docs.

Security hardening (mandatory, not optional): a localhost server with no auth is reachable from hostile websites via DNS rebinding, which would allow triggering paid LLM runs and reading results. Therefore: enforce a Host-header allowlist of {localhost, 127.0.0.1} (TrustedHostMiddleware or equivalent), accept only `application/json` bodies on state-changing endpoints, and add no CORS middleware so cross-origin preflights fail. A random session token remains optional extra hardening for the single-user localhost case.
