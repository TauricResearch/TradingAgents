# Current Milestone

Run-id unification + run history UX. Branch `codex/unify-run-id-ulid`.
The system now uses a single canonical ULID `run_id` across runtime and storage.

# Recent Progress

- `codex/scan-fallback-duplication-cleanup` (current docs refresh):
  - Added a code-derived graph execution reference covering scanner, per-ticker pipeline, portfolio, and auto orchestration
  - Corrected stale docs that still described parallel analysts and outdated scanner topology
  - Linked overview docs to the new runtime reference so graph/tool behavior is documented in one place

- **feat/fe-max-tickers-load-run** (merged base):
  - `max_auto_tickers` config + macro synthesis prompt injection + frontend input
  - Run persistence: `run_meta.json` + `run_events.jsonl`
  - Phase subgraphs (debate_graph, risk_graph) in LangGraphEngine
  - `POST /api/run/rerun-node` endpoint + frontend Re-run buttons on graph nodes
  - Run History popover in UI

- **codex/unify-run-id-ulid** (current work):
  - **Single canonical id**: one process id is now one ULID `run_id`
  - **Unified storage layout**: `reports/daily/{date}/{run_id}/`
  - **Strict writes**: report-store writes require `run_id`; no legacy flat-write path remains
  - **Auto subphases unified**: scan, per-ticker pipeline, portfolio, and re-runs stay inside the same `run_id`
  - **Startup hydration**: persisted `running` runs normalize to `failed` after restart
  - **WebSocket lazy-loading**: events load from disk for completed/failed historical runs
  - **Selective event filtering**: phase re-run preserves scan + other tickers; only clears stale nodes for the re-run scope

- **PR#108 merged**: Per-tier LLM fallback for 404/policy errors (ADR 017)
- **PR#107 merged**: `save_holding_review` per-ticker fix; RunLogger threading.local → contextvars
- **PR#106 merged**: MongoDB report store, RunLogger observability, reflexion memory
- **codex/global-search-graph-main-squash** (scanner gatekeeper foundation, local):
  - Added live-tested `yfinance` gatekeeper universe query for US-listed liquid profitable mid-cap+ names
  - Added live-tested Finviz gap-subset path using the bounded gatekeeper-plus-gap filter
  - Narrowed Finviz usage to the gap/event layer instead of the full market-universe layer
  - Added graph wiring: dedicated gatekeeper scanner node, gatekeeper-aware drift context, and deterministic ranking that excludes names outside the gatekeeper universe

# In Progress

- codex/unify-run-id-ulid: remove remaining legacy flow-id references from docs and ancillary code
- codex/global-search-graph-main-squash: wire gatekeeper universe into scanner graph and deterministic ranking

# Active Blockers

- None

# Key Architectural Decisions Active

| ADR | Topic | Status |
|-----|-------|--------|
| 013 | WebSocket streaming (extended by 018) | accepted |
| 015 | MongoDB/run-id namespacing | superseded |
| 016 | PR#106 review findings | accepted |
| 017 | LLM policy fallback | accepted |
| 018 | Storage layout, events, checkpoints, MongoDB vs local | accepted but partially outdated after run-id unification |
