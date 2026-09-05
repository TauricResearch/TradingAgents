# Personal Stock Research Platform

This fork is moving from a trading-agent demo toward a personal stock research
platform. The project should keep the useful TradingAgents ideas - analyst
roles, debate, and structured decisions - while separating deterministic data,
backtesting, and risk controls from LLM prose.

## Product Shape

The first usable product is a local research cockpit:

- Watchlist and ticker workspace.
- Deterministic market, fundamentals, news, and macro data snapshots.
- Structured analyst notes and investment theses.
- Signal backtests with clear lookahead rules.
- Risk review before any action is treated as actionable.
- Markdown/HTML/PDF research reports generated from validated artifacts.

This is not an automated broker or execution system. The platform can produce
research, watchlist alerts, backtests, and position guidance for a personal
investor, but order placement stays outside the project unless explicitly added
later.

## Reference Boundaries

TradingAgents is the base fork and provides:

- Existing LangGraph orchestration.
- Analyst, researcher, trader, and risk-agent roles.
- Vendor routing examples in `tradingagents/dataflows`.
- Existing structured output work in `tradingagents/agents/schemas.py`.
- Existing report-tree writer in `tradingagents/reporting.py`.

FinRobot is only a reference for product direction:

- Equity research cockpit flow.
- Deterministic valuation and calculation paths.
- Report generation sequence.
- Separation between calculations and LLM-written narrative.

Do not copy FinRobot internals, prompts, templates, or proprietary structure.
Use it as a workflow reference only.

## Target Architecture

The project should converge on these layers:

```text
tradingagents/
  research_platform/
    data_contracts.py       # data provider contracts and normalized records
    agent_contracts.py      # validated analyst notes, theses, and signals
    backtest_contracts.py   # simulation inputs, outputs, and timing guards
    risk_contracts.py       # deterministic risk policy and review artifacts
  dataflows/                # legacy vendor functions, migrated behind contracts
  agents/                   # legacy agent implementations, migrated to contracts
  graph/                    # legacy orchestration, later split into research flows
  reporting.py              # legacy markdown writer, later fed by contracts
```

The new `research_platform` namespace is intentionally contract-first. It gives
later work stable model boundaries before replacing existing data and agent
internals.

## Layer Ownership

### Data Layer

Owns provider adapters, normalized records, caching, data provenance, and
as-of-date discipline. It should expose typed records such as `PriceBar`,
`FundamentalSnapshot`, and `NewsItem`.

Rules:

- Every record carries provider, retrieval time, and `as_of_date`.
- Backtests may only read data available at or before the decision date.
- Vendor failures return typed errors or explicit unavailable states, not model
  guesses.
- Legacy `dataflows` functions are wrapped first, then gradually replaced.

### Agent Output Layer

Owns schemas that LLMs must satisfy before downstream systems consume results.
It should expose `AnalystNote`, `InvestmentThesis`, and `TradeSignal`.

Rules:

- LLM output is validated before it reaches backtesting, reporting, or risk.
- Evidence references are explicit and tied to a data/source id.
- Free text is allowed in summaries, but decisions must be structured.
- Agent prompts should ask for evidence and invalidation conditions.

### Backtest Layer

Owns deterministic simulation, portfolio accounting, and metrics.

Rules:

- Inputs are validated signals, not raw LLM prose.
- Execution assumptions are explicit: commission, slippage, shorting, and
  rebalance cadence.
- Timing guards reject signals that use future information.
- Results expose trades, equity curve, metrics, and assumptions.

### Risk Layer

Owns policy checks and final risk review artifacts.

Rules:

- Risk decisions are deterministic and reproducible.
- LLM risk debate can explain risks, but policy checks control approval.
- Position caps, drawdown limits, volatility limits, and confidence floors are
  checked before a signal is actionable.
- The final artifact is a `RiskReview`, not prose.

### Reporting And Cockpit

Owns user-facing research outputs.

Rules:

- Reports are generated from validated data, notes, theses, backtests, and risk
  reviews.
- Every chart or numeric statement should trace back to a deterministic artifact.
- The cockpit should be built after contracts stabilize, not before.

## Migration Strategy

1. Add contract models and tests without changing legacy runtime behavior.
2. Wrap existing `dataflows` functions behind provider contracts.
3. Update analyst tools to return normalized data snapshots with provenance.
4. Update structured agents to emit the new contract artifacts.
5. Build a minimal daily backtest engine over `TradeSignal`.
6. Add deterministic risk review before report generation.
7. Generate personal research reports from the new artifacts.
8. Build a local cockpit UI on top of the same artifact store.

The safest path is parallel build, then gradual cutover.
