# Ticker Accuracy Agent Background Run Limits Design

## Goal

Add configurable limits so the Ticker Accuracy Agent cannot overload the system with background past runs:

- a per-cycle scheduling cap
- a runtime concurrent-job cap

## Requirements

1. Add two persisted Ticker Accuracy Agent config fields:
   - max_background_runs_per_cycle
   - max_concurrent_background_runs
2. Expose both fields in the Agent Manager / Ticker Accuracy Agent section of the settings panel.
3. Include both limits in the agent strategy prompt so the LLM can plan within the configured bounds.
4. Enforce both limits server-side:
   - cap the number of scheduled runs per cycle
   - prevent starting new background jobs when the concurrent cap is reached

## Proposed Values

- max_background_runs_per_cycle: default 5
- max_concurrent_background_runs: default 2

## Architecture

### Config Layer

web/server/ticker_agent/config.py owns the persisted config schema. Both fields are added to AgentConfig, loaded from disk, and returned by config_to_dict().

web/server/ticker_agent/router.py accepts both fields through AgentConfigIn.

### Agent Prompt

_build_strategy_prompt() includes the configured limits in the current-state block and instructions. This gives the agent explicit context about the maximum number of background runs it may request.

### Execution Layer

_execute_plan() applies the per-cycle cap before scheduling and checks active running background jobs before each ackground_runs.start() call.

### Background Orchestrator

web/server/background_runs.py exposes a small helper for counting active running jobs and validates the concurrent cap inside start() so both agent-scheduled and manually-started jobs obey the same runtime limit.

## Error Handling

If the per-cycle cap is reached, _execute_plan() logs the limit and skips remaining plan items.

If the concurrent cap is reached, _execute_plan() logs the skip and leaves the job unscheduled. The agent will have another opportunity on a future cycle.

Manual API callers receive a clear validation error if they attempt to start a background job above the concurrent cap.

## Testing

Add or update tests for:

- config persistence includes both new fields
- agent prompt contains both limits
- per-cycle plan slicing
- concurrent cap enforcement in background-run startup
- settings panel rendering and update flow where practical

## Scope

This change is limited to Ticker Accuracy Agent background-run limits and the existing background-run orchestrator. It does not change the historical analysis drawer UI or existing manual background-run job controls.
