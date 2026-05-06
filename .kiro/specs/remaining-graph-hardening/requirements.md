# Requirements Document

## Introduction

This spec covers all remaining unfinished graph hardening work, organized into **5 independent PRs** that can be implemented, tested, and merged in any order. Each PR addresses a distinct concern with no cross-dependencies.

| PR | Scope | Requirements |
|----|-------|--------------|
| **PR-1** | Execution failure injection (Historical Report Reuse Stage 1.5) | Req 1 |
| **PR-2** | Memory backtest safety (ReflexionMemory as-of-date + micro_summary forwarding + run_id seeding) | Req 2, 3, 4 |
| **PR-3** | RunLogger telemetry wiring (Trust-First B3) | Req 5 |
| **PR-4** | Commodity timeframe tagging in scanner context (P2.1) | Req 6 |
| **PR-5** | Research packet summary + structured metric extraction (P2.2 + P2.3) | Req 7, 8 |

PR-2 groups three tightly coupled memory-safety changes (they share the same test fixtures and touch the same call paths). PR-5 groups summary generation with metric extraction because the summary consumes the structured metrics.

## Glossary

- **Graph**: The LangGraph-based directed acyclic workflow that orchestrates trading agents (scanner, analysts, debate, risk, portfolio manager, trader, execution).
- **RunLogger**: The `tradingagents.observability.RunLogger` class that accumulates structured events (LLM calls, tool calls, vendor calls) for a single run and writes them to `run_log.jsonl`.
- **ReflexionMemory**: The `tradingagents.memory.reflexion.ReflexionMemory` class that stores agent decisions with rationale and later associates actual market outcomes for reflection.
- **MacroMemory**: The `tradingagents.memory.macro_memory.MacroMemory` class that stores macro regime states (VIX, sector thesis, themes) for injection into agent prompts.
- **PortfolioGraph**: The `tradingagents.graph.portfolio_graph.PortfolioGraph` class that orchestrates the full portfolio manager workflow (data gathering, summarization, PM decision, execution).
- **Execution_Failure**: A trade that failed during execution due to insufficient cash, constraint violations, or other pre-flight checks. Stored in `reports/daily/{date}/{run_id}/portfolio/report/*_execution_result.json` under the `failed_trades` key.
- **Scanner_Context**: The text block assembled from market data (commodities, indices, VIX) and injected into agent prompts as `scanner_graph_context_text`.
- **Research_Packet_Summary**: A 400-token compressed summary of the analyst chain's conclusions (ticker, date, bull/bear points, rating, confidence) stored in AgentState for PM consumption.
- **Fundamentals_Report_Structured**: The structured output dict from the fundamentals analyst containing `key_metrics` (PE ratio, D/E, FCF, operating margin, current ratio, working capital) extracted at write time.
- **as_of_date**: An ISO date string (YYYY-MM-DD) used to filter memory records, preventing future context leakage in backtests.
- **run_id**: A unique identifier (UUID) seeded at run start and propagated through state to provide provenance for all memory records and reports produced during that run.
- **Micro_Summary_Agent**: The `tradingagents.agents.portfolio.micro_summary_agent` node that builds per-ticker reflexion memory context for the PM decision.
- **LangGraph_Event_Stream**: The async event iterator (`graph.astream_events`) that emits structured events (LLM start/end, tool calls, chain events) during graph execution.

## Requirements

---

## PR-1: Execution Failure Injection

### Requirement 1: Execution Failure Injection into Agent Prompts

**User Story:** As a portfolio manager agent, I want to see prior execution failures (insufficient cash, constraint violations) from the most recent prior run, so that I can avoid repeating the same trade sizing or constraint errors.

#### Acceptance Criteria

1. WHEN a prior run for the same portfolio produced execution failures (non-empty `failed_trades` in `*_execution_result.json`), THE Historical_Context_Loader SHALL extract and format those failures into a structured prompt block.
2. WHEN execution failures are available, THE Trader_Node SHALL receive the failure block in its system prompt context before generating a new investment plan.
3. WHEN execution failures are available, THE Research_Manager_Node SHALL receive the failure block in its system prompt context before synthesizing the research recommendation.
4. WHEN execution failures are available, THE Portfolio_Manager_Node SHALL receive the failure block in its system prompt context before making allocation decisions.
5. WHEN execution failures are available, THE Risk_Debater_Nodes SHALL receive the failure block in their system prompt context before debating risk.
6. IF no prior execution result exists or `failed_trades` is empty, THEN THE Historical_Context_Loader SHALL return an empty string and agent prompts SHALL remain unchanged.
7. THE Execution_Failure_Block SHALL include for each failed trade: action (BUY/SELL), ticker, shares, failure reason, and the date of the failed run.
8. THE Execution_Failure_Block SHALL be capped at 600 characters to avoid prompt bloat.

---

## PR-2: Memory Backtest Safety

### Requirement 2: ReflexionMemory As-Of-Date Filtering

**User Story:** As a backtesting operator, I want ReflexionMemory queries to respect an as-of-date boundary, so that future decisions do not leak into historical simulations.

#### Acceptance Criteria

1. WHEN `as_of_date` is provided to `ReflexionMemory.get_history()`, THE ReflexionMemory SHALL exclude all records with `decision_date` after the specified date.
2. WHEN `as_of_date` is provided to `ReflexionMemory.build_context()`, THE ReflexionMemory SHALL exclude all records with `decision_date` after the specified date.
3. WHEN `as_of_date` is not provided, THE ReflexionMemory SHALL return all matching records (backward-compatible behavior).
4. THE ReflexionMemory SHALL apply the as-of-date filter in both MongoDB and local JSON fallback paths.
5. IF the local JSON file is corrupt or unreadable, THEN THE ReflexionMemory SHALL log a warning and return an empty list rather than raising an exception.

### Requirement 3: Micro Summary Agent Date Forwarding

**User Story:** As a system operator, I want the micro_summary_agent to forward `analysis_date` as `as_of_date` to all memory calls, so that memory lookups are date-bounded and backtest-safe.

#### Acceptance Criteria

1. WHEN the micro_summary_agent invokes `ReflexionMemory.build_context()`, THE Micro_Summary_Agent SHALL pass `analysis_date` from state as the `as_of_date` parameter.
2. IF `analysis_date` is missing or empty in state, THEN THE Micro_Summary_Agent SHALL raise a RuntimeError with a descriptive message rather than falling back to unbounded queries.

### Requirement 4: PortfolioGraph Run ID Seeding

**User Story:** As a system operator, I want every PortfolioGraph run to carry a deterministic `run_id` in state, so that all memory records and reports produced during that run carry provenance.

#### Acceptance Criteria

1. WHEN `run_id` is provided to `PortfolioGraph.run()`, THE PortfolioGraph SHALL seed that value into the initial state dict.
2. WHEN `run_id` is not provided to `PortfolioGraph.run()`, THE PortfolioGraph SHALL generate a UUID and seed it into the initial state dict.
3. THE run_id in initial state SHALL propagate to all downstream nodes that record memory entries or save reports.

---

## PR-3: RunLogger Telemetry Wiring

### Requirement 5: RunLogger Telemetry Wiring (Trust-First B3)

**User Story:** As an operator reviewing run telemetry, I want `run_log.jsonl` summary to show accurate `llm_calls`, `tokens_in`, and `tokens_out` counters, so that I can monitor cost and latency per run.

#### Acceptance Criteria

1. WHEN the LangGraph engine executes a graph via `astream_events`, THE Engine SHALL pass `RunLogger.callback` in the `config["callbacks"]` list.
2. WHEN an LLM call completes during graph execution, THE RunLogger SHALL capture the event and increment `llm_calls` in the summary.
3. WHEN an LLM call completes, THE RunLogger SHALL record `tokens_in` and `tokens_out` from the response metadata.
4. THE `run_log.jsonl` summary block SHALL reflect non-zero `llm_calls` after any graph execution that invoked at least one LLM.
5. IF the RunLogger callback is not wired (defensive check), THEN THE Engine SHALL log a warning at run start indicating telemetry will be incomplete.

---

## PR-4: Commodity Timeframe Tagging

### Requirement 6: Commodity Timeframe Tagging in Scanner Context

**User Story:** As a trading agent consuming scanner context, I want commodity price changes labeled with explicit timeframes (daily vs YoY), so that I do not conflate year-over-year trends with intraday momentum.

#### Acceptance Criteria

1. THE Scanner_Context_Builder SHALL produce separate fields for daily and year-over-year commodity price changes.
2. THE Scanner_Context_Text SHALL label every commodity change with an explicit timeframe marker: `(daily)` and `(YoY)`.
3. THE Scanner_Context_Text SHALL use the format: `"Name: $price (±X.XX% daily, ±Y.YY% YoY)"` for each commodity (gold, oil, DXY, VIX).
4. IF a bare percentage change without a timeframe label appears in scanner context, THEN THE Scanner_Context_Validator SHALL reject the output.
5. THE Scanner_Context_Builder SHALL not fall back to wall-clock dates or synthesize data when scan_date context is missing; it SHALL fail the node with a clear reason.

---

## PR-5: Research Packet Summary + Structured Metric Extraction

### Requirement 7: Research Packet Summary Generation

**User Story:** As a portfolio manager agent, I want a compressed 400-token summary of the analyst chain's conclusions available in state after the RM consistency guard passes, so that I have structured memory of what was concluded without reading the full research packet.

#### Acceptance Criteria

1. WHEN the RM consistency guard returns `status: "ok"`, THE RM_Consistency_Guard_Node SHALL generate a structured summary and store it as `research_packet_summary` in AgentState.
2. THE Research_Packet_Summary SHALL contain: ticker, trade date, top bull points with numbers, top bear points with numbers, final RM rating, confidence score, entry price, and target price.
3. THE Research_Packet_Summary SHALL be between 200 and 500 characters in length.
4. WHEN the RM consistency guard fails (status not "ok"), THE RM_Consistency_Guard_Node SHALL leave `research_packet_summary` empty.
5. THE Portfolio_Manager_Node SHALL receive `research_packet_summary` as a structured header in its prompt context.

### Requirement 8: Structured Fundamentals Metric Extraction

**User Story:** As a downstream consumer of fundamentals data, I want PE ratio, D/E ratio, FCF change, operating margin, current ratio, and working capital extracted into typed fields at write time, so that I can access validated numbers without regex parsing at read time.

#### Acceptance Criteria

1. WHEN the fundamentals analyst LLM returns a report, THE Fundamentals_Analyst_Node SHALL extract metrics into `fundamentals_report_structured.key_metrics` at write time.
2. THE key_metrics dict SHALL contain typed fields: `pe_ratio` (float or None), `debt_equity_ratio` (float or None), `fcf_change_pct` (float or None), `operating_margin_pct` (float or None), `current_ratio` (float or None), `working_capital_str` (str or None).
3. IF a metric is not present in the LLM output, THEN THE Fundamentals_Analyst_Node SHALL set that field to None rather than raising an error.
4. THE `_fundamentals_risk_block` function SHALL prefer structured metrics from `key_metrics` over regex extraction from raw text.
5. IF structured metrics are unavailable or empty, THEN THE `_fundamentals_risk_block` function SHALL fall back to regex extraction from the raw `fundamentals_report` text.
6. FOR ALL valid fundamentals reports containing the mandated metric format, extracting metrics then formatting them back into text SHALL preserve the numeric values (round-trip property within floating-point tolerance).
