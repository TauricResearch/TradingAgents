# Current Milestone

Structured-contract rollout and summary-bypass validation. Branch `codex/structured-contracts-plan`.
The active objective is to remove hallucination-prone prose handoffs, preserve explicit contracts between nodes, and validate each fix with terminal-first live checks.

# Recent Progress

- `codex/structured-contracts-plan`:
  - Removed `Research Packet Summary` from the main analyst-to-researcher graph path in [setup.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/graph/setup.py)
  - Preserved analyst-to-downstream contracts by switching downstream packet consumers to deterministic packet assembly in [summary_context.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/utils/summary_context.py)
  - Kept `research_packet_summary` as a derived artifact only, via [context_summaries.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/managers/context_summaries.py)
  - Hardened market/news/social and downstream LLM nodes with timeout guards and bounded fallback behavior
  - Added runner-side validation for:
    - summary bypass before `Bull Researcher`
    - analyst structured contract presence
    - market checkpoint validation
    - stall detection / stop-on-stall
  - Live-validated the direct graph path for the news branch:
    - `Instrument Preflight -> News Analyst -> Msg Clear News -> News Fact Checker -> Bull Researcher`
    - confirmed `Research Packet Summary` does not appear in between on the tested path
  - Prompt/context probe for `JPM` verified:
    - ticker-filtered scanner context is attached to `News Analyst`
    - `News Fact Checker` receives structured payload
    - `Bull Researcher` receives deterministic packet content with scanner context and market structured contract
    - legacy summary prose is not reintroduced into downstream packet assembly

- `codex/auto-run-lifecycle-fix`:
  - Reworked `run_auto()` Phase 2 concurrency to use structured `TaskGroup` ownership for producer and per-ticker pipelines
  - Fixed the root auto-run logger lifecycle so cleanup now happens in `finally`
  - Added regression coverage for failure-path logger finalization and async-generator close while a ticker pipeline is in flight
  - Documented the architectural rule that child ticker work must not outlive the parent auto run

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

# Done In Current Rollout

- News-node structured output and fact-check path hardened
- Market-node structured contract persisted and validated
- Summary generator removed from the canonical analyst-to-researcher path
- Deterministic research packet now used downstream instead of legacy summary preference
- Terminal live-run helper and node-by-node testing guide expanded for this rollout
- `llm_guard.py` consolidated: `invoke_with_timeout`, `bind_max_tokens_if_supported`, `truncate_text` used by all downstream nodes
- `market_report_structured` canonical contract emitted by market analyst (status: completed/aborted/timeout_fallback/empty)
- All downstream nodes (bull/bear researchers, research manager, trader, risk debaters, risk synthesis, portfolio manager) hardened with `invoke_with_timeout` and deterministic fallback reports
- Scanner context packet exception handler split: each commodity/FX/calendar tool invocation is individually guarded, preserving partial data
- Path traversal fix in `_load_injected_market_report`: resolved paths validated against allowed directories
- `InvestDebateState` TypedDict aligned: `current_bull_summary`/`current_bear_summary` fields formalized
- Dead code marked for removal: `create_research_packet_summary`, `create_investment_debate_summary`

# Left In Current Rollout

- Continue node-by-node hardening for the remaining downstream runtime path until a full pipeline run completes cleanly through final report generation
- Fix the API-backed run/event wrapper behavior that can stall or fail to surface analyst node progress even when direct graph execution advances
- Execute the live-run recovery handoff in [022 Live Run Issue Handoff](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/022-live-run-issue-handoff.md)
- Harden scanner-context enrichment so context packets remain fully populated when one upstream vendor fails
- Perform final cleanup refactor on [langgraph_engine.py](/Users/Ahmet/Repo/TradingAgents/agent_os/backend/services/langgraph_engine.py):
  - remove unused helpers / dead branches
  - extract event mapping, pipeline runner, portfolio runner, and scan-state helpers into smaller modules
  - keep behavior unchanged while tightening regression coverage

# In Progress

- codex/structured-contracts-plan: continue post-news structured-contract rollout from market node downward using terminal runner validation and direct graph probes
- codex/unify-run-id-ulid: remove remaining legacy flow-id references from docs and ancillary code
- codex/global-search-graph-main-squash: wire gatekeeper universe into scanner graph and deterministic ranking

# Active Blockers

- API-backed pipeline runs can remain opaque at the event layer even when direct LangGraph execution progresses; this slows live validation and needs cleanup in the backend orchestration layer
- Handoff for that blocker is now captured in [022 Live Run Issue Handoff](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/022-live-run-issue-handoff.md)

# Key Architectural Decisions Active

| ADR | Topic | Status |
|-----|-------|--------|
| 013 | WebSocket streaming (extended by 018) | accepted |
| 015 | MongoDB/run-id namespacing | superseded |
| 016 | PR#106 review findings | accepted |
| 017 | LLM policy fallback | accepted |
| 018 | Storage layout, events, checkpoints, MongoDB vs local | accepted but partially outdated after run-id unification |
| 021 | Auto-run task lifecycle must be structured | accepted |
