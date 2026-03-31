# ADR 021 — Auto Run Task Lifecycle Must Be Structured

**Status**: accepted
**Date**: 2026-03-31
**PR**: codex/auto-run-lifecycle-fix (PR#166)

---

## Summary

`LangGraphEngine.run_auto()` previously spawned Phase 2 producer and per-ticker
pipeline work with detached `asyncio.create_task(...)` calls. That allowed
child ticker work to outlive the parent auto-run generator and created a
mismatch between:

- the top-level run status shown by `/api/run/`
- actual in-flight LLM work still executing in the backend process
- logger lifecycle for the root auto run

The fix moves Phase 2 under structured `asyncio.TaskGroup` ownership and puts
auto-run logger finalization in a `finally` block.

---

## Problem

The root FastAPI run tracker only knows about the single task registered in
`agent_os.backend.routes.runs.run_tasks`.

Before this change, `run_auto()` also created internal detached tasks for:

- the Phase 2 pipeline producer
- each queued per-ticker `run_pipeline()` execution

That made the following failure mode possible:

1. the root auto-run generator ends or is closed
2. the route layer marks the run complete / failed / stopped
3. one or more child ticker tasks continue running or flushing events
4. logs still show provider traffic even though `/api/run/` reports no running runs

This is an ownership bug, not just a UI bug.

---

## Decision

Phase 2 concurrency inside `run_auto()` now uses structured task ownership:

- one `TaskGroup` for the producer lifetime
- one nested `TaskGroup` for in-flight ticker pipelines
- queue sentinel emission in `finally`
- explicit async-generator close handling (`GeneratorExit`) so parent shutdown
  cancels descendant ticker work cleanly
- `_finish_run_logger(...)` in `finally` for the root auto run

---

## Consequences

### Good

- Top-level run completion now lines up with descendant pipeline completion.
- Closing or cancelling `run_auto()` tears down in-flight ticker pipelines.
- The root auto logger is finalized on success, failure, stop, and generator close.

### Constraints

- `run_auto()` cannot safely use detached `asyncio.create_task(...)` for child
  work unless that task is fully owned, awaited, and cancelled on every exit path.
- Async generators that yield values while child tasks are running must treat
  `GeneratorExit` as a first-class shutdown path.

---

## Warnings For Future Changes

### 1. Do not add detached child tasks inside run generators

If a task is spawned from `run_scan()`, `run_pipeline()`, `run_portfolio()`, or
`run_auto()`, it must not outlive the generator that owns the run lifecycle.

Preferred rule:

- use `asyncio.TaskGroup`
- keep the group inside the generator scope
- ensure all sentinels / queues are closed in `finally`

### 2. The run store only tracks the root task

`agent_os.backend.routes.runs.run_tasks` does not track descendant work. If
descendant tasks are introduced, the run status will become unreliable unless
those tasks are structurally bound to the root task.

### 3. Logger cleanup must live in `finally`

Run loggers are part of lifecycle correctness, not optional cleanup. New run
modes and rerun paths should always place `_finish_run_logger(...)` in `finally`
so cancellation and early returns do not leak logger state.

### 4. Open sockets are not a trustworthy run-status signal

Persistent HTTP connections to Ollama / OpenRouter may remain established after
the last request due to keep-alive. Use task ownership and run state as the
source of truth, not socket presence alone.

### 5. Regression tests should cover generator close paths

Any future concurrency refactor in `run_auto()` should preserve tests for:

- normal completion
- failure before Phase 3
- graceful stop
- async-generator close while a ticker pipeline is in flight

---

## Verification

The fix was verified with:

- `python -m py_compile agent_os/backend/services/langgraph_engine.py tests/unit/test_langgraph_engine_run_modes.py`
- `pytest -q tests/unit/test_langgraph_engine_run_modes.py -k 'run_auto'`
- `pytest -q tests/unit/test_langgraph_engine_run_modes.py`
