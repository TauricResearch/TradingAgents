# Implementation Plan: Remaining Graph Hardening

## Overview

Five independent PRs that close remaining graph-hardening gaps. Each PR is self-contained with no cross-dependencies. PR-2 and PR-3 are largely implemented and need verification + tests. PR-1, PR-4, and PR-5 require new implementation. Tasks follow test-first methodology: write failing test → implement → verify pass.

## Tasks

- [x] 1. PR-1: Execution Failure Injection
  - [x] 1.1 Write property tests for `format_execution_failure_block()`
    - Create `tests/agents/utils/test_execution_failure_context.py`
    - **Property 1: Execution failure block structural completeness** — for any non-empty list of failed trades, output contains action, ticker, shares, reason for every included trade plus date header
    - **Property 2: Execution failure block length cap** — for any input (including arbitrarily large failure lists), output never exceeds 600 characters
    - Use Hypothesis with `@settings(max_examples=100)` and strategies generating lists of failed trade dicts
    - _Requirements: 1.1, 1.7, 1.8_

  - [x] 1.2 Implement `find_latest_execution_failures()` in `tradingagents/agents/utils/historical_context.py`
    - Scan `reports/daily/{date}/{run_id}/portfolio/report/*_execution_result.json` for latest file strictly before `as_of_date` with non-empty `failed_trades`
    - Reuse existing `_candidate_dates()` + `_load_latest_in_date()` pattern
    - Return `{"date": "YYYY-MM-DD", "failed_trades": [...]}` or `None`
    - Handle corrupt/unreadable JSON by returning `None`
    - _Requirements: 1.1, 1.6_

  - [x] 1.3 Implement `format_execution_failure_block()` in `tradingagents/agents/utils/historical_context.py`
    - Format each failure as `"- {action} {ticker} x{shares}: {reason}"`
    - Add header `"## Prior Execution Failures ({date})"`
    - Cap total output at 600 characters
    - Return empty string if failures is None or `failed_trades` is empty
    - _Requirements: 1.7, 1.8, 1.6_

  - [x] 1.4 Inject failure block into agent prompts
    - Modify `tradingagents/agents/trader/trader.py` to call `find_latest_execution_failures()` + `format_execution_failure_block()` and append to system prompt
    - Modify `tradingagents/agents/research_manager.py` similarly
    - Modify `tradingagents/agents/portfolio/pm_decision_agent.py` similarly
    - Modify `tradingagents/agents/risk_debaters/*.py` similarly
    - Append block after existing prior-context sections when non-empty
    - _Requirements: 1.2, 1.3, 1.4, 1.5_

  - [x] 1.5 Write unit tests for agent prompt injection
    - Test that each agent node includes failure block in prompt when failures are available
    - Test that prompts remain unchanged when no failures exist (empty string returned)
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 2. Checkpoint — PR-1 verification
  - Ensure all PR-1 tests pass, ask the user if questions arise.

- [x] 3. PR-2: Memory Backtest Safety (verification + tests)
  - [x] 3.1 Write property tests for ReflexionMemory as-of-date filtering
    - Create `tests/unit/test_reflexion_memory_as_of_date.py`
    - **Property 3: ReflexionMemory as-of-date filtering** — for any set of reflexion records and any `as_of_date`, `get_history(ticker, as_of_date=d)` returns only records with `decision_date <= d` in descending date order
    - Use Hypothesis strategies generating lists of records with random ISO dates and a random as_of_date cutoff
    - Test both MongoDB mock path and local JSON fallback path
    - `@settings(max_examples=100)`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.2 Write unit tests for corrupt file handling and micro_summary_agent
    - Test that corrupt/unreadable local JSON logs warning and returns empty list
    - Test that `micro_summary_agent` raises `RuntimeError` when `analysis_date` is missing
    - Test that `micro_summary_agent` passes `analysis_date` as `as_of_date` to `build_context()`
    - _Requirements: 2.5, 3.1, 3.2_

  - [x] 3.3 Write integration test for run_id seeding and propagation
    - Test that `PortfolioGraph.run()` generates UUID when `run_id` not provided
    - Test that provided `run_id` is seeded into initial state
    - Test that `run_id` propagates to downstream nodes
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 4. Checkpoint — PR-2 verification
  - Ensure all PR-2 tests pass, ask the user if questions arise.

- [x] 5. PR-3: RunLogger Telemetry Wiring (verification + tests)
  - [x] 5.1 Write property tests for RunLogger event accumulation
    - Create `tests/observability/test_runlogger_telemetry.py`
    - **Property 4: RunLogger event accumulation accuracy** — for any sequence of N simulated LLM call events with known `tokens_in`/`tokens_out`, `RunLogger.summary()` reports `llm_calls == N`, `tokens_in == sum(all tokens_in)`, `tokens_out == sum(all tokens_out)`
    - Use Hypothesis strategies generating lists of (tokens_in, tokens_out) tuples
    - `@settings(max_examples=100)`
    - _Requirements: 5.2, 5.3_

  - [x] 5.2 Verify RunLogger callback wiring across all engine run methods
    - Verify `run_scan()`, `run_pipeline()`, and `run_portfolio()` in `agent_os/backend/services/langgraph_engine.py` all pass `RunLogger.callback` in `config["callbacks"]`
    - If any method is missing the callback wiring, add it
    - Add defensive warning log at run start if callback list is empty
    - _Requirements: 5.1, 5.5_

  - [x] 5.3 Write integration test for end-to-end telemetry
    - Test that a mocked graph execution produces non-zero `llm_calls` in `run_log.jsonl` summary
    - _Requirements: 5.4_

- [x] 6. Checkpoint — PR-3 verification
  - Ensure all PR-3 tests pass, ask the user if questions arise.

- [x] 7. PR-4: Commodity Timeframe Tagging
  - [x] 7.1 Write property tests for commodity timeframe format compliance
    - Create `tests/backend/services/test_scanner_context_timeframe.py`
    - **Property 5: Commodity timeframe format compliance** — for any commodity entry (name, price, daily_change_pct, yoy_change_pct), formatted line matches `"Name: $price (±X.XX% daily, ±Y.YY% YoY)"` and contains no bare percentage without timeframe label
    - Use Hypothesis strategies generating commodity names, prices, and percentage changes
    - `@settings(max_examples=100)`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 7.2 Implement `format_commodity_line()` in `agent_os/backend/services/scanner_context.py`
    - Format: `"Name: $price (+X.XX% daily, +Y.YY% YoY)"`
    - Accept name, price, daily change pct, and YoY change pct as parameters
    - _Requirements: 6.2, 6.3_

  - [x] 7.3 Implement `validate_commodity_block()` in `agent_os/backend/services/scanner_context.py`
    - Reject any bare percentage in commodity section without `(daily)` or `(YoY)` label
    - Return True if all percentages have timeframe labels, False otherwise
    - _Requirements: 6.4_

  - [x] 7.4 Modify `build_scanner_context_packet()` to use new commodity formatting
    - Replace existing bare-percentage commodity formatting with `format_commodity_line()` calls
    - Ensure scanner tools expose both daily and YoY change fields
    - Call `validate_commodity_block()` as post-condition check
    - Fail node with clear reason if `scan_date` is missing (no wall-clock fallback per scanner determinism rules)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 7.5 Write unit tests for scanner context failure modes
    - Test that missing `scan_date` fails the node with a clear error
    - Test that bare percentages are rejected by validator
    - _Requirements: 6.4, 6.5_

- [x] 8. Checkpoint — PR-4 verification
  - Ensure all PR-4 tests pass, ask the user if questions arise.

- [x] 9. PR-5: Research Packet Summary + Structured Metric Extraction
  - [x] 9.1 Write property tests for research packet summary
    - Create `tests/graph/test_research_packet_summary.py`
    - **Property 6: Research packet summary field completeness** — for any valid research packet (non-empty investment_plan with rating, bull/bear points, entry/target price), output contains ticker, trade_date, at least one bull point, at least one bear point, rating, and price info
    - **Property 7: Research packet summary length bounds** — for any input producing a non-empty result, output length is between 200 and 500 characters inclusive
    - Use Hypothesis strategies generating valid investment plan text with required fields
    - `@settings(max_examples=100)`
    - _Requirements: 7.2, 7.3_

  - [x] 9.2 Write property tests for fundamentals metric extraction
    - Create `tests/agents/utils/test_metric_extraction.py`
    - **Property 8: Fundamentals metric extraction correctness** — for any report text containing mandated metric format lines, `FundamentalsKeyMetrics.from_report_text()` extracts each present metric into its typed field and sets absent metrics to None without raising
    - **Property 9: Fundamentals metric round-trip preservation** — for any set of valid metric values, formatting into mandated text then extracting via `from_report_text()` produces values equal to originals within tolerance (±0.01 for percentages, ±0.1 for ratios)
    - Use Hypothesis strategies generating metric values and report text
    - `@settings(max_examples=100)`
    - _Requirements: 8.1, 8.2, 8.3, 8.6_

  - [x] 9.3 Implement `FundamentalsKeyMetrics` dataclass in `tradingagents/agents/utils/output_validation.py`
    - Define dataclass with fields: `pe_ratio`, `debt_equity_ratio`, `fcf_change_pct`, `operating_margin_pct`, `current_ratio`, `working_capital_str` (all Optional)
    - Implement `from_report_text(cls, report: str)` using regex patterns matching mandated format
    - Implement `to_dict()` and `format_risk_block()` methods
    - Never raise on missing metrics — set to None
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 9.4 Implement `generate_research_packet_summary()` in `tradingagents/graph/_consistency_guard.py`
    - Extract ticker, trade_date, bull/bear points, rating, confidence, entry/target price from investment_plan text using regex
    - Format as compact summary: `"{ticker} | {date} | Rating: {rating} | Confidence: {confidence}\nBull: ...\nBear: ...\nEntry: ${entry} | Target: ${target}"`
    - Enforce 200-500 character bounds (truncate if needed)
    - Return empty string if inputs are insufficient
    - _Requirements: 7.2, 7.3_

  - [x] 9.5 Wire summary generation into RM consistency guard node
    - In `tradingagents/graph/setup.py` (or `_consistency_guard.py`), call `generate_research_packet_summary()` when `rm_consistency_status == "ok"`
    - Store result as `research_packet_summary` in returned state dict
    - Leave `research_packet_summary` empty when status != "ok"
    - _Requirements: 7.1, 7.4_

  - [x] 9.6 Modify `_fundamentals_risk_block()` to prefer structured metrics
    - In `tradingagents/agents/utils/summary_context.py`, check for `key_metrics` in structured fundamentals data
    - If `key_metrics` has typed fields, format risk block from those
    - If structured metrics unavailable or empty, fall back to existing regex extraction from raw text
    - _Requirements: 8.4, 8.5_

  - [x] 9.7 Wire metric extraction into fundamentals analyst write path
    - In `tradingagents/agents/utils/output_validation.py`, call `FundamentalsKeyMetrics.from_report_text()` inside `build_fundamentals_report_structured()`
    - Store result in `structured_payload["key_metrics"]`
    - _Requirements: 8.1, 8.2_

  - [x] 9.8 Inject `research_packet_summary` into PM prompt
    - In `tradingagents/agents/portfolio/pm_decision_agent.py`, read `research_packet_summary` from state
    - Inject as structured header in PM prompt context
    - _Requirements: 7.5_

  - [x] 9.9 Write unit tests for summary and metric integration
    - Test RM guard produces empty summary on failure status
    - Test PM node receives `research_packet_summary` in prompt
    - Test `_fundamentals_risk_block` prefers structured over regex
    - Test `_fundamentals_risk_block` falls back to regex when structured unavailable
    - _Requirements: 7.4, 7.5, 8.4, 8.5_

- [x] 10. Final checkpoint — All PRs verified
  - Ensure all tests pass across all 5 PRs, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- PR-2 and PR-3 are largely implemented — tasks focus on verification and adding property tests
- PR-1, PR-4, and PR-5 require new implementation following test-first methodology
- Each PR is independent and can be implemented in any order
- Property tests use Hypothesis with `@settings(max_examples=100)` minimum
- Scanner determinism rules apply: no wall-clock fallbacks, fail loudly on missing context
- All property tests include docstrings with `Feature: remaining-graph-hardening, Property N: {title}` tags
