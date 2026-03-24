# ADR 014: Finviz Smart Money Scanner — Phase 1b Bottom-Up Signal Layer

## Status

Accepted

## Context

The macro scanner pipeline produced top-down qualitative analysis (geopolitical events, market movers, sector rotation) but selected stocks entirely from macro reasoning. There was no bottom-up quantitative signal layer to cross-validate candidates. Adding institutional footprint detection (insider buying, unusual volume, breakout accumulation) via `finvizfinance` creates a "Golden Overlap" — stocks confirmed by both top-down macro themes and bottom-up institutional signals carry higher conviction.

Key constraints considered during design:

1. `run_tool_loop()` has `MAX_TOOL_ROUNDS=5`. The market_movers_scanner already uses ~4 rounds. Adding Finviz tools to it would silently truncate at round 5.
2. `finvizfinance` is a web scraper, not an official API — it can be blocked or rate-limited at any time.
3. LLMs can hallucinate string parameter values when calling parameterized tools.
4. Sector rotation context is available from sector_scanner output and should inform smart money interpretation.

## Decisions

### 1. Separate Phase 1b Node (not bolted onto market_movers_scanner)

A dedicated `smart_money_scanner` node avoids the `MAX_TOOL_ROUNDS=5` truncation risk entirely. It runs sequentially after `sector_scanner` (not in the Phase 1a parallel fan-out), giving it access to `sector_performance_report` in state. This context lets the LLM cross-reference institutional footprints against leading/lagging sectors.

Final topology:
```
Phase 1a (parallel):   START → geopolitical_scanner
                       START → market_movers_scanner
                       START → sector_scanner
Phase 1b (sequential): sector_scanner → smart_money_scanner
Phase 2:               geopolitical_scanner, market_movers_scanner, smart_money_scanner → industry_deep_dive
Phase 3:               industry_deep_dive → macro_synthesis → END
```

### 2. Three Zero-Parameter Tools (not one parameterized tool)

Original proposal: `get_smart_money_anomalies(scan_type: str)` with values like `"insider_buying"`.

Problem: LLMs hallucinate string parameter values. The LLM might call `get_smart_money_anomalies("insider_buys")` or `get_smart_money_anomalies("volume_spike")` — strings that have no corresponding filter set.

Solution: Three separate zero-parameter tools:
- `get_insider_buying_stocks()` — hardcoded insider purchase filters
- `get_unusual_volume_stocks()` — hardcoded volume anomaly filters
- `get_breakout_accumulation_stocks()` — hardcoded 52-week high + volume filters

With zero parameters, there is nothing to hallucinate. The LLM selects tools by name from its schema — unambiguous. All three share a `_run_finviz_screen(filters_dict, label)` private helper to keep the implementation DRY.

### 3. Graceful Degradation (never raise)

`finvizfinance` wraps a web scraper that can fail at any time (rate limiting, Finviz HTML changes, network errors). `_run_finviz_screen()` catches all exceptions and returns a string starting with `"Smart money scan unavailable (Finviz error): <message>"`. The pipeline never hard-fails due to Finviz unavailability. `macro_synthesis` is instructed to note the absence and proceed on remaining reports.

### 4. `breakout_accumulation` over `oversold_bounces`

Original proposal included an `oversold_bounces` scan (RSI < 30). This was rejected: RSI < 30 bounces are retail contrarian signals, not smart money signals. Institutions don't systematically buy at RSI < 30. Replaced with `breakout_accumulation` (52-week highs on 2x+ volume) — the O'Neil CAN SLIM institutional accumulation pattern, where institutional buying drives price to new highs on above-average volume.

### 5. Golden Overlap in macro_synthesis

`macro_synthesis` now receives `smart_money_report` alongside the 4 existing reports. The system prompt includes explicit Golden Overlap instructions: if a smart money ticker fits the top-down macro narrative (e.g., an energy stock with heavy insider buying during a supply shock), assign it `"high"` conviction. If no smart money tickers align, proceed on remaining reports. The JSON output schema is unchanged.

## Consequences

- **Pro**: Dual evidence layer — top-down macro + bottom-up institutional signals improve conviction quality
- **Pro**: Zero hallucination risk — no string parameters in any Finviz tool
- **Pro**: Pipeline never fails due to Finviz — graceful degradation preserves all other outputs
- **Pro**: Sector context injection — smart money interpretation is informed by rotation context from sector_scanner
- **Con**: `finvizfinance` is a web scraper — brittle to Finviz HTML changes; requires periodic maintenance
- **Con**: Finviz screener results lag real-time institutional data (data is end-of-day); not suitable for intraday signals
- **Con**: Adds ~620 tokens to scanner pipeline token budget (quick_llm tier, acceptable)

## Source Files

- `tradingagents/agents/scanners/smart_money_scanner.py` (new)
- `tradingagents/agents/utils/scanner_tools.py` (3 new tools + `_run_finviz_screen` helper)
- `tradingagents/agents/utils/scanner_states.py` (`smart_money_report` field)
- `tradingagents/graph/scanner_setup.py` (Phase 1b topology)
- `tradingagents/graph/scanner_graph.py` (agent instantiation)
- `tradingagents/agents/scanners/macro_synthesis.py` (Golden Overlap prompt)
- `pyproject.toml` (`finvizfinance>=0.14.0`)
- `tests/unit/test_scanner_mocked.py` (6 new tests for Finviz tools)
