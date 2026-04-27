---
name: refactor
description: Improve code structure without changing behavior
allowed-tools: Read, Grep, Glob, Bash
---

Refactor the code at $ARGUMENTS (file or function) to improve structure without changing behavior.

**Steps:**
1. Read the target code and its tests (if any).
2. Identify improvement opportunities:
   - Extract long functions into smaller helpers (prefix private ones with `_`)
   - Reduce nesting with early returns
   - Replace raw dicts with dataclasses/pydantic models
   - Remove dead code
   - Improve naming (snake_case, predicates for bools)
   - Add missing type hints
3. Apply changes.
4. Run existing tests to verify no behavior change: `pytest --tb=short`.

**Constraints:**
- Keep code in the same package — don't move files between `cli/`, `agents/`, `dataflows/`, `graph/`, `llm_clients/` unless fixing a responsibility violation.
- If fixing a boundary violation (e.g. data fetching in `agents/`), move it to `dataflows/` and update `interface.py` registration.
- Preserve all public interfaces — don't rename exported functions without updating all callers.
