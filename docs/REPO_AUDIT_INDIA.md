# IndiaMarketAgents Repo Audit

Date: 2026-06-07
Branch: `india-market-agents`
Upstream: `https://github.com/TauricResearch/TradingAgents.git`

## Bootstrap Findings

- The working directory initially contained an empty Git repository with no working tree files, no commits, and no remotes.
- `gh` is not installed in this environment, so GitHub fork creation could not be executed locally.
- Added `upstream` remote and checked out `india-market-agents` from `upstream/main`.
- `python` is not available, but `python3` is available.
- Baseline install succeeded with `python3 -m pip install -e .`.
- Baseline tests required installing `pytest`, then passed with `python3 -m pytest`: 310 passed, 1 skipped, 8 warnings.

## Architecture Summary

The upstream project is a Typer CLI and Python package named `tradingagents`.
The main execution path is:

1. `cli/main.py` collects user selections, creates config, initializes `TradingAgentsGraph`, streams graph events, and saves markdown reports.
2. `tradingagents/graph/trading_graph.py` constructs LLM clients, tool nodes, LangGraph workflow, memory logging, state logging, and final signal extraction.
3. `tradingagents/graph/setup.py` wires analyst nodes, research debate nodes, trader, risk debate nodes, and portfolio manager.
4. `tradingagents/graph/analyst_execution.py` defines analyst keys and node/report metadata.
5. `tradingagents/agents/*` holds analyst prompts, researcher prompts, trader/manager prompts, risk prompts, and structured output schemas.
6. `tradingagents/dataflows/interface.py` routes tool calls to yfinance or Alpha Vantage with fallback handling and no-data sentinels.
7. `tradingagents/dataflows/symbol_utils.py` normalizes broad Yahoo symbols, including forex, crypto, futures, and several non-US markets.

## Existing Agents And India Limitations

- Market Analyst: generic technical prompt; can work with `.NS`/`.BO` through Yahoo, but not India-first, not benchmarked by sector, and still uses trading-language framing.
- Fundamentals Analyst: generic company fundamentals prompt; no Indian accounting/unit framing, promoter pledge/shareholding focus, sector lens, or filings-first hierarchy.
- News Analyst: generic macro/news prompt; does not prioritize NSE/BSE announcements, SEBI/RBI policy, Indian filings, or India sector terms.
- Sentiment Analyst: includes Yahoo news, StockTwits, and Reddit. This is US/retail-platform oriented and unsafe as an India default unless data is explicitly available.
- Researcher/Trader/Risk/Portfolio prompts: still use trade execution vocabulary and a US-style Buy/Overweight/Hold/Underweight/Sell framing.
- Compliance guardrails: upstream has research disclaimers in docs, but no India-specific SEBI-style guard agent or report disclaimer enforcement.

## Existing Data Vendors And Fallback Logic

- Config lives in `tradingagents/default_config.py` and is copied through `tradingagents/dataflows/config.py`.
- Vendor routing lives in `tradingagents/dataflows/interface.py`.
- Current vendors: `yfinance`, `alpha_vantage`.
- Fallback order is configured by category or tool and falls back to remaining vendors.
- Empty market data is converted to a clear `NO_DATA_AVAILABLE` sentinel after all vendors are exhausted.
- Existing default benchmark map already includes `.NS` -> `^NSEI` and `.BO` -> `^BSESN`, which is a useful India starting point.

## Existing CLI And Report Flow

- Typer app is named `TradingAgents`.
- `analyze` exists but is interactive-only except checkpoint flags.
- Reports are saved under timestamped `reports/<TICKER>_<TIMESTAMP>/` folders from the CLI, while graph JSON state logs are written under `<results_dir>/<ticker>/TradingAgentsStrategy_logs/`.
- The CLI welcome screen, headers, and panel copy use TradingAgents/Tauric branding.
- The report writer is embedded in `cli/main.py`; there is no independent report generation module yet.

## Files Targeted For First Pass

- `AGENTS.md`
- `NOTICE`
- `.env.example.india`
- `README_INDIA.md`
- `docs/BEGINNER_SETUP.md`
- `docs/INDIA_COMPLIANCE.md`
- `docs/INDIA_DATA_SOURCES.md`
- `docs/ADDING_NEW_INDIAN_AGENT.md`
- `docs/SECURITY.md`
- `config/india_market_holidays.yml`
- `pyproject.toml`
- `cli/main.py`
- `cli/utils.py`
- `cli/static/india_welcome.txt`
- `tradingagents/default_config.py`
- `tradingagents/dataflows/interface.py`
- `tradingagents/dataflows/india/*`
- `tradingagents/agents/__init__.py`
- `tradingagents/agents/analysts/india_*.py`
- `tradingagents/agents/utils/india_market_tools.py`
- `tradingagents/agents/schemas.py`
- `tradingagents/graph/analyst_execution.py`
- `tradingagents/graph/setup.py`
- `tradingagents/graph/trading_graph.py`
- `tradingagents/graph/propagation.py`
- `dashboard/app.py`
- New tests under `tests/test_india_*.py`

## Risks And Trade-Offs

- Full package rename from `tradingagents` to `indiamarketagents` is high-risk and unnecessary for the first pass. Keep internal imports stable and rebrand user-facing surfaces first.
- NSE/BSE endpoints may block automated requests or change format. New India modules must fail closed with explicit unavailable messages and data-quality notes.
- Adding India analyst keys requires graph/state changes. Preserve legacy keys and old tests by adding, not replacing.
- CLI non-interactive mode can instantiate real LLM clients. Add `doctor` and validation paths that do not require live keys; keep full `analyze` behavior explicit.
- Streamlit should be optional to avoid breaking base installs.
- Generated reports, API keys, caches, and local filings must stay out of commits.

## Migration Plan

1. Bootstrap/fork hygiene: preserve Apache 2.0 license, add NOTICE attribution, document missing `gh`.
2. Rebrand safe surfaces: CLI app alias, welcome art, report/disclaimer text, docs.
3. India scope: default `market_scope=india`, India ticker validation, environment overrides, India benchmark defaults, India macro queries.
4. Data integrity: India data-quality object, no-data sentinel helpers, local filings support, official-source placeholders.
5. Graph integration: India analyst keys and tool nodes, default India analyst set, legacy mode preserved through config.
6. CLI: doctor command, India ticker/date validation, beginner copy, safer report paths.
7. Reports/dashboard/docs: report structure, compliance disclaimers, optional Streamlit dashboard.
8. Tests: offline unit tests for symbol handling, calendar, formatting, fallback, CLI doctor, path safety, data quality, and disclaimer rendering.
9. Final validation: install, offline tests, doctor, non-India rejection, git diff review, commit.
