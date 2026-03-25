# ADR 016 — PR#106 Review Findings: Logging Strategy & MongoDB Models

**Status**: accepted
**Date**: 2026-03-25
**PR**: copilot/increase-observability-logging (PR#106)
**Reviewer**: Claude Code (PR#107 review)

---

## Summary

This ADR documents the bugs and architectural gaps found during the review of
PR#106 (observability logging + MongoDB report store + reflexion memory), along
with the solutions applied.

---

## Logging Strategy

### Finding 1 — LangChain callback never wired into graph execution

**Problem**: `RunLogger.callback` was created but never passed to
`astream_events()` or the LangGraph graph config.  No LLM events would be
captured in the JSONL log.

**Solution**: Wire `rl.callback` into all three `astream_events()` calls
(`run_scan`, `run_pipeline`, `run_portfolio`) via the `config={"callbacks": [rl.callback]}`
parameter.

### Finding 2 — `log_tool_call` and `log_vendor_call` never called

**Problem**: These methods exist on `RunLogger` but nothing invokes them from
`run_tool_loop` or `route_to_vendor`.

**Solution**: Both call-sites are now wired:
- `run_tool_loop` (`tradingagents/agents/utils/tool_runner.py`) calls
  `rl.log_tool_call()` on every tool invocation (success, failure, unknown tool).
- `route_to_vendor` (`tradingagents/dataflows/interface.py`) calls
  `rl.log_vendor_call()` on every vendor call (success and failure with fallback).

### Finding 3 — `threading.local` incompatible with asyncio

**Problem**: `set_run_logger` / `get_run_logger` used `threading.local()`.
Since asyncio runs all coroutines on one thread, concurrent pipelines (via
`asyncio.gather` in `run_auto`) share the same thread-local slot.

**Solution**: Replace with `contextvars.ContextVar` which is correctly isolated
per asyncio task.

### Finding 4 — `run_auto` log lands in flat date directory

**Problem**: `_finish_run_logger(run_id, get_daily_dir(date))` writes to the
flat date directory instead of a run-namespaced path.

**Status**: Acceptable for V1.  Each sub-phase already writes its own
namespaced log.  The top-level auto-run log is a summary.

### Finding 5 — JSONL log not emitted in real time

**Problem**: Events are buffered in memory until `_finish_run_logger`.

**Status**: Acceptable for V1.  Consider periodic flush for long-running auto
runs in a future PR.

---

## MongoDB Models

### Finding 6 — `list_pm_decisions` returns raw ObjectId

**Problem**: The `find()` query returned full documents including `_id: ObjectId`,
which is not JSON-serializable.

**Solution**: Add `{"_id": 0}` projection to the `list_pm_decisions` query.

### Finding 7 — `created_at` type inconsistency

**Problem**: `MongoReportStore` stores `created_at` as native BSON `datetime`;
`ReflexionMemory` stores it as an ISO 8601 string.  Within separate collections
this is consistent, but creates maintenance confusion.

**Solution**: `ReflexionMemory.record_decision()` now stores native `datetime`
when writing to MongoDB, and only converts to ISO string for the local JSON
fallback (which has no datetime type).

### Finding 8 — No TTL index

**Problem**: Reports accumulate indefinitely in MongoDB.

**Status**: *Deferred to a follow-up issue*.  Requires a retention policy
decision before implementation.

### Finding 9 — Synchronous `pymongo` in async FastAPI

**Problem**: All MongoDB calls block the asyncio event loop.

**Status**: Acceptable for V1.  Plan `motor` migration before production
deployment.

### Finding 10 — `MongoClient` created per instance

**Problem**: Each `MongoReportStore` instantiation creates a new `MongoClient`
with its own connection pool.

**Status**: Acceptable for V1.  Plan singleton via FastAPI app lifespan.

### Finding 11 — `ensure_indexes()` not called in `__init__`

**Problem**: Indexes were only created when going through the factory.
Direct instantiation skips them.

**Solution**: Move `ensure_indexes()` call into `MongoReportStore.__init__`
so indexes are always created regardless of construction path.

### Finding 12 — `write_latest_pointer`/`read_latest_pointer` use global `REPORTS_ROOT`

**Problem**: These functions use the global `REPORTS_ROOT` module constant,
ignoring `ReportStore._base_dir`.  When the base dir differs via env vars
(`PORTFOLIO_DATA_DIR`, `TRADINGAGENTS_REPORTS_DIR`), the pointer file lands
in the wrong directory tree.

**Solution**: Add an optional `base_dir` parameter to both functions, defaulting
to `REPORTS_ROOT`.  `ReportStore` now passes its `_base_dir` to both calls.

---

## Holding Reviews Bug

### Finding 13 — `save_holding_review` called with wrong arguments

**Problem**: In `run_portfolio`, `store.save_holding_review(date, portfolio_id, reviews)`
passed `portfolio_id` as the ticker argument and the full reviews dict (keyed
by ticker) as data.  This created a single file named after the portfolio
instead of one file per ticker.

**Solution**: Iterate over the reviews dict:
```python
if isinstance(reviews, dict):
    for ticker, review_data in reviews.items():
        store.save_holding_review(date, ticker, review_data)
```

---

## Consequences & Constraints

### MUST

- All `astream_events()` calls **MUST** pass `rl.callback` in the config to
  capture LLM metrics in the run log.
- `set_run_logger` / `get_run_logger` **MUST** use `contextvars.ContextVar`,
  not `threading.local`.
- `write_latest_pointer` / `read_latest_pointer` **MUST** accept a `base_dir`
  parameter and callers **MUST** pass it when their base differs from
  `REPORTS_ROOT`.
- `MongoReportStore.__init__` **MUST** call `ensure_indexes()`.

### SHOULD

- Plan `pymongo` → `motor` migration before production deployment.
- Add TTL index strategy after retention policy is decided.
