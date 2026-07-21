# Map: TradingAgents Web UI

Label: `wayfinder:map`
Tracker: local-markdown. Tickets live in `.wayfinder/tickets/NNN-slug.md`.
Conventions: frontmatter `status: open|closed`, `assignee:` (claim = assignee set), `blocked-by: [ids]`. Frontier = open + unassigned + all blockers closed. Resolution recorded in ticket under `## Resolution`, then status closed and gist appended to Decisions-so-far here.

## Destination

A local, single-user web UI that fully replaces the CLI flow: configure a run (ticker, date, asset type, analysts, models/provider), watch live multi-agent progress while it executes, and read/browse the final reports. Shipped inside this repo as an optional install extra with its own entry point. Destination reached when every decision needed to plan the build is made — spec ready to execute.

## Notes

- Domain: multi-agent LLM trading framework (LangGraph). Core API: `TradingAgentsGraph.propagate(ticker, date, asset_type)`; `debug=True` streams chunks via `graph.stream` (tradingagents/graph/trading_graph.py:443). CLI (`cli/main.py`, typer + Rich) mirrors progress via `MessageBuffer.report_sections` and writes reports to results dir.
- User delegated decisions ("grill yourself, do whatever you think"): grilling-type tickets may be resolved AFK by the driving agent using its recommended answer; still one ticket per session. Prototype ticket stays HITL — user reacts to the artifact.
- `chainlit` was removed for CVE-2026-22218 — do not reintroduce.
- Skills to consult per ticket type: /grilling, /domain-modeling, /prototype, /research.

## Decisions so far

<!-- one line per closed ticket -->

- [Research: streaming LangGraph runs to a browser](tickets/001-research-streaming-langgraph-to-browser.md) — SSE (not WebSockets) via FastAPI `EventSourceResponse`; stream `stream_mode=["updates","custom"]` as typed SSE events; prefer `graph.astream` for clean disconnect cancellation. Full findings on branch `research/web-streaming`.
- [Decide: backend stack, transport, and packaging](tickets/002-backend-stack.md) — FastAPI+uvicorn via `[web]` extra; native FastAPI SSE (generator-endpoint idiom, NOT constructor-return); server at `tradingagents/web/`; `tradingagents web` subcommand with lazy imports + `@app.callback` compat for bare CLI; 127.0.0.1:8035, single worker, serialized runs, astream + AsyncSqliteSaver, mandatory Host-allowlist hardening.
- [Prototype: web UI look](tickets/003-prototype-ui-look.md) — 3 variants built ([artifact](https://claude.ai/code/artifact/b2abcc02-a706-4f18-8a37-600c00586a73), branch `prototype/web-ui-look`); verdict: Ops Workspace sidebar shell as base, with Analyst Desk's article-style report reading view and Terminal Deck's collapsible tool-call ticker. User reaction still welcome — override lands in ticket 004.
- [Decide: frontend technology](tickets/004-frontend-tech.md) — vanilla ES modules, zero build, no framework; two vendored leaf libs (marked + DOMPurify, GFM tables prompt-mandated); strict CSP header incl. `img-src 'self' data:` against prompt-injection image-beacon exfiltration; MIME/cache/hash-routing hardening; SSE replay contract with Last-Event-ID + terminal-event close.
- [Decide: run execution and concurrency model](tickets/005-run-execution-model.md) — decoupled asyncio run-task + SSE log-tailer; single active run, 409, no queue; states running/done/failed/cancelled + draining; cancel is immediate but orphans executor threads → per-run ThreadPoolExecutor with drain-before-release; slim server-side event projection (raw updates are MBs); faithful propagate() scaffolding checklist (async checkpointer, stream_mode override, store_decision/clear_checkpoint post-phases, incremental report writes).
- [Decide: run history and results persistence](tickets/006-run-history-persistence.md) — one shared history in the existing `results_dir` tree; web runs add a `run.json` manifest per run (decision/models/duration are otherwise unrecoverable); CLI-era runs degrade gracefully; directory scan + mtime cache, no sqlite; reports served as raw markdown JSON, debug artifacts unexposed.
- [Decide: config and API-key handling](tickets/007-config-and-keys.md) — key presence booleans only, no key input or echo anywhere (incl. backend_url treated secret-adjacent, write-only); pre-run key validation replaces the CLI prompt; per-run form config over DEFAULT_CONFIG; last-used settings in `~/.tradingagents/web_settings.json`; GET /api/config is an explicit non-secret whitelist.
- [Decide: web-layer testing strategy](tickets/008-web-testing.md) — same pytest suite (`tests/test_web_*.py`), anyio plugin (zero new deps); injectable fake run engine as the test seam; SSE/API contract tests via TestClient; mandatory security regression tests (CSP exact, Host reject, key-echo, config whitelist); no browser automation in v1.
- [Decide: how the web UI ships in Docker](tickets/009-docker-shipping.md) — one image with `[web]` installed by default; `tradingagents-web` compose service (`--host 0.0.0.0` in-container, host publish loopback-only `127.0.0.1:8035:8035`); Host-allowlist matches hostname port-agnostically; shared data volume = shared history; `/api/health` endpoint added; existing CLI services untouched.
- [Task: assemble the implementation spec](tickets/010-assemble-spec.md) — **destination reached**: `docs/web-ui-spec.md` consolidates all decisions with an ordered 9-step implementation plan and traceability links. Map complete; no open tickets remain.

## Not yet specified

(none — the frontier reached the destination)

## Out of scope

- Portfolio dashboards, cross-ticker comparison, backtesting UI (the "Dashboard+" option was explicitly not chosen).
- Multi-user auth, remote deployment hardening — destination is local single-user; localhost-only binding is the assumption.
- Live price charts and token-level streaming — deferred as v2 candidates, recorded in the spec's non-goals section.
