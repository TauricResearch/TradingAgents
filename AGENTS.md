# AGENTS.md

Guidance for coding agents working in this repository. The user-facing docs are
in [README.md](README.md); release history and upgrade notes are in
[CHANGELOG.md](CHANGELOG.md).

## What this is

TradingAgents is a multi-agent LLM framework that analyzes one instrument on one
date and returns a 5-tier rating (Buy / Overweight / Hold / Underweight / Sell).
Analysts write reports, bull and bear researchers debate, a Research Manager
sets the plan, the Trader proposes a transaction, three risk analysts debate
it, and the Portfolio Manager makes the final call. Orchestration is LangGraph.
It is a research tool: nothing here places orders or gives financial advice.

## Setup and commands

Python 3.10–3.13. Install editable with the dev extras:

```bash
pip install -e ".[dev]"
```

| Task | Command |
|---|---|
| Full test suite | `pytest -q` |
| One file | `pytest tests/test_portfolio_review.py -v` |
| Lint (must be clean) | `ruff check .` |
| Interactive run | `tradingagents` |
| Run with holdings | `tradingagents --portfolio book.json` |
| Backtest a grid | `tradingagents backtest NVDA,AAPL --start 2026-01-05 --end 2026-03-02` |
| Portfolio review | `tradingagents review book.json --metrics-only` |

CI (`.github/workflows/ci.yml`) runs pytest on 3.10–3.13, once more under
`TZ=America/New_York`, runs `ruff check .` across the whole repo, and checks
that a plain `pip install .` can import `tradingagents` and `cli.main`. A change
is not done until all three would pass. A new runtime import must be declared in
`pyproject.toml` `dependencies`.

Real runs need an LLM provider key in `.env` (see `.env.example`). Tests never do.

## Layout

```
tradingagents/
  graph/            LangGraph wiring: trading_graph.py (TradingAgentsGraph, propagate),
                    setup.py, conditional_logic.py, propagation.py, checkpointer.py,
                    reflection.py, settlement.py (scores past decisions vs benchmark)
  agents/
    analysts/       market, sentiment, news, fundamentals
    researchers/    bull, bear
    managers/       research_manager, portfolio_manager, portfolio_reviewer
    risk_mgmt/      aggressive, conservative, neutral debaters
    trader/
    schemas.py      Pydantic output schemas + render_* back to markdown
    structured.py   bind_structured / invoke_structured_or_freetext
    context.py      instrument identity, portfolio and language context for prompts
    rating.py       5-tier vocabulary, parse_rating, the REVIEW sentinel
    tools.py        LangChain tools the analysts call
  dataflows/
    router.py       route_to_vendor: category -> vendor chain with fallback
    vendors/        yahoo/, alpha_vantage/, sec_edgar, fred, polymarket, reddit, stocktwits
    config.py       get_config / set_config / run_config
    errors.py       VendorError hierarchy
    date_window.py, symbols.py, net.py
  llm_clients/      provider clients, factory, model_catalog, capability checks
  portfolio.py      PortfolioContext: positions, options, cash (optional run input)
  portfolio_review.py  whole-book metrics + per-underlying runs + reviewer
  option_pricing.py    Black-Scholes value, greeks, implied volatility
  backtest.py       grid runs scored from the decision log
  decision_log.py   persistent memory of decisions and their outcomes
  reporting.py      markdown report tree
  default_config.py DEFAULT_CONFIG and TRADINGAGENTS_* env overrides
cli/                Typer app (main.py), interactive flow (run.py), display
tests/              pytest, one file per behavior
```

## Invariants

These rules are enforced by tests or were written after real bugs. Keep them.

- **Point in time.** A run dated D may only see data available on D: prices,
  fundamentals (SEC EDGAR as filed), news, social posts, macro, and decision-log
  lessons. Any new dated path filters to the trade date and gets a look-ahead
  test (see `test_*_lookahead.py`, `test_memory_pointintime.py`).
- **Vendor libraries stay in the data layer.** Only `tradingagents/dataflows/`
  may import `yfinance` or other vendor SDKs (`tests/test_layering.py`). Vendor
  failures are raised as `VendorError` subclasses from `dataflows/errors.py`, so
  an outage is never reported as a fact about the market.
- **No silent Hold.** An unreadable decision becomes `REVIEW`, never `Hold`. Use
  `parse_rating` and `is_review` from `agents/rating.py`.
- **Portfolio context has three distinct states:** a book with positions, a flat
  book (empty `positions`), and no context (`None`). Never treat "not provided"
  as flat. The research team stays blind to the book, so the bull and bear
  cases aren't anchored by it.
- **Structured agents** bind their schema with `bind_structured` and call
  `invoke_structured_or_freetext`, so a provider without structured output still
  works. Their prompts include `NO_EXTERNAL_TOOLS`. The schema's field
  descriptions are the output instructions. The rendered markdown shape is read
  by the decision log, CLI and reports, so don't rename its section headers.
- **Output language.** Every agent whose text reaches a report appends
  `get_language_instruction()` and is listed in `tests/test_i18n_coverage.py`.
- **Paths from user input** (tickers, run ids) go through
  `safe_ticker_component` before they become file or directory names.
- **Text files** are opened with `encoding="utf-8"`. Windows is a supported
  platform, and its default codepage corrupts non-ASCII reports.
- **Checkpoint signature.** Anything that changes graph shape or run inputs
  (analysts, debate depth, asset type, portfolio) is part of `_run_signature`,
  so a resume never continues a different run.

## Conventions

- Ruff with `E, W, F, I, B, UP, C4, SIM`; line length 100 (E501 ignored); isort
  with `combine-as-imports`. `from __future__ import annotations` in new modules.
- Module docstrings explain the purpose and the scope limits (what the module
  deliberately does not do). Comments explain why, and cite the issue number
  when a line exists because of a bug (`(#1201)`).
- New config keys go in `DEFAULT_CONFIG`. To make one settable from the
  environment, add a row to `_ENV_OVERRIDES`; the value is coerced from the
  default's type.
- A broad `except Exception` is acceptable only where one failure must not end a
  batch (a backtest cell, one holding in a review). It is logged and recorded in
  the result, never swallowed silently.
- User-visible changes get a CHANGELOG entry in Keep a Changelog form. Breaking
  changes go first in the release, under "Upgrading from …".

## Tests

- Every test carries a marker: `@pytest.mark.unit`, `integration` or `smoke`
  (`--strict-markers` is on).
- `tests/conftest.py` blocks socket connections for everything not marked
  `integration`, and blanks `TRADINGAGENTS_*` variables, so a contributor's
  `.env` can't change the defaults the suite asserts on. Unit tests
  monkeypatch the graph, LLM or price loader instead (see `_FakeGraph` in
  `tests/test_backtest.py` and `tests/test_portfolio_review.py`).
- Tests must pass in any timezone. Build dates explicitly and never rely on
  local midnight being UTC.
- Test module docstrings state the behavior being protected; test names read as
  sentences (`test_a_mark_from_another_day_is_not_used`).

## Adding things

- **An analyst or agent:** create it under `agents/`, wire it in
  `graph/setup.py` (and `conditional_logic.py` if it routes), add state fields
  in `agents/state.py`, include it in `_log_state` and `reporting.py` if it
  writes a report, and register it in the i18n coverage test.
- **A data vendor:** add a module under `dataflows/vendors/`, register its
  methods in `dataflows/router.py`, raise `NoMarketDataError`,
  `VendorRateLimitError` or `VendorNotConfiguredError` on failure, enforce the
  date cutoff, and add routing and look-ahead tests.
- **An LLM provider or model:** `llm_clients/factory.py`, `model_catalog.py`
  and `capabilities.py`, plus the provider registry tests.

## Don'ts

- Don't commit `.env`, API keys, or personal portfolio or brokerage files. Keep
  real holdings JSON outside the repo.
- Don't add order execution or a broker integration. Backtesting evaluates
  decision quality and is not a portfolio simulator (see the `backtest.py`
  docstring).
- Don't make network calls in unit tests, and don't add a real LLM call to the
  default suite.
- Don't write a date-dependent path without a look-ahead test.
