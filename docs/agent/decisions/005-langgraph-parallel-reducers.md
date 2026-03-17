---
type: decision
status: active
date: 2026-03-17
agent_author: "claude"
tags: [langgraph, state, parallel, scanner]
related_files: [tradingagents/agents/utils/scanner_states.py]
---

## Context

Phase 1 runs 3 scanners in parallel. All write to shared state fields (`sender`, etc.). LangGraph requires reducers for concurrent writes — otherwise raises `INVALID_CONCURRENT_GRAPH_UPDATE`.

## The Decision

Added `_last_value` reducer to all `ScannerState` fields via `Annotated[str, _last_value]`.

## Constraints

- Any LangGraph state field written by parallel nodes MUST have a reducer.

## Actionable Rules

- When adding new fields to `ScannerState`, always use `Annotated[type, reducer_fn]`.
- Test parallel execution paths to verify no concurrent write errors.
