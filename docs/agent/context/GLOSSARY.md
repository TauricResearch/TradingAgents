<!-- Last verified: 2026-03-23 -->

# Glossary

## Agents & Workflows

| Term | Definition | Source |
|------|-----------|--------|
| Trading Graph | Full per-ticker analysis pipeline: analysts → debate → trader → risk → decision | `graph/trading_graph.py` |
| Scanner Graph | 3-phase macro scanner: parallel scanners → deep dive → synthesis | `graph/scanner_graph.py` |
| Agent Factory | Closure pattern `create_X(llm)` → returns `_node(state)` function | `agents/analysts/*.py`, `agents/scanners/*.py` |
| ToolNode | LangGraph-native tool executor — used in trading graph for analyst tools | `langgraph.prebuilt`, wired in `graph/setup.py` |
| run_tool_loop | Inline tool executor for scanner agents — iterates up to `MAX_TOOL_ROUNDS` | `agents/utils/tool_runner.py` |
| Nudge | If first LLM response is < `MIN_REPORT_LENGTH` chars with no tool calls, a HumanMessage is appended asking LLM to use tools. Fires at most once. | `agents/utils/tool_runner.py` |

## Data Layer

| Term | Definition | Source |
|------|-----------|--------|
| route_to_vendor | Central dispatch: resolves vendor for a method, calls it, handles fallback for `FALLBACK_ALLOWED` methods | `dataflows/interface.py` |
| VENDOR_METHODS | Dict mapping method name → vendor → function reference. Direct function refs, not module paths. | `dataflows/interface.py` |
| FALLBACK_ALLOWED | Set of 5 method names that get cross-vendor fallback: `get_stock_data`, `get_market_indices`, `get_sector_performance`, `get_market_movers`, `get_industry_performance` | `dataflows/interface.py` |
| TOOLS_CATEGORIES | Dict mapping category name → `{"description": str, "tools": list}`. 6 categories: `core_stock_apis`, `technical_indicators`, `fundamental_data`, `news_data`, `scanner_data`, `calendar_data` | `dataflows/interface.py` |
| ETF Proxy | SPDR sector ETFs (XLK, XLV, XLF, etc.) used to get sector performance since `Sector.overview` lacks performance data | `yfinance_scanner.py`, `alpha_vantage_scanner.py` |

## Configuration

| Term | Definition | Source |
|------|-----------|--------|
| quick_think | Fast-response LLM tier. Default: `gpt-5-mini` via `openai` | `default_config.py` |
| mid_think | Balanced-analysis tier. Default: `None` (falls back to quick_think) | `default_config.py` |
| deep_think | Complex-reasoning tier. Default: `gpt-5.2` via `openai` | `default_config.py` |
| _env() | Helper: reads `TRADINGAGENTS_<KEY>`, returns default if unset or empty | `default_config.py` |
| _env_int() | Helper: same as `_env()` but coerces to `int` | `default_config.py` |

## Vendor-Specific

| Term | Definition | Source |
|------|-----------|--------|
| AlphaVantageError | Base exception for AV failures | `dataflows/alpha_vantage_common.py` |
| FinnhubError | Base exception for Finnhub failures | `dataflows/finnhub_common.py` |
| APIKeyInvalidError | Auth failure (both AV and Finnhub have one) | `*_common.py` |
| RateLimitError | Rate limit exceeded (AV: 75/min, Finnhub: 60/min) | `*_common.py` |
| ThirdPartyError | Generic API error | `*_common.py` |
| ThirdPartyTimeoutError | Request timeout | `*_common.py` |
| ThirdPartyParseError | Response parsing failure | `*_common.py` |
| MSPR | Market Sentiment and Price Return — Finnhub insider transaction metric with no AV/yfinance equivalent | `finnhub_news.py` |

## State & Data Classes

| Term | Definition | Source |
|------|-----------|--------|
| AgentState | Trading graph state (extends `MessagesState`). Fields for reports, debate states, trade decision. | `agents/utils/agent_states.py` |
| InvestDebateState | TypedDict sub-state for bull/bear debate. Fields: `bull_history`, `bear_history`, `history`, `current_response`, `judge_decision`, `count`. | `agents/utils/agent_states.py` |
| RiskDebateState | TypedDict sub-state for risk debate. Fields: `aggressive_history`, `conservative_history`, `neutral_history`, `history`, `latest_speaker`, `current_aggressive_response`, `current_conservative_response`, `current_neutral_response`, `judge_decision`, `count`. | `agents/utils/agent_states.py` |
| ScannerState | Scanner graph state (extends `MessagesState`). All report fields use `_last_value` reducer. | `agents/utils/scanner_states.py` |
| _last_value | Reducer function: `def _last_value(existing, new) -> new`. Always keeps the newest value. | `agents/utils/scanner_states.py` |
| FinancialSituationMemory | Memory object for agents that need cross-session recall (bull/bear/trader/judge/risk). | `agents/utils/memory.py` |

## Pipeline

| Term | Definition | Source |
|------|-----------|--------|
| MacroBridge | Facade class: load scan JSON → filter candidates → run per-ticker analysis → save results | `pipeline/macro_bridge.py` |
| MacroContext | @dataclass: `economic_cycle`, `central_bank_stance`, `geopolitical_risks`, `key_themes`, `executive_summary`, `risk_factors`, `timeframe`, `region` | `pipeline/macro_bridge.py` |
| StockCandidate | @dataclass: `ticker`, `name`, `sector`, `rationale`, `thesis_angle`, `conviction`, `key_catalysts`, `risks`, `macro_theme` | `pipeline/macro_bridge.py` |
| TickerResult | @dataclass: per-ticker analysis result with all report fields, populated after `propagate()` | `pipeline/macro_bridge.py` |
| ConvictionLevel | `Literal["high", "medium", "low"]` | `pipeline/macro_bridge.py` |
| CONVICTION_RANK | `{"high": 3, "medium": 2, "low": 1}` — used for sorting/filtering | `pipeline/macro_bridge.py` |

## CLI

| Term | Definition | Source |
|------|-----------|--------|
| MessageBuffer | Deque-based singleton tracking agent statuses, reports, tool calls for Rich live UI | `cli/main.py` |
| StatsCallbackHandler | Token and timing statistics handler for display | `cli/stats_handler.py` |
| FIXED_AGENTS | Dict grouping non-analyst agents by team: Research Team, Trading Team, Risk Management, Portfolio Management | `cli/main.py` |
| ANALYST_MAPPING | Dict: `"market"` → `"Market Analyst"`, `"social"` → `"Social Analyst"`, etc. | `cli/main.py` |

## Observability

| Term | Definition | Source |
|------|-----------|--------|
| RunLogger | Accumulates structured events (llm, tool, vendor, report) for a single CLI run. Thread-safe. | `observability.py` |
| _LLMCallbackHandler | LangChain `BaseCallbackHandler` that feeds LLM call events (model, tokens, latency) into a `RunLogger` | `observability.py` |
| _Event | @dataclass: `kind`, `ts`, `data` — one JSON-line per event | `observability.py` |
| set_run_logger / get_run_logger | Thread-local context for passing `RunLogger` to vendor/tool layers | `observability.py` |

## Report Paths

| Term | Definition | Source |
|------|-----------|--------|
| REPORTS_ROOT | `Path("reports")` — root for all generated artifacts | `report_paths.py` |
| get_daily_dir | Returns `reports/daily/{date}/` | `report_paths.py` |
| get_market_dir | Returns `reports/daily/{date}/market/` — scan results | `report_paths.py` |
| get_ticker_dir | Returns `reports/daily/{date}/{TICKER}/` — per-ticker analysis | `report_paths.py` |
| get_eval_dir | Returns `reports/daily/{date}/{TICKER}/eval/` — eval logs | `report_paths.py` |

## Constants

| Constant | Value | Source |
|----------|-------|--------|
| MAX_TOOL_ROUNDS | `5` | `agents/utils/tool_runner.py` |
| MIN_REPORT_LENGTH | `2000` | `agents/utils/tool_runner.py` |
| max_debate_rounds | `1` (default) | `default_config.py` |
| max_risk_discuss_rounds | `1` (default) | `default_config.py` |
| max_recur_limit | `100` (default) | `default_config.py` |
| AV _RATE_LIMIT | `75` calls/min | `dataflows/alpha_vantage_common.py` |
| Finnhub _RATE_LIMIT | `60` calls/min | `dataflows/finnhub_common.py` |
| AV API_BASE_URL | `"https://www.alphavantage.co/query"` | `dataflows/alpha_vantage_common.py` |
| Finnhub API_BASE_URL | `"https://finnhub.io/api/v1"` | `dataflows/finnhub_common.py` |
| _MAX_CONTENT_LEN | `300` (event message truncation) | `agent_os/backend/services/langgraph_engine.py` |
| _MAX_FULL_LEN | `50_000` (full prompt/response cap) | `agent_os/backend/services/langgraph_engine.py` |

## AgentOS

| Term | Definition | Source |
|------|-----------|--------|
| AgentOS | Full-stack visual observability layer for agent execution — FastAPI backend + React frontend | `agent_os/` |
| LangGraphEngine | Backend service that orchestrates run execution and maps LangGraph v2 events to frontend events | `agent_os/backend/services/langgraph_engine.py` |
| Run Type | One of 4 execution modes: `scan`, `pipeline`, `portfolio`, `auto` | `agent_os/backend/routes/runs.py` |
| AgentEvent | TypeScript interface for frontend events: `thought`, `tool`, `tool_result`, `result`, `log`, `system` | `agent_os/frontend/src/hooks/useAgentStream.ts` |
| useAgentStream | React hook that connects to `/ws/stream/{run_id}` and provides events + status | `agent_os/frontend/src/hooks/useAgentStream.ts` |
| AgentGraph | ReactFlow-based live graph visualization of agent workflow nodes | `agent_os/frontend/src/components/AgentGraph.tsx` |
| PortfolioViewer | 3-tab portfolio view: holdings, trade history, snapshot summary | `agent_os/frontend/src/components/PortfolioViewer.tsx` |
| MetricHeader | Top-3 dashboard metrics: Sharpe ratio, market regime+beta, drawdown+VaR | `agent_os/frontend/src/components/MetricHeader.tsx` |
| _safe_dict | Helper that converts non-dict metadata to empty dict to prevent crashes | `agent_os/backend/services/langgraph_engine.py` |
| Inspector Drawer | Side panel showing full prompt/response content for an event or node | `agent_os/frontend/src/Dashboard.tsx` |
| Field Mapping | `/latest` endpoint translates backend model fields to frontend shape (shares→quantity, etc.) | `agent_os/backend/routes/portfolios.py` |
