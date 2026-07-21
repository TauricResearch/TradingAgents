---
id: 005
title: "Decide: run execution and concurrency model"
labels: [wayfinder:grilling]
status: closed
assignee: JMAN730
blocked-by: [002]
---

## Question

How does the server execute `TradingAgentsGraph` runs?

- In-process background thread vs subprocess. (Graph is sync and long-running; memory state `reflect_and_remember` lives in-process.)
- Concurrency: single active run vs queue vs parallel runs. (Recommended: single active run + queue-of-one, matches single-user destination.)
- Cancellation: supported? How to stop a mid-flight `graph.stream` loop safely?
- Crash/exception surfacing to the UI.

## Resolution

Decided; design adversarially verified against repo source + installed langgraph 1.2.9 / fastapi 0.135.3 internals (workflow `wf_93975c3e-f68`, verdict "amended" — skeleton confirmed, three substantive corrections).

**Execution model (confirmed skeleton)**
- POST `/api/runs` spawns an asyncio.Task driving the whole run: pre-phases → `graph.astream(init_state, stream_mode=["updates","custom"])` → post-phases. Events append to an in-memory per-run log. SSE endpoint `GET /api/runs/{id}/events` is a pure log-tailer (async generator): replays from Last-Event-ID, then tails. Client disconnect kills only the tailer, never the run. Supersedes 002's phrasing that the SSE generator drives the stream.
- Last-Event-ID arrives only on EventSource auto-reconnect, never on a fresh page load — fresh loads replay from 0 (log covers the whole run). Registry holds a strong task reference (GC safety). uvicorn shutdown cancels the run task; document that server exit kills the active run.
- Single active run; POST while active → 409 with active run id; no queue (nothing in the prototype needs one; the pinned live-run sidebar covers navigate-away). **The one-active invariant counts "draining" runs (below) as active.**
- Lifecycle states: `running | done | failed | cancelled` (+ internal `draining`). Crash → terminal `error` event (message, exception class, last ~20 traceback lines), state=failed. Event log discarded when a new run starts; completed runs re-served from disk (ticket 006).
- No position-returns/reflection endpoint. Note: `reflect_and_remember` no longer exists (removed; CHANGELOG.md:247), but deferred reflection RUNS implicitly in web v1 via the `_resolve_pending_entries` pre-phase and `store_decision` post-phase — include both in draining semantics.

**Correction 1 — cancellation orphans threads (the big one).** `task.cancel()` lands immediately at the current await (not at a node boundary): langgraph's cancel cleanup is prompt, flushes checkpointer writes, records an ERROR write for resume, cannot deadlock (verified in `_runner.py`/`_loop.py`/`_executor.py`). BUT the in-flight sync node / `to_thread` pre-phase keeps running detached in its executor thread (uninterruptible; still bills; can mutate the lockless TradingMemoryLog and module-global config after the run is marked cancelled). Fix adopted: per-run dedicated ThreadPoolExecutor installed via `loop.set_default_executor()` at run start; on terminal transition the run enters **draining** and the single-run slot stays held until `old_pool.shutdown(wait=True)` (awaited in background) completes; explicit LLM SDK timeouts so server exit can't hang on atexit thread joins. Cancel endpoint idempotent.

**Correction 2 — raw "updates" events are MBs, not KBs.** Updates carry full tool outputs (15–60KB CSVs, news dumps), each analyst report twice, and cumulative debate histories re-sent per event. Fix adopted: run task projects updates server-side into slim typed events (agent status flips, report-section strings, tool-call name+args, message previews — the CLI's projection loop, cli/main.py:1132-1232, is the reference); only projected, id-stamped events enter the replay log (~50–150KB/run, report sections dominating).

**Correction 3 — web path must faithfully re-implement `propagate()` scaffolding.** Checklist: override `get_graph_args()`'s hardcoded `stream_mode:'values'` (propagation.py:82); add an async checkpointer helper (repo's `get_checkpointer` is sqlite3/sync-only — web needs aiosqlite + `AsyncSqliteSaver` + thread_id/checkpoint_step/clear_checkpoint parity); post-phases must include `store_decision` and `clear_checkpoint` (trading_graph.py:469-481), not just `_log_state`/`process_signal`, or the deferred-reflection memory loop silently breaks; write report sections to disk incrementally (mirror cli/main.py:1063-1079) or "partial reports on disk" is false for cancelled/failed runs. Also: `"custom"` stream mode currently emits nothing — zero `get_stream_writer` calls exist in tradingagents/ — so web code adds writers (or relies on projected updates only at first).

Threading facts verified: sync nodes run via `run_in_executor(None, …)` in the event loop's default pool (min(32, cpu+4)); starlette/anyio use a separate pool (capacity 40) — no cross-framework exhaustion; nodes are sequential (~1–5 threads/run); the per-run executor swap also removes repeated-cancel starvation.
