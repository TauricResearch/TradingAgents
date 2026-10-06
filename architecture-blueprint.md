## Code baseline

- Upstream project: TauricResearch/TradingAgents (multi-agent LLM trading framework, Apache-2.0).
- Fork point (baseline commit): 1394a3f72aa4393e1a98f51b382434c4b4c2d972
  ("Merge pull request #1478 from TauricResearch/v0.6.0", 2026-10-03).
- Inherited packages: `tradingagents/` (agents, dataflows, graph, llm_clients, memory) and `cli/`.
- Inherited test suite: 86 files; measured before any change on Python 3.12.14 in a clean venv:
  1262 passed, 1 skipped (optional `langchain_aws`), 1 deselected (`-m "not integration"`), ~12 s.
- Inherited CI: `.github/workflows/ci.yml` (upstream: test matrix, smoke install, full-repo ruff).
  Replaced by our six blocking gates (see ADR-003 / CHG-002).
- Decision to adopt this baseline: ADR-001. Layout alignment: ADR-002.
