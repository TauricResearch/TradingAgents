# IndiaMarketAgents Repo Audit

Date: 2026-06-07
Branch: `india-market-agents`
Upstream: `https://github.com/TauricResearch/TradingAgents.git`

## Current Repo State

- Worktree was clean before this documentation phase.
- Branch is ahead of `upstream/main`.
- `LICENSE` contains Apache License 2.0.
- `NOTICE` preserves upstream attribution to `TauricResearch/TradingAgents`.
- `python --version` fails in this environment because `python` is not on PATH; use `python3`.
- The repo already contains partial IndiaMarketAgents implementation work: India config, ticker validation, India dataflow package, India analyst files, India CLI alias, docs, dashboard, and tests.

## Existing Architecture Summary

The project is still packaged internally as `tradingagents`, with user-facing IndiaMarketAgents branding layered on top.

Key components:

- `pyproject.toml`: Python package metadata, dependencies, pytest markers, and console scripts. It keeps `tradingagents` and adds `indiamarketagents = "cli.main:app"`.
- `cli/main.py`: Typer CLI, interactive beginner flow, `analyze`, `doctor`, streaming display, report writing, India ticker/date validation, and compliance disclaimer display.
- `tradingagents/default_config.py`: default runtime config, environment overrides, LLM settings, India market profile, vendor routing defaults, and benchmark mapping.
- `tradingagents/dataflows/interface.py`: central vendor router. It supports `india`, `yfinance`, and `alpha_vantage`, validates India symbols in India mode, and returns explicit no-data sentinels.
- `tradingagents/graph/trading_graph.py`: main orchestrator. It creates LLM clients, tool nodes, memory log, LangGraph workflow, and defaults to India analyst keys when `market_scope == "india"`.
- `tradingagents/graph/setup.py`: builds the LangGraph node/edge structure for analysts, research debate, trader, risk debate, and portfolio manager.
- `tradingagents/graph/analyst_execution.py`: maps analyst keys to graph node names, tool node names, report keys, and default India analyst selection.
- `tradingagents/agents/*`: prompt factories, structured schemas, and agent helpers.
- `tradingagents/dataflows/india/*`: India-specific symbol handling, calendar, formatting, source wrappers/placeholders, local filings, data quality, macro/flows/sector context.

## Existing Agent Workflow Summary

The graph runs:

1. Selected analyst nodes.
2. Bull and Bear Researchers.
3. Research Manager.
4. Trader.
5. Aggressive, Conservative, and Neutral risk analysts.
6. Portfolio Manager.

In India mode, default selected analysts are:

- `india_market`
- `india_fundamentals`
- `india_news_filings`
- `india_macro_policy`
- `india_flows`
- `india_compliance`

Legacy analyst keys still exist for compatibility: `market`, `social`, `news`, and `fundamentals`.

## Current Data-Source And Vendor Routing Summary

- Default vendor order in India mode is `india,yfinance` for core stock data, technical indicators, fundamentals, and news data.
- `route_to_vendor()` validates symbols with `validate_india_symbol_or_raise()` before India-scope tool calls.
- India wrappers delegate some data to yfinance after India ticker normalization.
- Data-quality helpers provide `DataQuality` metadata and `UNAVAILABLE` responses.
- NSE/BSE and flows modules must remain defensive: blocked or unavailable public data should not crash analysis or produce fabricated values.
- Alpha Vantage remains available as a fallback vendor but should not bypass India scope by default.

## CLI And Report Flow Summary

- CLI app name and help text are IndiaMarketAgents-branded.
- `doctor` runs local checks without live LLM calls.
- `analyze --ticker ... --date ...` supports non-interactive execution, validates India tickers, resolves India trading dates, checks API-key presence, runs the graph, and writes reports.
- `save_report_to_disk()` writes a structured IndiaMarketAgents report directory with section markdown, summary JSON, data-quality JSON, sources, disclaimer, and complete report.
- Report paths use `safe_india_ticker_component()` in India mode.
- Generated reports live under `reports/` by default and must stay out of git.

## Limitations For Indian Markets

- Official NSE/BSE public endpoints can block automation or change schemas.
- Some India data modules are best-effort wrappers/placeholders and need source-by-source verification.
- `README.md` still contains a large upstream TradingAgents body after an IndiaMarketAgents preface.
- The internal package name remains `tradingagents`; this is intentional for now but may surprise new users.
- Some legacy prompts and wording may still use trade/execution language. Future phases should tighten research-only language.
- Real filings ingestion is limited; local filings support should be expanded with tests before relying on it.
- Sector benchmark mapping is intentionally conservative because Yahoo-compatible Indian sector symbols are uneven.

## Proposed India Migration Plan

1. Documentation and handoff: keep `AGENTS.md`, `docs/CODEX_HANDOFF.md`, and `docs/REPO_AUDIT_INDIA.md` current.
2. Rebrand and scope checkpoint: verify CLI branding, India config defaults, India-only ticker validation, env overrides, and tests.
3. Data-source layer: harden local filings, yfinance India wrapper, NSE/BSE placeholders, macro/flows unavailable responses, and data-quality rendering.
4. Agent layer: review India analyst prompts and downstream Researcher/Trader/Risk/Portfolio prompts for India context and research-only language.
5. Report layer: improve report structure, source coverage, data-quality dashboard, and disclaimer consistency.
6. Dashboard layer: keep Streamlit optional and focused on saved report review only; no trading buttons.
7. Security/compliance pass: scan for secrets, generated artifacts, unsafe file writes, path traversal, broker code paths, and fabricated-data risks.
8. Final validation: install, offline tests, doctor, non-India rejection, mocked/no-LLM smoke path, and git cleanliness.

## Files Likely To Be Modified In Future Phases

- `README.md`
- `README_INDIA.md`
- `.env.example.india`
- `docs/CODEX_HANDOFF.md`
- `docs/BEGINNER_SETUP.md`
- `docs/INDIA_COMPLIANCE.md`
- `docs/INDIA_DATA_SOURCES.md`
- `docs/SECURITY.md`
- `cli/main.py`
- `cli/utils.py`
- `tradingagents/default_config.py`
- `tradingagents/dataflows/interface.py`
- `tradingagents/dataflows/india/*`
- `tradingagents/agents/analysts/india_*.py`
- `tradingagents/agents/researchers/*`
- `tradingagents/agents/managers/*`
- `tradingagents/agents/trader/*`
- `tradingagents/agents/risk_mgmt/*`
- `tradingagents/agents/utils/india_market_tools.py`
- `tradingagents/agents/schemas.py`
- `tradingagents/graph/*`
- `dashboard/app.py`
- `tests/test_india_*.py`

## Risks And Trade-Offs

- Full package rename from `tradingagents` to `indiamarketagents` is high risk and not needed for near-term product value.
- NSE/BSE scraping must be avoided or handled conservatively; official/user-provided sources should come first.
- Over-eager yfinance fallback can create false confidence if source coverage is not clearly labeled.
- India-only rejection must happen before network calls and LLM prompts.
- LLM-generated reports can overstate confidence unless data gaps are explicitly carried through prompts and report sections.
- Adding richer dashboard features can accidentally imply trade execution; keep it read-only and report-focused.
