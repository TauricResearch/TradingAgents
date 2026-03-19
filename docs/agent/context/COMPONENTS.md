<!-- Last verified: 2026-03-19 -->

# Components

## Directory Tree

```
tradingagents/
├── __init__.py
├── default_config.py              # All config keys, defaults, env var overrides
├── report_paths.py                # Unified report path helpers (reports/daily/{date}/)
├── daily_digest.py                # append_to_digest() — consolidates runs into daily_digest.md
├── notebook_sync.py               # sync_to_notebooklm() — uploads digest to NotebookLM via nlm CLI
├── observability.py               # RunLogger, _LLMCallbackHandler, structured event logging
├── agents/
│   ├── __init__.py
│   ├── analysts/
│   │   ├── fundamentals_analyst.py  # create_fundamentals_analyst(llm)
│   │   ├── market_analyst.py        # create_market_analyst(llm)
│   │   ├── news_analyst.py          # create_news_analyst(llm)
│   │   └── social_media_analyst.py  # create_social_media_analyst(llm)
│   ├── managers/
│   │   ├── research_manager.py      # create_research_manager(llm, memory)
│   │   └── risk_manager.py          # create_risk_manager(llm, memory)
│   ├── researchers/
│   │   ├── bear_researcher.py       # create_bear_researcher(llm, memory)
│   │   └── bull_researcher.py       # create_bull_researcher(llm, memory)
│   ├── risk_mgmt/
│   │   ├── aggressive_debator.py    # create_aggressive_debator(llm)
│   │   ├── conservative_debator.py  # create_conservative_debator(llm)
│   │   └── neutral_debator.py       # create_neutral_debator(llm)
│   ├── scanners/
│   │   ├── __init__.py
│   │   ├── geopolitical_scanner.py  # create_geopolitical_scanner(llm)
│   │   ├── market_movers_scanner.py # create_market_movers_scanner(llm)
│   │   ├── sector_scanner.py        # create_sector_scanner(llm)
│   │   ├── industry_deep_dive.py    # create_industry_deep_dive(llm)
│   │   └── macro_synthesis.py       # create_macro_synthesis(llm)
│   ├── trader/
│   │   └── trader.py                # create_trader(llm, memory)
│   └── utils/
│       ├── agent_states.py          # AgentState, InvestDebateState, RiskDebateState
│       ├── agent_utils.py           # Tool re-exports, create_msg_delete()
│       ├── core_stock_tools.py      # get_stock_data, get_indicators, get_macro_regime
│       ├── fundamental_data_tools.py # get_fundamentals, get_balance_sheet, etc.
│       ├── json_utils.py            # extract_json()
│       ├── memory.py                # FinancialSituationMemory
│       ├── news_data_tools.py       # get_news, get_global_news, get_insider_transactions
│       ├── scanner_states.py        # ScannerState, _last_value reducer
│       ├── scanner_tools.py         # Scanner @tool definitions (7 tools)
│       ├── technical_indicators_tools.py
│       └── tool_runner.py           # run_tool_loop(), MAX_TOOL_ROUNDS, MIN_REPORT_LENGTH
├── dataflows/
│   ├── __init__.py
│   ├── config.py                    # set_config(), get_config(), initialize_config()
│   ├── interface.py                 # route_to_vendor, VENDOR_METHODS, FALLBACK_ALLOWED
│   ├── alpha_vantage.py             # Re-export facade
│   ├── alpha_vantage_common.py      # Exception hierarchy, rate limiter
│   ├── alpha_vantage_fundamentals.py
│   ├── alpha_vantage_indicator.py
│   ├── alpha_vantage_news.py
│   ├── alpha_vantage_scanner.py
│   ├── alpha_vantage_stock.py
│   ├── finnhub.py
│   ├── finnhub_common.py            # Exception hierarchy, rate limiter
│   ├── finnhub_fundamentals.py
│   ├── finnhub_indicators.py
│   ├── finnhub_news.py
│   ├── finnhub_scanner.py
│   ├── finnhub_stock.py
│   ├── macro_regime.py
│   ├── peer_comparison.py
│   ├── stockstats_utils.py
│   ├── ttm_analysis.py
│   ├── utils.py
│   ├── y_finance.py                 # Core yfinance data functions
│   ├── yfinance_news.py
│   └── yfinance_scanner.py
├── graph/
│   ├── trading_graph.py             # TradingAgentsGraph class
│   ├── scanner_graph.py             # ScannerGraph class
│   ├── setup.py                     # GraphSetup — trading graph builder
│   ├── scanner_setup.py             # ScannerGraphSetup — scanner graph builder
│   ├── conditional_logic.py         # ConditionalLogic — debate/risk routing
│   ├── propagation.py               # Propagator
│   ├── reflection.py                # Reflector
│   └── signal_processing.py         # SignalProcessor
├── llm_clients/                     # Multi-provider LLM factory
│   └── (create_llm_client dispatch)
└── pipeline/
    ├── __init__.py
    └── macro_bridge.py              # MacroBridge, data classes, pipeline orchestration

cli/
└── main.py                          # Typer app, MessageBuffer, Rich UI, 3 commands
```

## Agent Factory Inventory (17 factories + 1 utility)

| Factory | File | LLM Tier | Extra Params |
|---------|------|----------|-------------|
| `create_fundamentals_analyst` | `agents/analysts/fundamentals_analyst.py` | quick | — |
| `create_market_analyst` | `agents/analysts/market_analyst.py` | quick | — |
| `create_news_analyst` | `agents/analysts/news_analyst.py` | quick | — |
| `create_social_media_analyst` | `agents/analysts/social_media_analyst.py` | quick | — |
| `create_bull_researcher` | `agents/researchers/bull_researcher.py` | mid | `memory` |
| `create_bear_researcher` | `agents/researchers/bear_researcher.py` | mid | `memory` |
| `create_research_manager` | `agents/managers/research_manager.py` | deep | `memory` |
| `create_trader` | `agents/trader/trader.py` | mid | `memory` |
| `create_aggressive_debator` | `agents/risk_mgmt/aggressive_debator.py` | quick | — |
| `create_conservative_debator` | `agents/risk_mgmt/conservative_debator.py` | quick | — |
| `create_neutral_debator` | `agents/risk_mgmt/neutral_debator.py` | quick | — |
| `create_risk_manager` | `agents/managers/risk_manager.py` | deep | `memory` |
| `create_geopolitical_scanner` | `agents/scanners/geopolitical_scanner.py` | quick | — |
| `create_market_movers_scanner` | `agents/scanners/market_movers_scanner.py` | quick | — |
| `create_sector_scanner` | `agents/scanners/sector_scanner.py` | quick | — |
| `create_industry_deep_dive` | `agents/scanners/industry_deep_dive.py` | mid | — |
| `create_macro_synthesis` | `agents/scanners/macro_synthesis.py` | deep | — |
| `create_msg_delete` | `agents/utils/agent_utils.py` | — | No LLM param |

## Extension Guides

### Adding a New Analyst
1. Create `tradingagents/agents/analysts/new_analyst.py` with `create_new_analyst(llm)`
2. Add tools to `tradingagents/agents/utils/` and register in `agent_utils.py`
3. Register tool node in `trading_graph.py:_create_tool_nodes()`
4. Add node and edges in `graph/setup.py:setup_graph()`
5. Add conditional routing in `graph/conditional_logic.py`
6. Add to `cli/main.py` `ANALYST_MAPPING` and `REPORT_SECTIONS`

### Adding a New Scanner
1. Create `tradingagents/agents/scanners/new_scanner.py` with `create_new_scanner(llm)`
2. Export from `agents/scanners/__init__.py`
3. Add to `scanner_graph.py` agents dict
4. Add node and edges in `graph/scanner_setup.py`
5. Add state field with `_last_value` reducer to `scanner_states.py`

### Adding a New Data Vendor
1. Create `tradingagents/dataflows/newvendor_common.py` (exception hierarchy, rate limiter)
2. Create per-domain modules (`newvendor_stock.py`, `newvendor_scanner.py`, etc.)
3. Add vendor functions to `VENDOR_METHODS` in `interface.py`
4. Add vendor to `VENDOR_LIST` in `interface.py`
5. Add exception types to the catch tuple in `route_to_vendor`
6. Add config category in `default_config.py` `data_vendors`

### Adding a New LLM Provider
1. Add client creation logic to `tradingagents/llm_clients/`
2. Add provider-specific kwargs handling in `trading_graph.py:_get_provider_kwargs()` and `scanner_graph.py:_get_provider_kwargs()`
3. Add API key to `.env.example`

### Adding a New Config Key
1. Add to `DEFAULT_CONFIG` dict in `default_config.py` with `_env()` or `_env_int()` override
2. Add to `.env.example` with documentation
3. Update `CLAUDE.md` if it's a frequently-used key

## CLI Commands

| Command | Function | Description |
|---------|----------|-------------|
| `analyze` | `run_analysis()` | Interactive per-ticker multi-agent analysis with Rich live UI |
| `scan` | `run_scan(date)` | 3-phase macro scanner, saves 5 report files |
| `pipeline` | `run_pipeline()` | Full pipeline: scan JSON → filter by conviction → per-ticker deep dive |

## Test Organization

| Test File | Type | What It Covers | Markers |
|-----------|------|---------------|---------|
| `test_alpha_vantage_exceptions.py` | Mixed | AV exception hierarchy, `_make_api_request` errors | `integration` on HTTP tests |
| `test_alpha_vantage_integration.py` | Unit | Full AV data layer (all mocked) | — |
| `test_alpha_vantage_scanner.py` | Integration | Live AV scanner functions | `integration` |
| `test_config_wiring.py` | Unit | `AgentState` fields, tool exports, debate wiring | — |
| `test_debate_rounds.py` | Unit | `ConditionalLogic` routing at various round counts | — |
| `test_e2e_api_integration.py` | Unit | Vendor routing layer (all mocked) | — |
| `test_env_override.py` | Unit | `TRADINGAGENTS_*` env var overrides | — |
| `test_finnhub_integration.py` | Unit | Full Finnhub data layer (all mocked) | — |
| `test_finnhub_live_integration.py` | Integration | Live Finnhub endpoints | `integration`, `paid_tier` |
| `test_industry_deep_dive.py` | Mixed | `_extract_top_sectors`, nudge mechanism, enriched output | — |
| `test_json_utils.py` | Unit | `extract_json()` — markdown, think blocks, edge cases | — |
| `test_macro_bridge.py` | Unit | Pipeline: parse, filter, render, save | — |
| `test_macro_regime.py` | Mixed | Macro signals, regime classification, report format | `integration` on live test |
| `test_peer_comparison.py` | Mixed | Peer comparison functions | `integration` on live test |
| `test_scanner_comprehensive.py` | Integration | All 5 scanner tools + CLI output naming | — |
| `test_scanner_fallback.py` | Mixed | yfinance perf, AV failure mode, fallback routing | `integration` on some |
| `test_scanner_graph.py` | Unit | `ScannerGraph` import/instantiation, graph compilation | — |
| `test_scanner_mocked.py` | Unit | All yfinance + AV scanner functions (all mocked) | — |
| `test_scanner_routing.py` | Integration | Live routing with AV config | `integration` |
| `test_scanner_tools.py` | Integration | Scanner tool imports + live invocation | — |
| `test_ttm_analysis.py` | Mixed | TTM metrics computation, report format | `integration` on live test |
| `test_vendor_failfast.py` | Unit | ADR 011 fail-fast behavior, error chaining | — |
| `test_yfinance_integration.py` | Unit | Full yfinance data layer (all mocked) | — |

Pytest markers: `integration` (live API), `paid_tier` (Finnhub paid subscription), `slow` (long-running). Defined in `conftest.py`.
