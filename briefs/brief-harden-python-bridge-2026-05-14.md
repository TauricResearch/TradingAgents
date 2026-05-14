# Brief: Harden Python Bridge

**Date:** 2026-05-14
**Status:** Open

---

## Task: Add timeout, heartbeat, and real-time streaming to the Python subprocess bridge

**Objective:** The single Python bridge (`scripts/py/analyze_stream.py`) is the most critical data flow in the project and has no safety net — add timeout enforcement, heartbeat events, and stream agent reports as they happen rather than batched at the end.

## What

- [ ] Add a heartbeat event (`{"event": "heartbeat", "data": {"tick": N}}`) emitted every 15s during LLM processing so the browser can distinguish "still thinking" from "hung"
- [ ] Add a configurable timeout (default: 240s matching the SSE idleTimeout) on the Python subprocess — kill and emit error if exceeded
- [ ] Stream agent reports and debate rounds as they are produced by `TradingAgentsGraph`, not batched at the end of `graph.propagate()` (currently lines 114-132 of `analyze_stream.py` emit everything after the fact)
- [ ] Extract LLM config from hardcoded defaults into CLI args so the dashboard can pass provider/model
- [ ] Add a `retry` flag so the server-side SSE handler can re-spawn the subprocess once on transient failure

## How to Verify

- [ ] Run `just check`
- [ ] Start `just serve-test`, trigger an analysis, observe heartbeat events in the SSE stream (browser dev tools)
- [ ] Kill the Python process mid-analysis, confirm timeout error reaches the browser within 5s of the threshold
- [ ] Verify agent reports appear progressively in the analysis tab, not all at once at the end
- [ ] Edge case: zero-position ticker still emits `complete` without error
- [ ] Edge case: very long analysis (>4 min) is properly terminated

## Technical Notes

- Current `analyze_stream.py` implementation: 158 lines, single file, no heartbeat, no timeout, reports batched at end
- The SSE handler in `src/server/routes/analysis.ts` already reads stdout line-by-line — it can forward heartbeat events without changes
- Heartbeat should use `stderr` not `stdout` to avoid interfering with the JSON-line protocol
- Timeout: use `subprocess.run(timeout=...)` in Python or `AbortSignal.timeout()` in the Bun `spawn()` — pick one layer, don't double-wrap
- Real-time streaming requires either: (a) modifying `TradingAgentsGraph` to accept a callback (violates "never fork core"), or (b) running the graph in a background thread and polling agent state — approach (b) is preferred but needs careful state access
- Alternative to (b): patch `TradingAgentsGraph.propagate()` at the bridge level using Python's `monkeypatch` on the graph's step function — fragile but doesn't touch core files
- Simplest approach: wrap `graph.propagate()` in a thread, poll `final_state` progressively via injected hooks. If impossible, add heartbeat + timeout now and defer real-time streaming

---

## Done

When all `[ ]` items are checked and verified.
