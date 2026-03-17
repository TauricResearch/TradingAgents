# Global Macro Analyzer Implementation Plan

## Execution Plan for TradingAgents Framework

### Overview

This plan outlines the implementation of a global macro analyzer (market-wide scanner) for the TradingAgents framework. The scanner will discover interesting stocks before running deep per-ticker analysis by scanning global news, market movers, sector performance, and outputting a top-10 stock watchlist.

### Architecture

A separate LangGraph with its own state, agents, and CLI command — sharing the existing LLM infrastructure, tool patterns, and data layer.

```
START ──┬── Geopolitical Scanner (quick_think) ──┐
        ├── Market Movers Scanner (quick_think) ──┼── Industry Deep Dive (mid_think) ── Macro Synthesis (deep_think) ── END
        └── Sector Scanner (quick_think) ─────────┘
```

### Implementation Steps

#### 1. Fix Infrastructure Issues

- [ ] Verify pyproject.toml has correct [build-system] and [project.scripts] sections
- [ ] Check for and remove any stray scanner_tools.py files outside tradingagents/

#### 2. Create Data Layer

- [ ] Create tradingagents/dataflows/yfinance_scanner.py with required functions:
  - get_market_movers_yfinance(category) — uses yf.Screener() for day_gainers, day_losers, most_actives
  - get_market_indices_yfinance() — fetches ^GSPC, ^DJI, ^IXIC, ^VIX, ^RUT daily data
  - get_sector_performance_yfinance() — uses yf.Sector() for all 11 GICS sectors
  - get_industry_performance_yfinance(sector_key) — uses yf.Industry() for drill-down
  - get_topic_news_yfinance(topic, limit) — uses yf.Search(query=topic)
- [ ] Create tradingagents/dataflows/alpha_vantage_scanner.py with fallback function:
  - get_market_movers_alpha_vantage(category) — uses TOP_GAINERS_LOSERS endpoint

#### 3. Create Tools

- [ ] Create tradingagents/agents/utils/scanner_tools.py with @tool decorated wrappers (same pattern as news_data_tools.py):
  - get_market_movers — top gainers, losers, most active
  - get_market_indices — major index values and daily changes
  - get_sector_performance — sector-level performance overview
  - get_industry_performance — industry-level drill-down within a sector
  - get_topic_news — search news by arbitrary topic
  Each function should call route_to_vendor(method, ...) instead of the yfinance functions directly.

#### 4. Update Supporting Files

- [ ] Update tradingagents/agents/utils/agent_utils.py to import/re-export scanner tools
- [ ] Update tradingagents/dataflows/interface.py to add scanner_data category to TOOLS_CATEGORIES and VENDOR_METHODS

#### 5. Create State

- [ ] Create tradingagents/agents/utils/scanner_states.py with ScannerState class:

    ```python
    class ScannerState(MessagesState):
        scan_date: str
        geopolitical_report: str          # Phase 1
        market_movers_report: str         # Phase 1
        sector_performance_report: str    # Phase 1
        industry_deep_dive_report: str    # Phase 2
        macro_scan_summary: str           # Phase 3 (final output)
    ```

#### 6. Create Agents

- [ ] Create tradingagents/agents/scanner/__init__.py (exports all factories)
- [ ] Create tradingagents/agents/scanner/geopolitical_scanner.py:
  - create_geopolitical_scanner(llm)
  - quick_think LLM tier
  - Tools: get_global_news, get_topic_news
  - Output Field: geopolitical_report
- [ ] Create tradingagents/agents/scanner/market_movers_scanner.py:
  - create_market_movers_scanner(llm)
  - quick_think LLM tier
  - Tools: get_market_movers, get_market_indices
  - Output Field: market_movers_report
- [ ] Create tradingagents/agents/scanner/sector_scanner.py:
  - create_sector_scanner(llm)
  - quick_think LLM tier
  - Tools: get_sector_performance, get_industry_performance
  - Output Field: sector_performance_report
- [ ] Create tradingagents/agents/scanner/industry_deep_dive.py:
  - create_industry_deep_dive_agent(llm)
  - mid_think LLM tier
  - Tools: get_industry_performance, get_topic_news
  - Output Field: industry_deep_dive_report
- [ ] Create tradingagents/agents/scanner/synthesis_agent.py:
  - create_macro_synthesis_agent(llm)
  - deep_think LLM tier
  - Tools: none (pure LLM)
  - Output Field: macro_scan_summary

#### 7. Create Graph Components

- [ ] Create tradingagents/graph/scanner_conditional_logic.py:
  - ScannerConditionalLogic class
  - Functions: should_continue_geopolitical, should_continue_movers, should_continue_sector, should_continue_industry
  - Tool-call check pattern (same as conditional_logic.py)
- [ ] Create tradingagents/graph/scanner_setup.py:
  - ScannerGraphSetup class
  - Registers nodes/edges
  - Fan-out from START to 3 scanners
  - Fan-in to Industry Deep Dive
  - Then Synthesis → END
- [ ] Create tradingagents/graph/scanner_graph.py:
  - MacroScannerGraph class (mirrors TradingAgentsGraph)
  - Init LLMs, build tool nodes, compile graph
  - Expose scan(date) method
  - No memory/reflection needed

#### 8. Modify CLI

- [ ] Add scan command to cli/main.py:
  - @app.command() def scan():
  - Asks for: scan date (default: today), LLM provider config (reuse existing helpers)
  - Does NOT ask for ticker (whole-market scan)
  - Instantiates MacroScannerGraph, calls graph.scan(date)
  - Displays results with Rich: panels for each report section, numbered table for top 10 stocks
  - Saves report to results/macro_scan/{date}/

#### 9. Update Config

- [ ] Add "scanner_data": "yfinance" to data_vendors in tradingagents/default_config.py

#### 10. Verify Implementation

- [ ] Test with commands:

    ```bash
    python -c "from tradingagents.agents.utils.scanner_tools import get_market_movers"
    python -c "from tradingagents.graph.scanner_graph import MacroScannerGraph"
    tradingagents scan
    ```

### Data Source Decision

- __Primary__: yfinance (has Screener(), Sector(), Industry(), index tickers — comprehensive)
- __Fallback__: Alpha Vantage TOP_GAINERS_LOSERS for get_market_movers tool only
- __Reason__: yfinance has broader screener/sector coverage; Alpha Vantage free tier limited to 25 requests/day

### Key Design Decisions

- Separate graph — scanner doesn't modify the existing trading analysis pipeline
- No debate phase — this is an informational scan, not a trading decision
- No memory/reflection — point-in-time snapshot; can be added later
- Parallel phase 1 — 3 scanners run concurrently for speed; Industry Deep Dive cross-references all outputs
- yfinance primary, AV fallback — yfinance has broader screener/sector coverage; Alpha Vantage only for market movers fallback

### Verification Criteria

1. All created files are in correct locations with proper content
2. Scanner tools can be imported and used correctly
3. Graph compiles and executes without errors
4. CLI scan command works and produces expected output
5. Configuration properly routes scanner data to yfinance
