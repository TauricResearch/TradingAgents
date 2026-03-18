---
type: decision
status: active
date: 2026-03-17
agent_author: "claude"
tags: [lessons, mistakes, patterns]
related_files: []
---

## Context

Documented bugs and wrong assumptions encountered during scanner pipeline development. These lessons prevent repeating the same mistakes.

## The Decision

Codify all lessons learned as actionable rules for future development.

## Constraints

None — these are universal rules for this project.

## Actionable Rules

### Tool Execution
- When an LLM has `bind_tools`, there MUST be a tool execution mechanism — either graph-level `ToolNode` routing or inline `run_tool_loop()`. Always verify the tool execution path exists.

### yfinance DataFrames
- `top_companies` has ticker as INDEX, not column. Always use `.iterrows()` or check `.index`.
- `Sector.overview` returns only metadata — no performance data. Use ETF proxies.
- Always inspect DataFrame structure with `.head()`, `.columns`, `.index` before writing access code.

### Vendor Fallback
- Functions inside `route_to_vendor` must RAISE on failure, not embed errors in return values.
- Catch `(AlphaVantageError, FinnhubError, ConnectionError, TimeoutError)`, not just specific subtypes.
- Fallback is opt-in: only methods in `FALLBACK_ALLOWED` get cross-vendor fallback. All others fail-fast (ADR 011).

### LangGraph
- Any state field written by parallel nodes MUST have a reducer (`Annotated[str, reducer_fn]`).

### Configuration
- Never hardcode URLs. Always use configured values with sensible defaults.
- `llm_provider` and `backend_url` must always exist at top level as fallbacks.
- When refactoring config, grep for all references before removing keys.

### Environment
- When creating `.env` files, always verify they have real values, not placeholders.
- When debugging auth errors, first check `os.environ.get('KEY')` to see what's actually loaded.
- `load_dotenv()` runs at module level in `default_config.py` — import-order-independent.

### Threading
- Never hold a lock during `sleep()` or IO. Release, sleep, re-acquire.
