# Refactor Roadmap

This roadmap turns the fork into a personal stock research platform while
keeping the current TradingAgents workflow runnable during migration.

## PR 1 - Foundation Contracts

Status: started.

Scope:

- Add architecture docs.
- Add `tradingagents.research_platform` namespace.
- Add contract models for data, agent output, backtesting, and risk.
- Add unit tests for validation and basic risk review.

Acceptance criteria:

- No legacy graph behavior changes.
- Contract tests pass without API keys or network access.
- The new modules import without loading LangGraph or LLM clients.

## PR 2 - Data Provider Wrapper

Scope:

- Wrap existing `tradingagents/dataflows` functions behind a provider class.
- Normalize price bars, fundamentals, and news into contract models.
- Add provenance for vendor, retrieved time, source url, and as-of date.
- Add cache interface stubs for SQLite/Parquet.

Acceptance criteria:

- Existing yfinance path can produce `PriceBar` records.
- Data calls can be tested with fixtures.
- No lookahead tests cover news and price data boundaries.

## PR 3 - Agent Artifact Output

Scope:

- Extend structured agent schemas toward `AnalystNote`, `InvestmentThesis`, and
  `TradeSignal`.
- Add renderers that keep markdown reports readable.
- Keep backward-compatible markdown for legacy graph consumers.

Acceptance criteria:

- Agent outputs validate as Pydantic models.
- Failed validation falls back safely and does not enter backtest/risk layers.
- Tests cover each artifact renderer.

## PR 4 - Backtest Engine MVP

Scope:

- Add daily-bar simulation from `TradeSignal`.
- Add commission, slippage, cash, positions, and equity curve.
- Add metrics: total return, CAGR, max drawdown, volatility, Sharpe, win rate,
  turnover, and exposure.
- Add timing guards to reject future data.

Acceptance criteria:

- A fixture signal set can run fully offline.
- Lookahead violations fail loudly.
- Metrics are deterministic across runs.

## PR 5 - Risk Engine MVP

Scope:

- Add policy object for max single-name exposure, confidence floor, drawdown
  limit, volatility limit, and default position size.
- Add deterministic `RiskReview`.
- Add a wrapper that can consume legacy final decisions and new `TradeSignal`.

Acceptance criteria:

- Oversized signals are capped or rejected.
- Low-confidence signals are rejected.
- Drawdown limit can halt new risk.

## PR 6 - Research Report MVP

Scope:

- Generate a personal ticker report from normalized artifacts.
- Include data provenance, analyst notes, thesis, backtest summary, and risk
  review.
- Keep markdown as the first output format.

Acceptance criteria:

- A report can be generated from fixtures without LLM/network calls.
- The report clearly separates facts, model commentary, and risk decisions.

## PR 7 - Cockpit MVP

Scope:

- Add a local UI for watchlist, ticker workspace, thesis board, backtest lab,
  and risk dashboard.
- Prefer a thin API over the artifact store before building heavy UI features.

Acceptance criteria:

- Local user can inspect one ticker from data snapshot through report.
- No broker integration is present.
- UI reads artifacts produced by the same backend contracts.

## Current Cutover Map

| Legacy area | Current role | Target direction |
| --- | --- | --- |
| `tradingagents/dataflows` | Vendor functions and routing | Wrapped behind provider contracts |
| `tradingagents/agents/schemas.py` | Structured outputs for legacy graph | Expanded into reusable artifacts |
| `tradingagents/graph` | End-to-end LangGraph orchestration | Split into research flows over artifacts |
| `tradingagents/reporting.py` | Markdown tree from graph state | Report from validated artifacts |
| Risk debator agents | LLM risk discussion | Commentary around deterministic policy |
