# Brief: Add Bridge and SSE Tests

**Date:** 2026-05-14
**Status:** Open

---

## Task: Add test coverage for the Python bridge and SSE streaming endpoints

**Objective:** The Python bridge (`scripts/py/analyze_stream.py`) and the SSE endpoint (`src/server/routes/analysis.ts`) are the most critical data flow in the application and have zero test coverage. Add tests.

## What

- [ ] Add Python-side tests for `analyze_stream.py`:
  - [ ] Test `emit()` produces valid JSON-line output
  - [ ] Test `_inject_position_context()` writes correct markdown format
  - [ ] Test error handling: malformed input args produce `{"event": "error", ...}`
  - [ ] Test timeout path: long-running graph execution is properly terminated
  - [ ] Mock `TradingAgentsGraph.propagate()` to test the streaming layer without calling real LLMs
- [ ] Add TypeScript-side tests for the SSE endpoint (`src/server/routes/analysis.ts`):
  - [ ] Test that `POST /api/analyze` returns SSE content-type header
  - [ ] Test that the subprocess is spawned with correct arguments
  - [ ] Test that valid JSON lines from stdout are forwarded as SSE events
  - [ ] Test that malformed stdout lines are handled without crashing the stream
  - [ ] Test that subprocess crash propagates as `{"event": "error", ...}`
  - [ ] Test that analysis results are persisted to the `analyses` table on `complete` event
  - [ ] Test that decisions are auto-saved to the `signals` table
- [ ] Add heartbeat forwarding test: heartbeat events on stderr reach the browser as SSE events
- [ ] Verify existing `just check` and test commands still pass

## How to Verify

- [ ] Run `just test-smoke` — Python tests pass
- [ ] Run `bun test tests/bridge.test.ts` — TypeScript tests pass
- [ ] `just check` passes
- [ ] Python tests run in CI without requiring LLM API keys (mocked)
- [ ] Edge case: empty ticker or invalid date returns `error` event, not a crash
- [ ] Edge case: two concurrent analysis requests don't corrupt each other's data

## Technical Notes

- Python tests: use `unittest.mock` to patch `TradingAgentsGraph` and `sys.stdout`. Tests should run without API keys.
- TypeScript tests: use Bun's built-in test runner with mocked subprocess (mock `spawn` to return a controlled stream of lines). No need to actually call Python.
- Add a test file `tests/bridge/` for Python-side and `tests/bridge.test.ts` for TypeScript-side.
- The `just test-smoke` marker is `smoke` — use that for the Python bridge tests so they run with the existing smoke suite.
- Risk: mocking `spawn` is fragile across Bun versions. Abstract the subprocess call behind the shared utility from brief-consolidate-server-lib, then mock the utility.

---

## Done

When all `[ ]` items are checked and verified.
