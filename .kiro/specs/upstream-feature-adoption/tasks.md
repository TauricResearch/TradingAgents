# Implementation Plan: Upstream Feature Adoption

## Overview

This plan implements four upstream features in priority order: P0 (look-ahead bias prevention), P1 (checkpoint resume), P2 (decision outcome tracker), and P3 (schema-driven structured output). Each task builds incrementally, with property-based tests validating correctness properties from the design document. The implementation language is Python, matching the existing codebase and design document.

## Tasks

- [ ] 1. P0: OHLCV Look-Ahead Bias Filter
  - [ ] 1.1 Implement `filter_ohlcv_by_date()` in `tradingagents/dataflows/stockstats_utils.py`
    - Add the `filter_ohlcv_by_date(data: pd.DataFrame, curr_date: str | None) -> pd.DataFrame` function
    - Filter rows where DatetimeIndex <= pd.Timestamp(curr_date)
    - Return data unchanged when curr_date is None
    - Raise ValueError for unparseable curr_date strings
    - _Requirements: 1.1, 1.4, 1.6_
  - [ ] 1.2 Integrate OHLCV filter into `StockstatsUtils.get_stock_stats()` and `_get_stock_stats_bulk()`
    - In `get_stock_stats()`: insert `filter_ohlcv_by_date(data, curr_date)` after `_clean_dataframe()` and before `wrap()`
    - In `_get_stock_stats_bulk()` (in `y_finance.py`): insert filter after clean, before wrap and indicator calculation
    - Ensure 6-layer validation still operates on full dataset before filter
    - _Requirements: 1.2, 1.3, 1.5_
  - [ ]* 1.3 Write property tests for OHLCV date filter (`tests/test_ohlcv_date_filter.py`)
    - **Property 1: OHLCV Date Filter Correctness** — all rows in result have index <= curr_date
    - **Property 2: OHLCV Date Filter Idempotence** — filter(filter(data, d2), d1) == filter(data, d1) for d1 <= d2
    - **Property 3: OHLCV None Passthrough** — filter(data, None) returns identical DataFrame
    - **Validates: Requirements 1.1, 1.4, 1.5, 1.6**
  - [ ]* 1.4 Write unit tests for OHLCV filter edge cases
    - Test empty DataFrame input
    - Test curr_date before all data (returns empty)
    - Test curr_date after all data (returns full dataset)
    - Test invalid curr_date string raises ValueError
    - _Requirements: 1.1, 1.3, 1.4_

- [ ] 2. P0: Alpha Vantage Fundamentals Look-Ahead Bias Filter
  - [ ] 2.1 Implement `_filter_reports_by_date()` in `tradingagents/dataflows/alpha_vantage_fundamentals.py`
    - Add `_filter_reports_by_date(result: dict | str, curr_date: str | None) -> dict | str`
    - Filter `annualReports` and `quarterlyReports` arrays by `fiscalDateEnding <= curr_date`
    - Return result unchanged when curr_date is None or result is not a dict
    - _Requirements: 2.1, 2.3_
  - [ ] 2.2 Apply Alpha Vantage filter to all endpoints
    - Modify `get_balance_sheet()`, `get_cashflow()`, `get_income_statement()` to call `_filter_reports_by_date()` on the API response before returning
    - Modify `get_fundamentals()` to pass through (overview has no date-indexed arrays)
    - _Requirements: 2.1, 2.4_
  - [ ]* 2.3 Write property tests for Alpha Vantage date filter (`tests/test_alpha_vantage_date_filter.py`)
    - **Property 4: Alpha Vantage Report Date Filter** — all remaining reports have fiscalDateEnding <= curr_date
    - **Property 5: Alpha Vantage None Passthrough** — filter(result, None) returns identical dict
    - **Validates: Requirements 2.1, 2.3**
  - [ ]* 2.4 Write unit tests for Alpha Vantage filter edge cases
    - Test with error string input (passthrough)
    - Test with all reports after curr_date (returns empty arrays)
    - Test with missing report keys in dict
    - _Requirements: 2.1, 2.2, 2.3_

- [ ] 3. P0: YFinance Financial Statements Look-Ahead Bias Filter
  - [ ] 3.1 Implement `_filter_financials_by_date()` in `tradingagents/dataflows/y_finance.py`
    - Add `_filter_financials_by_date(data: pd.DataFrame, curr_date: str | None) -> pd.DataFrame | str`
    - Drop columns whose Timestamp header is after curr_date
    - Return data unchanged when curr_date is None
    - Return message string if all columns are filtered out
    - _Requirements: 3.1, 3.2, 3.3_
  - [ ] 3.2 Apply yfinance filter to `get_balance_sheet()`, `get_cashflow()`, `get_income_statement()` in `y_finance.py`
    - Insert `_filter_financials_by_date()` call before converting DataFrame to CSV string
    - _Requirements: 3.1, 3.4_
  - [ ]* 3.3 Write property tests for yfinance date filter (`tests/test_yfinance_date_filter.py`)
    - **Property 6: YFinance Column Date Filter** — all remaining column headers represent dates <= curr_date
    - **Property 7: YFinance None Passthrough** — filter(data, None) returns identical DataFrame
    - **Validates: Requirements 3.1, 3.3**
  - [ ]* 3.4 Write unit tests for yfinance filter edge cases
    - Test empty DataFrame
    - Test all columns after curr_date (returns message string)
    - Test columns with mixed Timestamp types
    - _Requirements: 3.1, 3.2, 3.3_

- [ ] 4. Checkpoint — P0 validation
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. P1: LangGraph Checkpoint Resume — Checkpointer Module
  - [ ] 5.1 Create `tradingagents/graph/checkpointer.py`
    - Implement `thread_id(ticker, trade_date) -> str` using SHA-256 of `{ticker}:{trade_date}`
    - Implement `_db_path(data_cache_dir, ticker) -> Path`
    - Implement `get_checkpointer(data_cache_dir, ticker)` context manager yielding SqliteSaver
    - Implement `has_checkpoint()`, `clear_checkpoint()`, `clear_all_checkpoints()`
    - _Requirements: 4.1, 4.2, 4.3, 4.6_
  - [ ] 5.2 Add `langgraph-checkpoint-sqlite>=2.0.0` to `pyproject.toml` dependencies
    - _Requirements: 4.1_
  - [ ]* 5.3 Write property test for deterministic thread ID (`tests/test_checkpointer.py`)
    - **Property 8: Deterministic Thread ID** — same inputs produce same output; different inputs produce different output
    - **Validates: Requirements 4.2**
  - [ ]* 5.4 Write unit tests for checkpointer module
    - Test `_db_path` creates correct path structure
    - Test `get_checkpointer` creates directory and yields SqliteSaver
    - Test `clear_checkpoint` and `clear_all_checkpoints` lifecycle
    - _Requirements: 4.1, 4.3, 4.6_

- [ ] 6. P1: Graph Setup Refactor and Checkpoint Integration
  - [ ] 6.1 Modify `tradingagents/graph/setup.py` to return uncompiled StateGraph
    - Change `setup_graph()` to return the `StateGraph` object before `.compile()` is called
    - _Requirements: 5.1_
  - [ ] 6.2 Modify `tradingagents/graph/trading_graph.py` for checkpoint support
    - In `__init__`: store `self.workflow = setup_graph(...)` and `self.graph = self.workflow.compile()`
    - In `propagate()`: when `checkpoint_enabled` is True, use `get_checkpointer()` context manager, recompile with SqliteSaver, invoke with `thread_id` in config, clear checkpoint on success
    - When `checkpoint_enabled` is False: preserve current behavior exactly
    - _Requirements: 5.2, 5.3, 5.4_
  - [ ] 6.3 Add `checkpoint_enabled` config key to `tradingagents/default_config.py`
    - Default to `False` for opt-in behavior
    - _Requirements: 4.4_
  - [ ]* 6.4 Write integration tests for checkpoint lifecycle (`tests/test_checkpointer.py`)
    - Test full lifecycle: enable → compile with saver → invoke → clear
    - Test that disabled checkpoint produces identical behavior to current
    - _Requirements: 4.4, 4.5, 5.4_

- [ ] 7. Checkpoint — P1 validation
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. P2: Decision Outcome Tracker — Recording
  - [ ] 8.1 Create `tradingagents/agents/utils/decision_outcome_tracker.py` with `DecisionRecord` dataclass and `DecisionOutcomeTracker` class
    - Implement `DecisionRecord` dataclass with all fields (ticker, trade_date, rating, rationale_summary, status, recorded_at, actual_return, benchmark_return, alpha, resolved_at)
    - Implement `__init__(data_cache_dir, holding_period_days=5)`
    - Implement `log_path` property
    - Implement `record_decision()` — append-only JSONL write, no-op on empty rating
    - Implement `_read_all_records()` and `_write_record()` helpers
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - [ ]* 8.2 Write property test for append-only invariant (`tests/test_decision_outcome_tracker.py`)
    - **Property 9: Decision Log Append-Only Invariant** — first N records unchanged after appending (N+1)th
    - **Validates: Requirements 6.1, 6.3**
  - [ ]* 8.3 Write unit tests for decision recording
    - Test record_decision appends valid JSONL
    - Test no-op on empty/None rating
    - Test file creation on first write
    - _Requirements: 6.1, 6.2, 6.4_

- [ ] 9. P2: Decision Outcome Tracker — Resolution and Cross-Ticker Learning
  - [ ] 9.1 Implement `resolve_pending()` in `DecisionOutcomeTracker`
    - Fetch actual return and SPY benchmark for holding period
    - Update status to "resolved", compute alpha = actual - benchmark
    - Leave as "pending" if price data unavailable
    - Implement `_update_record()` helper for in-place rewrite
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [ ] 9.2 Implement `get_cross_ticker_lessons()` in `DecisionOutcomeTracker`
    - Return up to N resolved records from other tickers
    - Order by descending abs(alpha), break ties by recency
    - Format as context string with ticker, date, rating, outcome, lesson
    - Return empty string when no resolved records exist
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - [ ] 9.3 Integrate tracker into `tradingagents/graph/trading_graph.py`
    - Call `resolve_pending()` at start of `propagate()` before graph execution
    - Call `record_decision()` at end of `propagate()` after successful execution
    - Gate on `decision_tracker_enabled` config key
    - _Requirements: 6.1, 7.4_
  - [ ] 9.4 Add decision tracker config keys to `tradingagents/default_config.py`
    - Add `decision_tracker_enabled: False`, `decision_holding_period_days: 5`, `decision_cross_ticker_n: 3`
    - _Requirements: 6.1, 8.1_
  - [ ]* 9.5 Write property tests for resolution and cross-ticker (`tests/test_decision_outcome_tracker.py`)
    - **Property 10: Decision Resolution Alpha Computation** — alpha == actual_return - benchmark_return
    - **Property 11: Cross-Ticker Lessons Ordering and Filtering** — at most N records, excludes target ticker, ordered by abs(alpha) desc
    - **Property 12: Cross-Ticker Context Field Completeness** — output contains ticker, trade_date, rating, outcome, lesson
    - **Validates: Requirements 7.2, 8.1, 8.2**
  - [ ]* 9.6 Write unit tests for resolution and cross-ticker
    - Test resolution with mocked price fetcher
    - Test pending records left unchanged when price unavailable
    - Test cross-ticker excludes current ticker
    - Test empty log returns empty string
    - _Requirements: 7.1, 7.3, 8.3, 8.4_

- [ ] 10. Checkpoint — P2 validation
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. P3: Schema-Driven Structured Output — Schemas and Rating Vocabulary
  - [ ] 11.1 Create `tradingagents/agents/utils/structured_schemas.py`
    - Define `CANONICAL_RATINGS` tuple
    - Define `RATING_SYNONYMS` dictionary mapping legacy terms to canonical
    - Implement `normalize_rating(raw: str) -> str` — map to canonical, default to "Hold"
    - Define `ResearchPlanSchema` Pydantic model (recommendation, confidence, bull_evidence, bear_evidence, rationale, strategic_actions, conflict_resolution)
    - Define `TraderProposalSchema` Pydantic model (action, entry_price, stop_loss, take_profit, position_sizing, reasoning, catalyst_timeline)
    - _Requirements: 9.1, 10.1, 11.1, 11.2, 11.3_
  - [ ]* 11.2 Write property test for rating synonym mapping (`tests/test_structured_schemas.py`)
    - **Property 13: Rating Synonym Mapping** — normalize_rating(synonym) returns canonical value; normalize_rating(canonical) returns itself
    - **Validates: Requirements 11.3**
  - [ ]* 11.3 Write unit tests for schemas
    - Test ResearchPlanSchema validates correct input
    - Test TraderProposalSchema validates correct input
    - Test normalize_rating with unknown input defaults to "Hold"
    - Test all RATING_SYNONYMS keys map correctly
    - _Requirements: 9.1, 10.1, 11.1, 11.3_

- [ ] 12. P3: Structured Output Fallback Utility
  - [ ] 12.1 Create `tradingagents/agents/utils/structured_output.py`
    - Implement `invoke_structured_or_freetext(llm, schema, messages, fallback_extractor, *, agent_name, timeout_tier)`
    - Try `llm.with_structured_output(schema).invoke(messages)` first
    - On `NotImplementedError`, `ValidationError`, or timeout: log warning, invoke LLM without structured output, apply `fallback_extractor`
    - Respect existing `invoke_with_timeout()` and `resolve_timeout()` semantics
    - _Requirements: 12.1, 12.2, 12.3, 12.4_
  - [ ]* 12.2 Write property test for fallback behavior (`tests/test_structured_output_fallback.py`)
    - **Property 14: Structured Output Fallback on Error Types** — for NotImplementedError, ValidationError, or provider error, utility invokes fallback and returns without raising
    - **Validates: Requirements 12.2**
  - [ ]* 12.3 Write unit tests for structured output utility
    - Test successful structured output path returns Pydantic model
    - Test fallback on NotImplementedError
    - Test fallback on ValidationError
    - Test logging includes agent_name and error type
    - _Requirements: 12.1, 12.2, 12.3_

- [ ] 13. P3: Research Manager and Trader Integration
  - [ ] 13.1 Modify `tradingagents/agents/managers/research_manager.py` to use structured output
    - Import `invoke_structured_or_freetext` and `ResearchPlanSchema`
    - Replace direct LLM invocation with `invoke_structured_or_freetext()` call
    - Provide `build_investment_plan_structured()` as the fallback extractor
    - Preserve all existing prompt engineering (conflict resolution, ground-truth constraints)
    - Gate on `structured_output_enabled` config key
    - _Requirements: 9.2, 9.3, 9.4_
  - [ ] 13.2 Modify `tradingagents/agents/trader/trader.py` to use structured output
    - Import `invoke_structured_or_freetext` and `TraderProposalSchema`
    - Replace direct LLM invocation with `invoke_structured_or_freetext()` call
    - Provide `build_trader_plan_structured()` as the fallback extractor
    - Preserve all existing guardrails (ATR sanity check, entry price drift, stop-loss validation)
    - Gate on `structured_output_enabled` config key
    - _Requirements: 10.2, 10.3, 10.4_
  - [ ] 13.3 Add `structured_output_enabled` config key to `tradingagents/default_config.py`
    - Default to `True`
    - _Requirements: 12.1_
  - [ ]* 13.4 Write integration tests for structured output in agents
    - Test Research Manager with structured output enabled (mock LLM)
    - Test Trader with structured output enabled (mock LLM)
    - Test fallback path when structured output disabled via config
    - _Requirements: 9.2, 9.3, 10.2, 10.3_

- [ ] 14. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints at tasks 4, 7, 10, and 14 ensure incremental validation
- Property tests validate the 14 universal correctness properties from the design document
- Unit tests validate specific edge cases and error conditions
- All features are opt-in via config keys — no regression to existing behavior when disabled
- The implementation uses Hypothesis for property-based testing (already configured in the repo)
