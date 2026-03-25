# Current Milestone

Smart Money Scanner added to scanner pipeline (Phase 1b). MongoDB report store + run-ID namespacing + reflexion memory added. PR#106 review findings addressed (ADR 016). 18 agent factories. All tests passing (886 passed, 14 skipped).

# Recent Progress

- **PR#106 review fixes (ADR 016)**:
  - Fix 1: `save_holding_review` iteration — was passing `portfolio_id` as ticker; now iterates per ticker
  - Fix 2: `contextvars.ContextVar` replaces `threading.local` for RunLogger — async-safe
  - Fix 3: `list_pm_decisions` — added `{"_id": 0}` projection to exclude non-serializable ObjectId
  - Fix 4: `ReflexionMemory.created_at` — native `datetime` for MongoDB, ISO string for local JSON fallback
  - Fix 5: `write/read_latest_pointer` — accepts `base_dir` parameter; `ReportStore` passes its `_base_dir`
  - Fix 6: `RunLogger.callback` — wired into all 3 `astream_events()` calls (scan, pipeline, portfolio)
  - Fix 7: `MongoReportStore.__init__` — calls `ensure_indexes()` automatically
  - `docs/agent/decisions/016-pr106-review-findings.md` — full writeup of all 13 findings and resolutions
  - Tests: 14 new tests covering all 7 fixes
- **MongoDB Report Store + Run-ID + Reflexion (current branch)**:
  - `tradingagents/report_paths.py` — All path helpers accept optional `run_id` for run-scoped directories; `latest.json` pointer mechanism
  - `tradingagents/portfolio/report_store.py` — `ReportStore` supports `run_id` + `latest.json` pointer for read resolution
  - `tradingagents/portfolio/mongo_report_store.py` — MongoDB-backed report store (same interface as filesystem)
  - `tradingagents/portfolio/store_factory.py` — Factory returns MongoDB or filesystem store based on config
  - `tradingagents/memory/reflexion.py` — Reflexion memory: store decisions, record outcomes, build context for agent prompts
  - `agent_os/backend/services/langgraph_engine.py` — Uses store factory + run_id for all run methods; fixed run_portfolio directory iteration for run-scoped layouts
  - `tradingagents/default_config.py` — Added `mongo_uri` and `mongo_db` config keys
  - `pyproject.toml` — Added `pymongo>=4.12.1` dependency
  - Tests: 56 new tests (report_paths, report_store run_id, mongo store, reflexion, factory)
  - `docs/agent/decisions/015-mongodb-report-store-reflexion.md` — ADR documenting all design decisions
- **Smart Money Scanner**: 4th scanner node added to macro pipeline
- **AgentOS**: Full-stack visual observability layer (FastAPI + React + ReactFlow)
- **Portfolio Manager**: Phases 1–10 fully implemented

# In Progress

- None — branch ready for PR

# Active Blockers

- None currently
