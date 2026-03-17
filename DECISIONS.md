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

## Decision 008: Git Remote Strategy — origin = fork

**Date**: 2026-03-17
**Status**: Documented ✅

**Setup**: There is only one configured remote:
```
origin → http://127.0.0.1:46699/git/aguzererler/TradingAgents  (the user's fork)
```
No `upstream` remote for the parent repo.

**Rule**: Always push feature branches to `origin`. Never push directly to `main`. PRs are created from `claude/*` branches on the fork via the Gitea web UI (no `gh` CLI available).

---

## Decision 009: Medium-Term Upgrade — Macro Regime via yfinance Only

**Date**: 2026-03-17
**Status**: Implemented ✅

**Context**: Macro regime classification needs VIX, credit spreads, yield curve, market breadth, sector rotation — all free signals.

**Decision**: Use yfinance exclusively for all macro regime signals (no Alpha Vantage endpoint for this data). 6 signals from `^VIX`, `^GSPC`, `HYG`, `LQD`, `TLT`, `SHY`, and sector ETFs. No vendor routing needed.

**Scoring**: Each signal ±1. Total ≥3 = risk-on, ≤-3 = risk-off, else transition. Confidence based on absolute score: |score| ≥4 → high, ≥2 → medium, else low.

**File**: `tradingagents/dataflows/macro_regime.py`

---

## Decision 009: TTM Tool Prefers Alpha Vantage (More History)

**Date**: 2026-03-17
**Status**: Implemented ✅

**Context**: yfinance returns only 4-5 quarterly periods. Alpha Vantage `INCOME_STATEMENT` endpoint returns up to 20 quarters. For 8-quarter trend analysis, AV is significantly better.

**Decision**: `get_ttm_analysis` tool uses `route_to_vendor` with AV as primary, yfinance as fallback. TTM module handles <8 quarters gracefully (computes with what's available, reports `quarters_available`).

**File**: `tradingagents/dataflows/ttm_analysis.py`

---

## Decision 010: Peer Comparison via Hardcoded Sector Tickers

**Date**: 2026-03-17
**Status**: Implemented ✅

**Context**: No Alpha Vantage endpoint for peer comparison. yfinance `top_companies` was unreliable (Mistake 3). Need deterministic peer lists.

**Decision**: Hardcode `_SECTOR_TICKERS` mapping (20 tickers per sector) and `_SECTOR_ETFS` in `peer_comparison.py`. Peer data via `yf.download()` — reliable and fast. Sector ETF used as benchmark for alpha calculation.

**Trade-off**: Peers don't auto-update if sector composition changes. Acceptable for current use case.

**File**: `tradingagents/dataflows/peer_comparison.py`

---

## Decision 007: .env Loading Strategy

**Date**: 2026-03-17
**Status**: Implemented ✅

**Context**: `load_dotenv()` loads from CWD. When running from a git worktree, the worktree `.env` may have placeholder values while the main repo `.env` has real keys.

**Decision**: `cli/main.py` calls `load_dotenv()` (CWD) then `load_dotenv(Path(__file__).parent.parent / ".env")` as fallback. The worktree `.env` was also updated with real API keys.

**Note for future**: If `.env` issues recur, check which `.env` file is being picked up. The worktree and main repo each have their own `.env`.
