# Architecture Decisions Log

## Decision 001: Hybrid LLM Setup (Ollama + OpenRouter)

**Date**: 2026-03-17
**Status**: Implemented ✅

**Context**: Need cost-effective LLM setup for scanner pipeline with different complexity tiers.

**Decision**: Use hybrid approach:
- **quick_think + mid_think**: `qwen3.5:27b` via Ollama at `http://192.168.50.76:11434` (local, free)
- **deep_think**: `deepseek/deepseek-r1-0528` via OpenRouter (cloud, paid)

**Config location**: `tradingagents/default_config.py` — per-tier `_llm_provider` and `_backend_url` keys.

**Consequence**: Removed top-level `llm_provider` and `backend_url` from config. Each tier must have its own `{tier}_llm_provider` set explicitly.

---

## Decision 002: Data Vendor Fallback Strategy

**Date**: 2026-03-17
**Status**: Implemented ✅

**Context**: Alpha Vantage free/demo key doesn't support ETF symbols and has strict rate limits. Need reliable data for scanner.

**Decision**:
- `route_to_vendor()` catches `AlphaVantageError` (base class) to trigger fallback, not just `RateLimitError`.
- AV scanner functions raise `AlphaVantageError` when ALL queries fail (not silently embedding errors in output strings).
- yfinance is the fallback vendor and uses SPDR ETF proxies for sector performance instead of broken `Sector.overview`.

**Files changed**:
- `tradingagents/dataflows/interface.py` — broadened catch
- `tradingagents/dataflows/alpha_vantage_scanner.py` — raise on total failure
- `tradingagents/dataflows/yfinance_scanner.py` — ETF proxy approach

---

## Decision 003: yfinance Sector Performance via ETF Proxies

**Date**: 2026-03-17
**Status**: Implemented ✅

**Context**: `yfinance.Sector("technology").overview` returns only metadata (companies_count, market_cap, etc.) — no performance data (oneDay, oneWeek, etc.).

**Decision**: Use SPDR sector ETFs as proxies:
```python
sector_etfs = {
    "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
    "Energy": "XLE", "Consumer Discretionary": "XLY", ...
}
```
Download 6 months of history via `yf.download()` and compute 1-day, 1-week, 1-month, YTD percentage changes from closing prices.

**File**: `tradingagents/dataflows/yfinance_scanner.py`

---

## Decision 004: Inline Tool Execution Loop for Scanner Agents

**Date**: 2026-03-17
**Status**: Implemented ✅

**Context**: The existing trading graph uses separate `ToolNode` graph nodes for tool execution (agent → tool_node → agent routing loop). Scanner agents are simpler single-pass nodes — no ToolNode in the graph. When the LLM returned tool_calls, nobody executed them, resulting in empty reports.

**Decision**: Created `tradingagents/agents/utils/tool_runner.py` with `run_tool_loop()` that runs an inline tool execution loop within each scanner agent node:
1. Invoke chain
2. If tool_calls present → execute tools → append ToolMessages → re-invoke
3. Repeat up to `MAX_TOOL_ROUNDS=5` until LLM produces text response

**Alternative considered**: Adding ToolNode + conditional routing to scanner_setup.py (like trading graph). Rejected — too complex for the fan-out/fan-in pattern and would require 4 separate tool nodes with routing logic.

**Files**:
- `tradingagents/agents/utils/tool_runner.py` (new)
- All scanner agents updated to use `run_tool_loop()`

---

## Decision 005: LangGraph State Reducers for Parallel Fan-Out

**Date**: 2026-03-17
**Status**: Implemented ✅

**Context**: Phase 1 runs 3 scanners in parallel. All write to shared state fields (`sender`, etc.). LangGraph requires reducers for concurrent writes — otherwise raises `INVALID_CONCURRENT_GRAPH_UPDATE`.

**Decision**: Added `_last_value` reducer to all `ScannerState` fields via `Annotated[str, _last_value]`.

**File**: `tradingagents/agents/utils/scanner_states.py`

---

## Decision 006: CLI --date Flag for Scanner

**Date**: 2026-03-17
**Status**: Implemented ✅

**Context**: `python -m cli.main scan` was interactive-only (prompts for date). Needed non-interactive invocation for testing/automation.

**Decision**: Added `--date` / `-d` option to `scan` command. Falls back to interactive prompt if not provided.

**File**: `cli/main.py`

---

## Decision 007: .env Loading Strategy

**Date**: 2026-03-17
**Status**: Implemented ✅

**Context**: `load_dotenv()` loads from CWD. When running from a git worktree, the worktree `.env` may have placeholder values while the main repo `.env` has real keys.

**Decision**: `cli/main.py` calls `load_dotenv()` (CWD) then `load_dotenv(Path(__file__).parent.parent / ".env")` as fallback. The worktree `.env` was also updated with real API keys.

**Note for future**: If `.env` issues recur, check which `.env` file is being picked up. The worktree and main repo each have their own `.env`.
