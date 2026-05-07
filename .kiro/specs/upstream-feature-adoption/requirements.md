# Requirements Document

## Introduction

This specification covers four features inspired by upstream TauricResearch/TradingAgents commits, adapted to our fork's architecture. The features address: (1) look-ahead bias prevention in backtesting, (2) crash-recovery via LangGraph checkpoint resume, (3) a decision outcome tracker for cross-run learning, and (4) schema-driven structured output for the Research Manager and Trader agents. Each feature is designed to coexist with our existing systems (BM25 memory, historical context, PM structured output, 6-layer OHLCV validation) without regression.

## Glossary

- **OHLCV_Loader**: The `_load_or_fetch_ohlcv()` function in `stockstats_utils.py` — single authority for loading cached or freshly-downloaded Open/High/Low/Close/Volume data with 6 layers of validation (corruption, staleness, plausibility, contamination, row count, retry).
- **Date_Filter**: A function that truncates a time-indexed DataFrame or report list to exclude rows/entries after a given `curr_date`, preventing look-ahead bias.
- **Stockstats_Wrapper**: The `StockstatsUtils.get_stock_stats()` method and `_get_stock_stats_bulk()` helper that compute technical indicators via the stockstats library.
- **Alpha_Vantage_Fundamentals**: The module `alpha_vantage_fundamentals.py` providing `get_fundamentals()`, `get_balance_sheet()`, `get_cashflow()`, `get_income_statement()` via Alpha Vantage API.
- **YFinance_Financials**: The functions `get_balance_sheet()`, `get_cashflow()`, `get_income_statement()` in `y_finance.py` that fetch financial statements from yfinance.
- **Checkpointer**: A module providing per-ticker SQLite-based crash recovery for LangGraph graph execution, using deterministic thread IDs derived from ticker and date.
- **Graph_Setup**: The `GraphSetup.setup_graph()` method in `setup.py` that constructs and compiles the LangGraph workflow.
- **Propagator**: The `Propagator` class in `propagation.py` that creates initial state and provides graph invocation arguments.
- **Decision_Outcome_Tracker**: A new module that records trading decisions in an append-only log and resolves actual outcomes on subsequent runs.
- **Structured_Output_Schema**: A Pydantic BaseModel used with `llm.with_structured_output()` to obtain type-safe, validated responses from LLM calls.
- **Research_Manager**: The agent node (`create_research_manager()`) that synthesizes analyst reports into an investment plan.
- **Trader**: The agent node (`create_trader()`) that produces a concrete trade proposal with entry/exit levels.
- **PM_Decision_Agent**: The portfolio manager agent that already uses `PMDecisionSchema` with `llm.with_structured_output()`.
- **BM25_Memory**: The existing `FinancialSituationMemory` class using BM25 for within-run lexical similarity matching.
- **Historical_Context**: The existing `historical_context.py` module that loads prior analysis reports from disk for prompt injection.

## Requirements

### Requirement 1: OHLCV Look-Ahead Bias Filter

**User Story:** As a quantitative researcher, I want OHLCV data filtered to exclude rows after the current trading date, so that backtest results are not contaminated by future price information.

#### Acceptance Criteria

1. WHEN `curr_date` is provided to the OHLCV loading pipeline, THE Date_Filter SHALL return only rows where the DatetimeIndex is on or before `curr_date`.
2. WHEN `curr_date` is provided, THE Stockstats_Wrapper SHALL compute technical indicators using only data on or before `curr_date`, ensuring moving averages, RSI, and other indicators never incorporate future prices.
3. THE OHLCV_Loader SHALL continue to apply all 6 existing validation layers (corruption detection, staleness check, plausibility guard, contamination check, row count assertion, retry logic) before the Date_Filter is applied.
4. IF `curr_date` is not provided or is None, THEN THE Date_Filter SHALL return the full unfiltered dataset to preserve live-trading behavior.
5. WHEN `_get_stock_stats_bulk()` is called with a `curr_date`, THE Date_Filter SHALL truncate the OHLCV data before indicator calculation, so the returned indicator dictionary contains only dates on or before `curr_date`.
6. FOR ALL valid OHLCV DataFrames, filtering by `curr_date` then filtering by an earlier date SHALL produce the same result as filtering by the earlier date alone (idempotence of date boundary).

### Requirement 2: Alpha Vantage Fundamentals Look-Ahead Bias Filter

**User Story:** As a quantitative researcher, I want Alpha Vantage fundamental reports filtered by fiscal date, so that backtests cannot access financial data from future reporting periods.

#### Acceptance Criteria

1. WHEN `curr_date` is provided, THE Alpha_Vantage_Fundamentals SHALL filter `annualReports` and `quarterlyReports` arrays to exclude entries where `fiscalDateEnding` is after `curr_date`.
2. WHEN the API response contains no reports on or before `curr_date`, THE Alpha_Vantage_Fundamentals SHALL return an empty reports array rather than raising an error.
3. IF `curr_date` is None or not provided, THEN THE Alpha_Vantage_Fundamentals SHALL return the full unfiltered API response.
4. THE Alpha_Vantage_Fundamentals filter SHALL apply to all four endpoints: `get_fundamentals()`, `get_balance_sheet()`, `get_cashflow()`, and `get_income_statement()`.

### Requirement 3: YFinance Financial Statements Look-Ahead Bias Filter

**User Story:** As a quantitative researcher, I want yfinance financial statements filtered to exclude columns representing future fiscal periods, so that backtests only see data that would have been publicly available on the trading date.

#### Acceptance Criteria

1. WHEN `curr_date` is provided, THE YFinance_Financials SHALL drop DataFrame columns whose date header is after `curr_date`.
2. WHEN all columns in a financial statement are after `curr_date`, THE YFinance_Financials SHALL return a message indicating no data is available for the requested period rather than returning an empty DataFrame silently.
3. IF `curr_date` is None or not provided, THEN THE YFinance_Financials SHALL return the full unfiltered financial statement.
4. THE filter SHALL apply to `get_balance_sheet()`, `get_cashflow()`, and `get_income_statement()` in `y_finance.py`.

### Requirement 4: LangGraph Checkpoint Resume Module

**User Story:** As an operator, I want opt-in crash recovery for graph execution, so that a failed multi-minute analysis run can resume from its last checkpoint rather than restarting from scratch.

#### Acceptance Criteria

1. WHEN `checkpoint_enabled` is True in config, THE Checkpointer SHALL create a per-ticker SQLite database at `{data_cache_dir}/checkpoints/{TICKER}.db`.
2. THE Checkpointer SHALL generate a deterministic `thread_id` from `sha256(ticker + ":" + trade_date)`, so that the same ticker and date resume from a prior checkpoint while a different date starts fresh.
3. WHEN a graph execution completes successfully, THE Checkpointer SHALL clear the checkpoint for that thread_id so the next run with the same ticker+date starts fresh.
4. IF `checkpoint_enabled` is False or absent from config, THEN THE Checkpointer SHALL not be instantiated and graph execution SHALL behave identically to the current implementation.
5. WHEN a graph execution is interrupted (crash, timeout, exception), THE Checkpointer SHALL preserve the last committed checkpoint state in the SQLite database for future resume.
6. THE Checkpointer context manager SHALL guarantee resource cleanup (database connection closure) regardless of whether execution succeeds or fails.

### Requirement 5: Graph Setup Refactor for Checkpoint Support

**User Story:** As a developer, I want the graph setup to return an uncompiled StateGraph, so that the graph can be recompiled with a checkpointer when crash recovery is enabled.

#### Acceptance Criteria

1. THE Graph_Setup `setup_graph()` method SHALL return an uncompiled `StateGraph` object instead of a compiled `CompiledStateGraph`.
2. THE TradingAgentsGraph `__init__` SHALL store the uncompiled workflow and compile it separately, so recompilation with a checkpointer is possible without re-running setup.
3. WHEN `checkpoint_enabled` is True, THE Propagator SHALL recompile the workflow with the SqliteSaver checkpointer and include the `thread_id` in the graph invocation config.
4. WHEN `checkpoint_enabled` is False, THE compiled graph SHALL be identical in behavior to the current implementation (no regression).

### Requirement 6: Decision Outcome Tracker — Recording

**User Story:** As a system operator, I want each trading decision recorded in an append-only log with a pending status, so that outcomes can be resolved on subsequent runs.

#### Acceptance Criteria

1. WHEN a graph execution completes with a final trade decision, THE Decision_Outcome_Tracker SHALL append a record containing: ticker, trade_date, rating, rationale summary, and status "pending".
2. THE Decision_Outcome_Tracker SHALL store records in a structured file at `{data_cache_dir}/decision_log.jsonl` using one JSON object per line.
3. THE Decision_Outcome_Tracker SHALL not modify or delete existing records when appending new ones (append-only semantics).
4. IF the final trade decision is empty or the graph terminates early, THEN THE Decision_Outcome_Tracker SHALL not append a record.

### Requirement 7: Decision Outcome Tracker — Resolution

**User Story:** As a quantitative researcher, I want pending decisions resolved with actual market returns on subsequent runs, so that the system can learn from its past accuracy.

#### Acceptance Criteria

1. WHEN a new graph execution starts for a ticker that has pending decisions older than the configured holding period, THE Decision_Outcome_Tracker SHALL fetch the actual return for the ticker over the holding period and the SPY benchmark return for the same period.
2. WHEN resolving a pending decision, THE Decision_Outcome_Tracker SHALL update the record status from "pending" to "resolved" and store: actual_return, benchmark_return, and alpha (actual minus benchmark).
3. IF price data is unavailable for the resolution period (e.g., future dates in backtest), THEN THE Decision_Outcome_Tracker SHALL leave the record as "pending" without error.
4. THE Decision_Outcome_Tracker SHALL resolve pending decisions at the start of `propagate()`, before the graph executes, so resolved outcomes are available for prompt injection.

### Requirement 8: Decision Outcome Tracker — Cross-Ticker Learning

**User Story:** As a portfolio manager agent, I want to see lessons learned from decisions on other tickers, so that cross-asset patterns inform current analysis.

#### Acceptance Criteria

1. WHEN requested, THE Decision_Outcome_Tracker SHALL return up to N resolved decisions from other tickers, prioritizing recent decisions with the largest absolute alpha.
2. THE cross-ticker context SHALL include: ticker, date, rating, actual outcome, and a one-sentence lesson summary.
3. THE Decision_Outcome_Tracker SHALL coexist with the existing BM25_Memory and Historical_Context systems without replacing or modifying them.
4. WHEN no resolved cross-ticker decisions exist, THE Decision_Outcome_Tracker SHALL return an empty context string rather than raising an error.

### Requirement 9: Research Manager Structured Output Schema

**User Story:** As a developer, I want the Research Manager to use a Pydantic schema with `llm.with_structured_output()` as the primary call path, so that output parsing is type-safe and eliminates fragile regex extraction.

#### Acceptance Criteria

1. THE Research_Manager SHALL define a `ResearchPlanSchema` Pydantic model with fields: recommendation (5-tier: Buy/Overweight/Hold/Underweight/Sell), confidence (HIGH/MED/LOW), bull_evidence (list of strings), bear_evidence (list of strings), rationale, strategic_actions, and conflict_resolution.
2. WHEN the LLM provider supports structured output, THE Research_Manager SHALL use `llm.with_structured_output(ResearchPlanSchema)` as the primary invocation path.
3. IF the structured output call fails (provider incompatibility, validation error, or timeout), THEN THE Research_Manager SHALL fall back to the existing free-text invocation with `build_investment_plan_structured()` post-hoc extraction.
4. THE Research_Manager structured output SHALL preserve all existing prompt engineering (conflict resolution section, ground-truth constraints, anonymization) without modification.

### Requirement 10: Trader Structured Output Schema

**User Story:** As a developer, I want the Trader to use a Pydantic schema with `llm.with_structured_output()` as the primary call path, so that trade proposals are type-safe and validated at the LLM boundary.

#### Acceptance Criteria

1. THE Trader SHALL define a `TraderProposalSchema` Pydantic model with fields: action (Buy/Hold/Sell), entry_price (optional float), stop_loss (optional float), take_profit (optional float), position_sizing (optional string), reasoning, and catalyst_timeline.
2. WHEN the LLM provider supports structured output, THE Trader SHALL use `llm.with_structured_output(TraderProposalSchema)` as the primary invocation path.
3. IF the structured output call fails, THEN THE Trader SHALL fall back to the existing free-text invocation with `build_trader_plan_structured()` post-hoc extraction.
4. THE Trader structured output SHALL preserve all existing guardrails (ATR sanity check, entry price drift check, stop-loss validation) by applying them as post-validation on the schema output.

### Requirement 11: Standardized Rating Vocabulary

**User Story:** As a system architect, I want all agents to use a consistent 5-tier rating vocabulary, so that downstream consumers can reliably compare recommendations across agents and time periods.

#### Acceptance Criteria

1. THE system SHALL define a canonical 5-tier rating vocabulary: Buy, Overweight, Hold, Underweight, Sell.
2. THE Research_Manager and Trader structured schemas SHALL use the canonical vocabulary for their recommendation/action fields.
3. WHEN parsing legacy free-text outputs (fallback path), THE system SHALL map common synonyms (e.g., "Strong Buy" → "Buy", "Neutral" → "Hold", "Strong Sell" → "Sell") to the canonical vocabulary.
4. THE PM_Decision_Agent SHALL continue using its existing `PMDecisionSchema` without modification, as it already has a richer decision model.

### Requirement 12: Structured Output Fallback Pattern

**User Story:** As a developer, I want a reusable fallback pattern for structured output calls, so that agents gracefully degrade when the LLM provider does not support schema-driven responses.

#### Acceptance Criteria

1. THE system SHALL provide a utility function `invoke_structured_or_freetext(llm, schema, messages, fallback_extractor)` that attempts structured output first and falls back to free-text extraction on failure.
2. WHEN the structured output call raises a `NotImplementedError`, validation error, or provider-specific unsupported-feature error, THE utility SHALL invoke the LLM without structured output and apply the `fallback_extractor` function.
3. THE utility SHALL log a warning when falling back, including the error type and agent name, for operational visibility.
4. THE utility SHALL respect the existing `invoke_with_timeout()` timeout semantics for both the structured and fallback paths.
