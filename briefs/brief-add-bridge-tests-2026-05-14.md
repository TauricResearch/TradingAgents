# Brief: Add Bridge and SSE Tests

**Date:** 2026-05-14
**Status:** Done

---

## Task: Add test coverage for the Python bridge and SSE streaming endpoints

**Objective:** The Python bridge (`scripts/py/analyze_stream.py`) and the SSE endpoint (`src/server/routes/analysis.ts`) are the most critical data flow in the application and have zero test coverage. Add tests.

## What

- [x] Add Python-side tests for `analyze_stream.py`:
  - [x] Test `emit()` produces valid JSON-line output
  - [x] Test `_inject_position_context()` writes correct markdown format
  - [x] Test error handling: malformed input args produce `{"event": "error", ...}`
  - [x] Test heartbeat thread emits JSON to stderr at configurable interval
  - [x] Test CLI argument parsing (--timeout, --heartbeat-interval, --llm-*, --retry)
  - [x] Mock `TradingAgentsGraph.propagate()` to test the streaming layer without calling real LLMs
  - [x] Test threaded propagate fills result_holder, catches exceptions, propagates errors
- [x] Add TypeScript-side tests for the SSE endpoint (`src/server/routes/analysis.ts`):
  - [x] Test `parseDecisionEvents()` parses valid decision event from JSON lines
  - [x] Test SSE event schema: all 7 event types (start, heartbeat, agent_report, debate_round, decision, complete, error)
  - [x] Test parseDecisionEvents skips malformed JSON lines without crashing
  - [x] Test parseDecisionEvents defaults to hold when signal missing
  - [x] Test analyze_stream.py output parsing: complete analysis sequence
  - [x] Test heartbeat events do not interfere with decision parsing
  - [x] Test timeout enforcement: AbortController kills subprocess after timeout
  - [x] Test fast script completes before timeout
  - [x] Test edge cases: empty ticker, unicode, very long content, confidence range

## How to Verify

- [x] Run `just test-smoke` — all 19 Python tests pass (via `uv run pytest`)
- [x] Run `bun test tests/bridge.test.ts` — all 27 TypeScript tests pass
- [x] `just check` passes — biome, tsc, import boundaries, db usage, reg-enrich, reg-sync
- [x] Python tests run without requiring LLM API keys (all mocked with unittest.mock)
- [x] Edge case: malformed stdout lines are skipped by parseDecisionEvents
- [x] Edge case: heartbeat events do not interfere with decision parsing
- [x] Edge case: AbortController timeout properly kills subprocess

## Technical Notes

- Python tests use `importlib.util.spec_from_file_location()` to load
  `scripts/py/analyze_stream.py` as an isolated module. This avoids sys.path
  issues with uv vs python discrepancies. Works with both `python -m pytest`
  and `uv run pytest`.
- TypeScript tests use Bun's built-in test runner with real subprocess spawning
  (writes temp Python scripts to tmpdir, spawns, checks output). No mocking of
  spawn required — tests use short-lived scripts that exit cleanly or are
  aborted by AbortController.
- `just test-smoke` (uv run pytest tests/ -v) runs all 158+ pytest tests including
  the 19 new bridge tests (marked @pytest.mark.smoke).
- Pre-existing failure in tests/test_backup_hledger.py::TestBackupScript::test_verify_succeeds
  (hledger command not available in environment) — unrelated to bridge tests.

## Deferred

- Server SSE route tests (`POST /api/analyze`) would require refactoring
  `src/server/routes/analysis.ts` to use a `runPythonScript()` utility from
  `subprocess.ts`, then mocking that utility. Brief recommends this as a
  larger refactor. Tests for parseDecisionEvents, output schema, and timeout
  enforcement provide sufficient coverage for the bridge interface.

---

## Done

2026-05-14. Files added:
- tests/test_analyze_stream.py (19 tests, @pytest.mark.smoke)
- tests/bridge.test.ts (27 tests, bun test)