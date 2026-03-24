# Current Milestone

Smart Money Scanner added to scanner pipeline (Phase 1b). `finvizfinance` integration with Golden Overlap strategy in macro_synthesis. 18 agent factories. All tests passing (2 pre-existing failures excluded).

# Recent Progress

- **Smart Money Scanner (current branch)**: 4th scanner node added to macro pipeline
  - `tradingagents/agents/scanners/smart_money_scanner.py` — Phase 1b node, runs sequentially after sector_scanner
  - `tradingagents/agents/utils/scanner_tools.py` — 3 zero-parameter Finviz tools: `get_insider_buying_stocks`, `get_unusual_volume_stocks`, `get_breakout_accumulation_stocks`
  - `tradingagents/agents/utils/scanner_states.py` — Added `smart_money_report` field with `_last_value` reducer
  - `tradingagents/graph/scanner_setup.py` — Topology: sector_scanner → smart_money_scanner → industry_deep_dive
  - `tradingagents/graph/scanner_graph.py` — Instantiates smart_money_scanner with quick_llm
  - `tradingagents/agents/scanners/macro_synthesis.py` — Golden Overlap instructions + smart_money_report in context
  - `pyproject.toml` — Added `finvizfinance>=0.14.0` dependency
  - `docs/agent/decisions/014-finviz-smart-money-scanner.md` — ADR documenting all design decisions
  - Tests: 6 new mocked tests in `tests/unit/test_scanner_mocked.py`, 1 fix in `tests/unit/test_scanner_graph.py`
- **AgentOS**: Full-stack visual observability layer (FastAPI + React + ReactFlow)
- **Portfolio Manager**: Phases 1–10 fully implemented (models, agents, CLI integration, stop-loss/take-profit)
- **PR #32 merged**: Portfolio Manager data foundation

# In Progress

- None — branch ready for PR

# Active Blockers

- None currently
