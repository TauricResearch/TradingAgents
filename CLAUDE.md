# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[dev]"          # dev install (ruff, pytest); add ",bedrock" for the Bedrock provider
pytest -q                        # full suite (integration tests excluded by default via pyproject addopts)
pytest tests/test_vendor_routing.py::test_name -q   # single test
pytest -m integration            # tests that hit real services; run only when asked
ruff check .                     # lint (CI lints the whole repo with the strict select in pyproject)
tradingagents                    # interactive CLI (or: python -m cli.main)
tradingagents --ticker NVDA --date 2026-09-23 --analysts market,news --save --no-show   # headless run
tradingagents backtest NVDA,AAPL --start 2026-06-01 --end 2026-08-01 --every 7
```

CI runs the suite on Python 3.11–3.14 plus once with `TZ=America/New_York` (a test that only passes in UTC fails there), a no-dev-extras install that must import `tradingagents` and `cli.main` (catches undeclared runtime deps), and `ruff check .`. Don't run `ruff format` repo-wide; formatter adoption is deliberately deferred.

## Test harness (tests/conftest.py)

- Blanks every `TRADINGAGENTS_*` env var and redirects results/cache/memory log to a temp dir **before** the package is imported, because `DEFAULT_CONFIG` folds the environment in at import time.
- An autouse fixture blocks all network access (sockets and yfinance's curl_cffi). A test that needs the network must be marked `integration`; otherwise mock the vendor.
- Many invariants are enforced by AST/source-scanning tests rather than by convention, e.g. `test_layering.py` (only `tradingagents/dataflows/` may import vendor libs like `yfinance`), `test_i18n_coverage.py` (every report-producing agent must call `get_language_instruction()`; add new agents to its list), `test_prompt_integrity.py`, `test_risk_router_path_map.py`.

## Architecture

**Entry points.** `TradingAgentsGraph` (`tradingagents/graph/trading_graph.py`) is the library API: `propagate(ticker, date, portfolio=None)` returns `(state, decision)`, `save_reports(...)` writes the report tree/HTML. The Typer CLI (`cli/`, entry `cli.main:app`) wraps it; `cli/run.py` drives a run, `cli/display.py` the Rich live view, `cli/prefs.py` remembers the last run's answers. `tradingagents/backtest.py` runs the same pipeline over a ticker × date grid with its own memory log.

**Graph** (`tradingagents/graph/setup.py`, LangGraph). Selected analysts (market, social/sentiment, news, fundamentals) run **in parallel**, each as its own compiled subgraph with a private message history that returns only its report key; after `max_tool_rounds` it is forced to wrap up. A "Memory Log" node runs alongside them, settling past decisions. Then: Bull ↔ Bear debate → Research Manager → Trader → Aggressive/Conservative/Neutral risk debate → Portfolio Manager. Debate routing lives in `conditional_logic.py`; every conditional edge must use the full `DEBATE_PATH_MAP` / `RISK_ANALYSIS_PATH_MAP` so a stray router return can't crash the graph. State types are in `agents/state.py`. Optional SQLite checkpoint resume is in `graph/checkpointer.py` (per-ticker DB, keyed on a config signature).

**Two LLM tiers.** The quick tier serves analysts, researchers, debaters and trader; the deep tier serves the Research and Portfolio Managers. Each tier may have its own provider/backend URL (`quick_think_provider`, `deep_think_backend_url`, …). Clients are built by `llm_clients/factory.py` (`create_tier_client`): Anthropic, Google, Azure, Bedrock have native clients; everything else (OpenAI, xAI, DeepSeek, Qwen, GLM, Ollama, OpenRouter, `openai_compatible`, the ChatGPT-plan `chatgpt` provider, …) goes through the `OPENAI_COMPATIBLE_PROVIDERS` registry in `openai_client.py`. API-key env var names live in `api_key_env.py`; CLI model lists in `model_catalog.py`; per-model capability quirks in `capabilities.py`. Provider SDKs are imported lazily.

**Structured agents.** Research Manager, Trader and Portfolio Manager use `with_structured_output` with Pydantic schemas (`agents/schemas.py`) via `agents/structured.py`, falling back to free text if the provider/model can't comply, then render to markdown. The final rating is extracted in `agents/rating.py`.

**Data layer** (`tradingagents/dataflows/`). Agent tools (`agents/tools.py`) call `route_to_vendor(method, ...)` in `dataflows/router.py`, which maps methods → categories → the configured vendor chain (`data_vendors` / `tool_vendors` in config; comma-separated = ordered fallback, and the router never falls back to a vendor the user didn't list). Vendors live in `dataflows/vendors/` and must signal failure with the `VendorError` hierarchy in `dataflows/errors.py` (`NoMarketDataError`, `VendorUnavailableError`, `VendorNotConfiguredError`); the router turns these into `NO_DATA_AVAILABLE` / `DATA_UNAVAILABLE` sentinel strings telling the model not to fabricate. Optional categories (macro, prediction markets) degrade to a sentinel; core categories raise.

**Point-in-time integrity is a core invariant.** Dated tools take `trade_date` from graph state via `InjectedState` and clamp any model-requested dates with `as_of` / `as_of_window` (`dataflows/date_window.py`); news/social items are filtered to the window, undated items are dropped for historical runs, and live snapshots (e.g. Yahoo statements, insider trades) are withheld from past-dated runs. SEC EDGAR serves statements as originally filed. Any new dated data path must follow these rules; many `test_*_lookahead.py` tests guard them.

**Config.** `tradingagents/default_config.py` builds `DEFAULT_CONFIG` at import, applying `TRADINGAGENTS_*` env overrides from the `_ENV_OVERRIDES` table (add a row there to expose a new key; values are coerced to the default's type and invalid values raise). `.env` / `.env.enterprise` are loaded on import. `dataflows/config.py` holds the active config and binds a per-run config in a `ContextVar` so concurrent graphs in one process read their own vendor settings.

**Memory** (`tradingagents/memory/`). Each completed run appends to a markdown decision log (`~/.tradingagents/memory/trading_memory.md`). `settlement.py` later computes realised return and alpha vs. the regional benchmark (`benchmark_map` by ticker suffix), measured from the first close after the decision date over `holding_period_days`; `reflection.py` writes a lesson that the Portfolio Manager reads in later runs.

**Instrument identity.** `agents/context.py` resolves the company identity from the ticker once, deterministically, before agents run; `dataflows/symbols.py` normalises exchange-suffixed tickers and crypto symbols and sanitises tickers used in file paths (`safe_ticker_component`).

## Conventions

- Comments and docstrings explain *why*, often citing the GitHub issue number (`#1088`); keep that style.
- User-facing changes are recorded in `CHANGELOG.md` (Keep a Changelog format, with an "Upgrading from" section for breaking changes). The version is `tradingagents.__version__`.
- Internal agent debate stays in English; only report-producing output follows `output_language`.
