# Architecture Learnings

## Phase 1: Conditional Logic Simplification

- Identified highly repetitive conditional logic for agents (market, news, social, fundamentals).
- Replaced identical `should_continue_*` methods with a single factory method `make_should_continue`.
- This adheres to DRY principles, making the conditional logic concise, easier to maintain, and simpler to test. The `setup.py` was updated to use this factory instead of dynamic `getattr`.

## Phase 2: Decoupling API and Graph Topology

- Identified tight coupling in `agent_os/backend/routes/runs.py` where graph dependency trees (like `_SCAN_RERUN_DESCENDANTS`) were hardcoded.
- Abstracted this into `get_scanner_descendants` inside `tradingagents/graph/scanner_setup.py`.
- This allows the graph component to own its topology, while the API simply queries it for reruns. This ensures changes to the graph automatically propagate to the API without modifying routes.

## Phase 3: Auto-Run Completion Barrier And Human Decision Gate

- Observed in run `01KN0QTY60VHHJTJ5WA04S33D3` that the auto workflow could move into portfolio management without durable proof that every queued ticker pipeline had reached a terminal artifact.
- The root cause was orchestration state, not a broad tool outage. The run mostly showed graceful tool skips, but Phase 2 still lacked a hard completion barrier before Phase 3.
- Added a terminal-artifact check in `LangGraphEngine.run_auto()` so queued tickers must resolve to `completed`, `aborted`, or an explicit incomplete/failure record before portfolio logic can proceed.
- Added an `awaiting_decision` runtime state so AgentOS can pause before Phase 3, present incomplete tickers to the user, retry only the selected ones, and then either pause again or continue.
- Preserved this decision state in persisted run metadata so reloading the UI or restarting the backend does not silently lose the pending choice.

## Warnings For Future Changes

- Do not treat "pipeline generator returned" as equivalent to "ticker is safe for portfolio stage". The durable source of truth is the saved analysis artifact and its terminal status.
- Do not collapse graceful skips, aborted analyses, and missing artifacts into one generic "failure" bucket. The UI decision prompt needs ticker-specific reasons to support informed retry choices.
- Any new auto-run branch that can pause must update all three layers together:
  - backend run status persistence
  - websocket terminal-state signaling
  - frontend stream status handling
- If `awaiting_decision` is changed or renamed, update the route layer, websocket payload, stream hook, history UI, and tests in the same change. A partial update will strand runs in a pseudo-running state.
- When introducing new sub-run execution keys, keep root run logger cleanup in a `finally` block. This regression was easy to introduce once auto pause/retry logic split the flow across methods.
