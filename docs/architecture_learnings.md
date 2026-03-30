# Architecture Learnings

## Phase 1: Conditional Logic Simplification

- Identified highly repetitive conditional logic for agents (market, news, social, fundamentals).
- Replaced identical `should_continue_*` methods with a single factory method `make_should_continue`.
- This adheres to DRY principles, making the conditional logic concise, easier to maintain, and simpler to test. The `setup.py` was updated to use this factory instead of dynamic `getattr`.

## Phase 2: Decoupling API and Graph Topology

- Identified tight coupling in `agent_os/backend/routes/runs.py` where graph dependency trees (like `_SCAN_RERUN_DESCENDANTS`) were hardcoded.
- Abstracted this into `get_scanner_descendants` inside `tradingagents/graph/scanner_setup.py`.
- This allows the graph component to own its topology, while the API simply queries it for reruns. This ensures changes to the graph automatically propagate to the API without modifying routes.
