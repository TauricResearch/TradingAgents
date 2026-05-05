# Real End-to-End Search Examples Report (2026-05-01)

Repo: `/Users/sydneymilton/dev/_sandbox/tradingagents-flint-shadow`
Service: `http://localhost:8000`

## Goal
Run a series of real shadow-analysis searches and document full I/O receipts.

## Example 1: AAPL (Completed)
Input:
```json
{"ticker":"AAPL","trade_date":"2026-01-22","selected_analysts":["market","news"]}
```
Run:
- run_id: `0cc06896-e041-47cc-9824-387237df4e0f`
- status: `succeeded`
- created_at: `2026-05-01T02:22:33.660457Z`
- updated_at: `2026-05-01T02:27:20.240853Z`

Decision:
- final_rating: `Buy`
- provider: `ollama`
- deep_model: `llama3.2:latest`
- quick_model: `llama3.2:latest`

Event timeline:
1. running @ 2026-05-01T02:22:34.362103Z
2. succeeded @ 2026-05-01T02:27:20.301127Z

Artifacts (top 3):
1. memory_log | 8814 bytes | 51d07ed74cd7f947...
2. state_log | 41120 bytes | 4bec9a04c588e942...

## Example 2: NVDA (Completed)
Input:
```json
{"ticker":"NVDA","trade_date":"2026-01-21","selected_analysts":["market","news"]}
```
Run:
- run_id: `f4edc7b4-95f8-448b-90dc-d9e0f98919e7`
- status: `succeeded`
- created_at: `2026-04-30T10:27:51.763796Z`
- updated_at: `2026-04-30T10:30:17.562917Z`

Decision:
- final_rating: `Hold`
- provider: `ollama`
- deep_model: `llama3.2:latest`
- quick_model: `llama3.2:latest`

Event timeline:
1. running @ 2026-04-30T10:27:52.590275Z
2. succeeded @ 2026-04-30T10:30:17.592663Z

Artifacts (top 3):
1. memory_log | 5800 bytes | a463ca6a1ba27a74...
2. state_log | 42983 bytes | 559c4c88164ef9a6...
3. state_log | 45811 bytes | 151bced1e62d8f90...

## Example 3: Failure-path Receipt (Completed with Error)
Input:
```json
{"ticker":"NVDA","trade_date":"2026-01-20","selected_analysts":["market","news"]}
```
Run:
- run_id: `23e617d3-d2a6-4e82-955a-44c5d044b2d2`
- status: `failed`
- error_message: `Connection error.`

Event timeline:
1. running @ 2026-04-30T10:25:53.825496Z
2. failed @ 2026-04-30T10:25:55.365934Z

Interpretation:
- This confirms failure-path I/O is also auditable end-to-end (error propagated to run status and events).

## Example 4: MSFT (Completed, Higher Latency)
Input:
```json
{"ticker":"MSFT","trade_date":"2026-01-23","selected_analysts":["market","news"]}
```
Run:
- run_id: `726acf0f-7705-43c8-9111-833e68e2f970`
- status: `succeeded`
- last_updated: `2026-05-01T02:30:58.236675Z`
- events captured: `2`

Interpretation:
- This run completed successfully but took longer than the AAPL/NVDA examples.
- Worker logs showed structured-output validation fallback events; this resilience behavior can increase latency.

## I/O Interpretation Across Examples

What the search tool is doing operationally:
1. API validates and enqueues requests.
2. Worker claims queued jobs and executes TradingAgents graph.
3. System emits lifecycle events (running/succeeded/failed).
4. Decision payload and artifact manifests are persisted and queryable.

Observed behavior from real runs:
- Success path verified repeatedly (AAPL, NVDA, MSFT).
- Failure path verified (connection-error example).
- Higher-latency behavior observed on MSFT with fallback behaviors in logs.

## Evidence Files Used
- `tmp/aapl_run.json`, `tmp/aapl_events.json`, `tmp/aapl_decision.json`, `tmp/aapl_artifacts.json`
- `tmp/nvda_run.json`, `tmp/nvda_events.json`, `tmp/nvda_decision.json`, `tmp/nvda_artifacts.json`
- `tmp/fail_run.json`, `tmp/fail_events.json`
- `tmp/msft_run.json`, `tmp/msft_events.json`
