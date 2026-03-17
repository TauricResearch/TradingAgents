---
type: decision
status: active
date: 2026-03-17
agent_author: "copilot+claude"
tags: [scanner, industry-deep-dive, tool-execution, prompt-engineering, yfinance]
related_files:
  - tradingagents/agents/scanners/industry_deep_dive.py
  - tradingagents/agents/utils/tool_runner.py
  - tradingagents/agents/utils/scanner_tools.py
  - tradingagents/dataflows/yfinance_scanner.py
pr: "13"
---

## Context

Phase 2 (Industry Deep Dive) produced sparse reports despite receiving ~21K chars of Phase 1
context. Three root causes were identified:

1. **LLM guessing sector keys** — the LLM had to infer valid `sector_key` strings (e.g., `"financial-services"` vs `"financials"`) with no guidance, leading to failed tool calls.
2. **Thin industry data** — `get_industry_performance_yfinance` returned only static metadata (name, rating, market weight). No performance signal for the LLM to act on.
3. **Tool-call skipping under long context** — weaker local LLMs (Ollama/qwen) sometimes produce a short prose response instead of calling tools when the prompt is long.

## The Decision

Three-pronged fix (PR #13):

### 1. Enriched Industry Performance Data

`get_industry_performance_yfinance` now batch-downloads 1-month price history for the top 10
tickers in each industry and computes 1-day, 1-week, and 1-month percentage returns.
Output table expands from 4 to 7 columns:

```
| Company | Symbol | Rating | Market Weight | 1-Day % | 1-Week % | 1-Month % |
```

Both download and display use `head(10)` for consistency (avoids N/A rows for positions 11-20).

### 2. Explicit Sector Routing via `_extract_top_sectors()`

`industry_deep_dive.py` defines:
- `VALID_SECTOR_KEYS` — the 11 canonical yfinance sector key strings
- `_DISPLAY_TO_KEY` — maps display names (e.g., `"Financial Services"`) to keys (e.g., `"financial-services"`)
- `_extract_top_sectors(sector_report, n)` — parses the Phase 1 sector performance table, ranks sectors by absolute 1-month move, returns top-N valid keys

The prompt now injects the pre-extracted keys directly:

```
Call get_industry_performance for EACH of these top sectors: 'energy', 'communication-services', 'technology'
Valid sector_key values: 'technology', 'healthcare', 'financial-services', ...
```

This eliminates LLM guesswork entirely.

### 3. Tool-Call Nudge in `run_tool_loop`

If the LLM's first response has no `tool_calls` and is under 500 characters, a
`HumanMessage` nudge is appended before re-invoking. Fires **once only** to avoid loops.
Prevents short-circuit prose responses from weak LLMs under heavy context.

### 4. Tool Description Update

`get_industry_performance` docstring now enumerates all 11 valid sector keys so they appear
in the tool schema visible to the LLM.

## Constraints

- `_extract_top_sectors()` must degrade gracefully: if parsing fails (malformed Phase 1 report),
  it falls back to the top 3 default sectors `["technology", "financial-services", "energy"]`.
- The tool-call nudge fires **at most once** per agent invocation — do not loop on nudge.
- `get_industry_performance_yfinance` must use `head(10)` for **both** download and display
  to prevent N/A rows (Mistake #11: was displaying 20 rows but only downloading data for 10).

## Actionable Rules

- Always inject pre-extracted sector keys into Industry Deep Dive prompt — never rely on the LLM to guess valid `sector_key` values.
- When enriching `get_industry_performance_yfinance`, keep download count and display count in sync.
- Tool-call nudge threshold is 500 chars — do not raise it; the intent is to catch short non-tool responses, not legitimate brief answers.
- All 11 VALID_SECTOR_KEYS must be listed in the `get_industry_performance` tool docstring.

## Tests Added

15 new tests in `tests/test_industry_deep_dive.py`:
- 8 tests for `_extract_top_sectors()` parsing and edge cases
- 4 tests for nudge mechanism (mock chain)
- 3 tests for enriched output format (network-dependent, auto-skip if offline)
