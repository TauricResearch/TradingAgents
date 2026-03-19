<!-- Last verified: 2026-03-19 -->

# Architecture

TradingAgents v0.2.1 is a multi-agent LLM framework using LangGraph. It has 17 agent factory functions, 3 data vendors (yfinance, Alpha Vantage, Finnhub), and 6 LLM providers (OpenAI, Anthropic, Google, xAI, OpenRouter, Ollama).

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
START ──┬── Geopolitical Scanner (quick) ──┐
        ├── Market Movers Scanner (quick) ──┼── Industry Deep Dive (mid) ── Macro Synthesis (deep) ── END
        └── Sector Scanner (quick) ─────────┘
```

Phase 1: 3 scanners run in parallel. Phase 2: Deep dive cross-references all outputs, calls `get_industry_performance` per sector. Phase 3: Macro synthesis produces top-10 watchlist as JSON.

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
- **Thread-local context**: `set_run_logger()` / `get_run_logger()` for passing logger to vendor/tool layers without changing signatures.

`RunLogger.summary()` returns aggregated stats (total tokens, model breakdown, vendor success/fail counts). `RunLogger.write_log(path)` writes all events + summary to a JSON-lines file.

Source: `tradingagents/observability.py`

## CLI Architecture

3 Typer commands: `analyze` (interactive per-ticker), `scan` (macro scanner), `pipeline` (scan → filter → deep dive). Rich-based live UI with `MessageBuffer` (deque-backed state manager tracking agent status, reports, tool calls, defined in `cli/main.py`) and `StatsCallbackHandler` (token/timing stats, defined in `cli/stats_handler.py`). 7-step interactive questionnaire in `analyze` for provider/model selection.

Source: `cli/main.py`, `cli/stats_handler.py`

## Key Source Files

| File | Purpose |
|------|---------|
| `tradingagents/default_config.py` | All config keys, defaults, env var override pattern |
| `tradingagents/graph/trading_graph.py` | `TradingAgentsGraph` class, LLM wiring, tool nodes |
| `tradingagents/graph/scanner_graph.py` | `ScannerGraph` class, 3-phase workflow |
| `tradingagents/graph/setup.py` | `GraphSetup` — agent node creation, graph compilation |
| `tradingagents/graph/scanner_setup.py` | `ScannerGraphSetup` — scanner graph compilation |
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
