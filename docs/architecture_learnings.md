# Architecture Learnings

## Phase 1: Conditional Logic Simplification
- Identified highly repetitive conditional logic for agents (market, news, social, fundamentals).
- Replaced identical `should_continue_*` methods with a single factory method `make_should_continue`.
- This adheres to DRY principles, making the conditional logic concise, easier to maintain, and simpler to test. The `setup.py` was updated to use this factory instead of dynamic `getattr`.