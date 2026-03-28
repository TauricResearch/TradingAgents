# Current Milestone

Storage finalisation + run history UX. Branch `claude/wizardly-poitras` (PR pending).
All storage, event, checkpoint, and phase re-run logic is now documented in ADR 018.

# Recent Progress

- **feat/fe-max-tickers-load-run** (merged base):
  - `max_auto_tickers` config + macro synthesis prompt injection + frontend input
  - Run persistence: `run_meta.json` + `run_events.jsonl` per flow_id
  - Phase subgraphs (debate_graph, risk_graph) in LangGraphEngine
  - `POST /api/run/rerun-node` endpoint + frontend Re-run buttons on graph nodes
  - Run History popover in UI

- **claude/wizardly-poitras** (this PR — storage finalisation):
  - **flow_id layout** replaces run_id namespacing: `reports/daily/{date}/{flow_id}/`
  - **Startup hydration**: `hydrate_runs_from_disk()` rebuilds runs dict from disk on restart
  - **WebSocket lazy-loading**: events loaded from disk on first WS connect (fixes blank Run History)
  - **Orphaned run detection**: runs stuck in "running" with disk events → marked "failed"
  - **Analysts checkpoint fix**: `any()` instead of `all()` — Social Analyst is optional
  - **flow_id checkpoint lookup**: re-run passes original flow_id to store so checkpoints resolve correctly
  - **Selective event filtering**: phase re-run preserves scan + other tickers; only clears stale nodes for the re-run scope
  - **ADR 018**: definitive documentation of storage, events, checkpoints, MongoDB vs local

- **PR#108 merged**: Per-tier LLM fallback for 404/policy errors (ADR 017)
- **PR#107 merged**: `save_holding_review` per-ticker fix; RunLogger threading.local → contextvars
- **PR#106 merged**: MongoDB report store, RunLogger observability, reflexion memory
- **codex/global-search-graph-main-squash** (scanner gatekeeper foundation, local):
  - Added live-tested `yfinance` gatekeeper universe query for US-listed liquid profitable mid-cap+ names
  - Added live-tested Finviz gap-subset path using the bounded gatekeeper-plus-gap filter
  - Narrowed Finviz usage to the gap/event layer instead of the full market-universe layer
  - Next step is graph wiring so downstream candidate selection is hard-filtered by the gatekeeper universe

# In Progress

- claude/wizardly-poitras PR: storage finalisation + run history UX
- codex/global-search-graph-main-squash: wire gatekeeper universe into scanner graph and deterministic ranking

# Active Blockers

- None

# Key Architectural Decisions Active

| ADR | Topic | Status |
|-----|-------|--------|
| 013 | WebSocket streaming (extended by 018) | accepted |
| 015 | MongoDB/run-id namespacing | superseded by 018 (flow_id replaces run_id) |
| 016 | PR#106 review findings | accepted |
| 017 | LLM policy fallback | accepted |
| 018 | Storage layout, events, checkpoints, MongoDB vs local | **accepted — canonical reference** |
