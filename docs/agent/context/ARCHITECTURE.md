<!-- Last verified: 2026-03-24 -->

# Architecture

TradingAgents v0.2.2 is a multi-agent LLM framework using LangGraph. It has 18 agent factory functions, 4 data vendors (yfinance, Alpha Vantage, Finnhub, Finviz), and 6 LLM providers (OpenAI, Anthropic, Google, xAI, OpenRouter, Ollama).

## 3-Tier LLM System

| Tier | Config Key | Default Model | Purpose |
|------|-----------|---------------|---------|
| Quick | `quick_think_llm` | `gpt-5-mini` | Analysts, scanners — fast responses |
| Mid | `mid_think_llm` | `None` (falls back to quick) | Bull/bear researchers, trader, deep dive |
| Deep | `deep_think_llm` | `gpt-5.2` | Research manager, risk manager, macro synthesis |

Each tier has optional `_{tier}_llm_provider` and `_{tier}_backend_url` overrides. All fall back to top-level `llm_provider` (`"openai"`) and `backend_url` (`"https://api.openai.com/v1"`).

Source: `tradingagents/default_config.py`

## LLM Provider Factory

| Provider | Config Value | Client | Notes |
|----------|-------------|--------|-------|
| OpenAI | `"openai"` | `ChatOpenAI` | `openai_reasoning_effort` supported |
| Anthropic | `"anthropic"` | `ChatAnthropic` | — |
| Google | `"google"` | `ChatGoogleGenerativeAI` | `google_thinking_level` supported |
| xAI | `"xai"` | `ChatOpenAI` (OpenAI-compat) | `reasoning_effort` supported |
| OpenRouter | `"openrouter"` | `ChatOpenAI` (OpenAI-compat) | `reasoning_effort` supported |
| Ollama | `"ollama"` | `ChatOpenAI` (OpenAI-compat) | Uses configured `base_url`, never hardcode localhost |

Source: `tradingagents/llm_clients/`

## Data Vendor Routing

| Vendor | Role | Capabilities |
|--------|------|-------------|
| yfinance | Primary (free) | OHLCV, fundamentals, news, screener, sector/industry, indices |
| Alpha Vantage | Fallback | OHLCV, fundamentals, news, sector ETF proxies, market movers |
| Finnhub | Specialized | Insider transactions (primary), earnings calendar, economic calendar |
| Finviz | Smart Money (best-effort) | Institutional screeners via `finvizfinance` web scraper — insider buys, unusual volume, breakout accumulation; graceful degradation on failure |

Routing: 2-level dispatch — category-level (`data_vendors` config) + tool-level (`tool_vendors` config). Fail-fast by default; only 5 methods in `FALLBACK_ALLOWED` get cross-vendor fallback (ADR 011).

Source: `tradingagents/dataflows/interface.py`

## Trading Pipeline

```
START ──┬── Market Analyst (quick) ── tools_market ──┐
        ├── Social Analyst (quick) ── tools_social ──┤
        ├── News Analyst (quick) ── tools_news ───────┼── Bull Researcher (mid) ⇄ Bear Researcher (mid)
        └── Fundamentals Analyst (quick) ── tools_fund─┘         │ (max_debate_rounds)
                                                          Research Manager (deep)
                                                                  │
                                                            Trader (mid)
                                                                  │
                                                  Aggressive ⇄ Neutral ⇄ Conservative (quick)
                                                         (max_risk_discuss_rounds)
                                                                  │
                                                            Risk Judge (deep)
```

Analysts run in parallel → investment debate → trading plan → risk debate → final decision.

Source: `tradingagents/graph/trading_graph.py`, `tradingagents/graph/setup.py`

## Scanner Pipeline

```
START ──┬── Geopolitical Scanner (quick) ──────────────────────┐
        ├── Market Movers Scanner (quick) ─────────────────────┤
        └── Sector Scanner (quick) ── Smart Money Scanner ─────┴── Industry Deep Dive (mid) ── Macro Synthesis (deep) ── END
                                         (quick, Finviz)
```

- **Phase 1a** (parallel): geopolitical, market_movers, sector scanners
- **Phase 1b** (sequential after sector): smart_money_scanner — uses sector rotation context when running Finviz screeners (insider buys, unusual volume, breakout accumulation)
- **Phase 2**: Industry deep dive cross-references all 4 Phase 1 outputs
- **Phase 3**: Macro synthesis applies **Golden Overlap** — cross-references smart money tickers with top-down macro thesis to assign high/medium/low conviction; produces top 8-10 watchlist as JSON

Source: `tradingagents/graph/scanner_graph.py`, `tradingagents/graph/scanner_setup.py`

## Pipeline Bridge

Scanner JSON output → `MacroBridge.load()` → parse into `MacroContext` + `list[StockCandidate]` → `filter_candidates()` by conviction → `run_all_tickers()` (async, `max_concurrent=2`) → per-ticker `TradingAgentsGraph.propagate()` → `save_results()` (per-ticker `.md` + `summary.md` + `results.json`).

Source: `tradingagents/pipeline/macro_bridge.py`

## Unified Report Paths

All generated artifacts live under `reports/daily/{YYYY-MM-DD}/`:

```
reports/
└── daily/{YYYY-MM-DD}/
    ├── daily_digest.md            # consolidated daily report (all runs appended)
    ├── market/                    # scan results (geopolitical_report.md, etc.)
    ├── {TICKER}/                  # per-ticker analysis / pipeline
    │   ├── 1_analysts/
    │   ├── complete_report.md
    │   └── eval/full_states_log.json
    └── summary.md                 # pipeline combined summary
```

Helper functions: `get_daily_dir()`, `get_market_dir()`, `get_ticker_dir()`, `get_eval_dir()`, `get_digest_path()`.

Source: `tradingagents/report_paths.py`

## Daily Digest & NotebookLM Sync

After every `analyze`, `scan`, or `pipeline` run, the CLI:
1. Calls `append_to_digest(date, entry_type, label, content)` → appends a timestamped section to `reports/daily/{date}/daily_digest.md` (creates the file on first run)
2. Calls `sync_to_notebooklm(digest_path, date)` → finds the existing source titled `Daily Trading Digest ({date})` inside the configured NotebookLM notebook, deletes it if it exists, and then uploads the updated file content via `nlm source add --text --wait`.

This ensures there is a single, up-to-date source per day in the user's NotebookLM workspace. `scan` consolidates all 5 macro reports into this digest.

`NOTEBOOKLM_ID` env var controls the target notebook. If unset, the sync step is silently skipped (opt-in).
Source: `tradingagents/daily_digest.py`, `tradingagents/notebook_sync.py`

## Observability

`RunLogger` accumulates structured events (JSON-lines) for a single run. Four event kinds: `llm` (model, agent, tokens in/out, latency), `tool` (tool name, args, success, latency), `vendor` (method, vendor, success, latency), `report` (path). Thread-safe via `_lock`.

Integration points:
- **LLM calls**: `_LLMCallbackHandler` (LangChain `BaseCallbackHandler`) — attach as callback to LLM constructors or graph invocations. Extracts model name from `invocation_params` / `serialized`, token counts from `usage_metadata`.
- **Vendor calls**: `log_vendor_call()` — called from `route_to_vendor`.
- **Tool calls**: `log_tool_call()` — called from `run_tool_loop()`.
- **Context propagation**: `set_run_logger()` / `get_run_logger()` use `contextvars.ContextVar` for passing logger to vendor/tool layers without changing signatures. Asyncio-safe (isolated per task).

`RunLogger.summary()` returns aggregated stats (total tokens, model breakdown, vendor success/fail counts). `RunLogger.write_log(path)` writes all events + summary to a JSON-lines file.

Source: `tradingagents/observability.py`

## CLI Architecture

3 Typer commands: `analyze` (interactive per-ticker), `scan` (macro scanner), `pipeline` (scan → filter → deep dive). Rich-based live UI with `MessageBuffer` (deque-backed state manager tracking agent status, reports, tool calls, defined in `cli/main.py`) and `StatsCallbackHandler` (token/timing stats, defined in `cli/stats_handler.py`). 7-step interactive questionnaire in `analyze` for provider/model selection.

Source: `cli/main.py`, `cli/stats_handler.py`

## AgentOS — Visual Observability Layer

Full-stack web UI for monitoring and controlling agent execution in real-time.

### Architecture

```
┌──────────────────────────────────┐       ┌───────────────────────────────────┐
│  Frontend (React + Vite 8)       │       │  Backend (FastAPI)                │
│  localhost:5173                   │◄─WS──►│  127.0.0.1:8088                  │
│                                  │       │                                   │
│  Dashboard (2 pages via sidebar) │       │  POST /api/run/{type} — queue run │
│  ├─ dashboard: graph+terminal    │       │  WS /ws/stream/{run_id} — execute │
│  └─ portfolio: PortfolioViewer   │       │  GET /api/portfolios/* — data     │
│                                  │       │                                   │
│  ReactFlow (live agent graph)    │       │  LangGraphEngine                  │
│  Terminal (event stream)         │       │  ├─ run_scan()                    │
│  MetricHeader (Sharpe/regime)    │       │  ├─ run_pipeline()                │
│  Param panel (date/ticker/id)    │       │  ├─ run_portfolio()               │
│                                  │       │  └─ run_auto() [scan→pipe→port]   │
└──────────────────────────────────┘       └───────────────────────────────────┘
```

### Run Types

| Type | REST Trigger | WebSocket Executor | Description |
|------|-------------|-------------------|-------------|
| `scan` | `POST /api/run/scan` | `run_scan()` | 4-node macro scanner (3 parallel + smart money) |
| `pipeline` | `POST /api/run/pipeline` | `run_pipeline()` | Per-ticker trading analysis |
| `portfolio` | `POST /api/run/portfolio` | `run_portfolio()` | Portfolio manager workflow |
| `auto` | `POST /api/run/auto` | `run_auto()` | Sequential: scan → pipeline → portfolio |

REST endpoints only queue runs (in-memory store). WebSocket is the sole executor — streaming LangGraph events to the frontend in real-time.

### Event Streaming

`LangGraphEngine._map_langgraph_event()` maps LangGraph v2 events to 4 frontend event types:

| Event | LangGraph Trigger | Content |
|-------|------------------|---------|
| `thought` | `on_chat_model_start` | Prompt text, model name |
| `tool` | `on_tool_start` | Tool name, arguments |
| `tool_result` | `on_tool_end` | Tool output |
| `result` | `on_chat_model_end` | Response text, token counts, latency |

Each event includes optional `prompt` and `response` full-text fields. Model name extraction uses 3 fallbacks: `invocation_params` → serialized kwargs → `metadata.ls_model_name`. Event mapping uses try/except per type and `_safe_dict()` helper to prevent crashes from non-dict metadata.

### Portfolio API

| Endpoint | Description |
|----------|-------------|
| `GET /api/portfolios/` | List all portfolios |
| `GET /api/portfolios/{id}` | Get portfolio details |
| `GET /api/portfolios/{id}/summary` | Top-3 metrics (Sharpe, regime, drawdown) |
| `GET /api/portfolios/{id}/latest` | Holdings, trades, snapshot with field mapping |

The `/latest` endpoint maps backend model fields to frontend shape: `Holding.shares` → `quantity`, `Portfolio.portfolio_id` → `id`, `cash` → `cash_balance`, `Trade.trade_date` → `executed_at`. Computed runtime fields (`market_value`, `unrealized_pnl`) are included from enriched Holding properties.

### Pipeline Recursion Limit

`run_pipeline()` passes `config={"recursion_limit": propagator.max_recur_limit}` (default 100) to `astream_events()`. Without it, LangGraph defaults to 25 which is too low for the debate + risk cycles.

Source: `agent_os/backend/`, `agent_os/frontend/`

## Key Source Files

| File | Purpose |
|------|---------|
| `tradingagents/default_config.py` | All config keys, defaults, env var override pattern |
| `tradingagents/graph/trading_graph.py` | `TradingAgentsGraph` class, LLM wiring, tool nodes |
| `tradingagents/graph/scanner_graph.py` | `ScannerGraph` class, 3-phase workflow |
| `tradingagents/graph/portfolio_graph.py` | `PortfolioGraph` class, 6-node portfolio workflow |
| `tradingagents/graph/setup.py` | `GraphSetup` — agent node creation, graph compilation |
| `tradingagents/graph/scanner_setup.py` | `ScannerGraphSetup` — scanner graph compilation |
| `tradingagents/graph/portfolio_setup.py` | `PortfolioGraphSetup` — portfolio graph compilation |
| `tradingagents/dataflows/interface.py` | `route_to_vendor`, `VENDOR_METHODS`, `FALLBACK_ALLOWED` |
| `tradingagents/agents/utils/tool_runner.py` | `run_tool_loop()`, `MAX_TOOL_ROUNDS=5`, `MIN_REPORT_LENGTH=2000` |
| `tradingagents/agents/utils/agent_states.py` | `AgentState`, `InvestDebateState`, `RiskDebateState` |
| `tradingagents/agents/utils/scanner_states.py` | `ScannerState`, `_last_value` reducer |
| `tradingagents/pipeline/macro_bridge.py` | `MacroBridge`, data classes, pipeline orchestration |
| `tradingagents/agents/utils/json_utils.py` | `extract_json()` — handles DeepSeek R1 markdown wrapping |
| `cli/main.py` | CLI commands, `MessageBuffer`, Rich UI, interactive setup |
| `tradingagents/report_paths.py` | Unified report path helpers (`get_market_dir`, `get_ticker_dir`, etc.) |
| `tradingagents/observability.py` | `RunLogger`, `_LLMCallbackHandler`, structured event logging |
| `tradingagents/dataflows/config.py` | `set_config()`, `get_config()`, `initialize_config()` |
| `agent_os/backend/main.py` | FastAPI app, CORS, route mounting, health check |
| `agent_os/backend/services/langgraph_engine.py` | `LangGraphEngine` — run orchestration, LangGraph event mapping |
| `agent_os/backend/routes/websocket.py` | WebSocket streaming endpoint (`/ws/stream/{run_id}`) |
| `agent_os/backend/routes/runs.py` | REST run triggers (`POST /api/run/{type}`) |
| `agent_os/backend/routes/portfolios.py` | Portfolio REST API with field mapping |
| `agent_os/frontend/src/Dashboard.tsx` | 2-page dashboard, graph + terminal + controls |
| `agent_os/frontend/src/hooks/useAgentStream.ts` | WebSocket hook, `AgentEvent` type, status tracking |
| `agent_os/frontend/src/components/AgentGraph.tsx` | ReactFlow live agent graph visualization |
| `agent_os/frontend/src/components/PortfolioViewer.tsx` | Holdings table, trade history, snapshot summary |
| `agent_os/frontend/src/components/MetricHeader.tsx` | Top-3 portfolio metrics display |
