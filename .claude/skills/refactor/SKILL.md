---
name: refactor
description: Refactor selected code for clarity and structure without changing behavior
allowed-tools: Read, Grep, Glob, Bash
---

Refactor the code in $ARGUMENTS (or the current selection) without changing its external behavior.

**Steps:**
1. Read the file and the relevant tests.
2. Run the existing tests to establish a baseline: `pytest --tb=short`.
3. Apply improvements — apply only what is clearly beneficial:
   - Extract long functions into smaller, focused ones.
   - Replace magic numbers with named constants.
   - Simplify nested conditionals with early returns.
   - Remove dead code.
   - Fix naming to match conventions in `.claude/rules/rules.md`.
4. Do **not** move logic across DDD layers or change public interfaces.
5. Re-run tests: `pytest --tb=short`. All must pass.
6. Show a brief diff summary of what changed and why.

**Do not:**
- Add new features or error handling not previously present.
- Change behavior to "fix" something that isn't broken.
- Refactor beyond what was asked.
