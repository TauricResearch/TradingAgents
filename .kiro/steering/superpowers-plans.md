---
inclusion: manual
---

# Writing Implementation Plans

Use when you have an approved design/spec for a multi-step task, before touching code.

## Overview

Write plans assuming the implementer has zero codebase context. Document everything: which files to touch, complete code, how to test, exact commands. Bite-sized TDD tasks. DRY. YAGNI. Frequent commits.

## Scope Check

If the spec covers multiple independent subsystems, break into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

## File Structure First

Before defining tasks, map out which files will be created or modified:
- Each file should have one clear responsibility
- Prefer smaller, focused files over large multi-purpose ones
- Files that change together should live together
- Follow existing codebase patterns

## Task Granularity

Each step is one action (2-5 minutes):
- "Write the failing test" — one step
- "Run it to verify it fails" — one step
- "Implement minimal code to pass" — one step
- "Run tests to verify they pass" — one step
- "Commit" — one step

## Task Structure

```markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py`
- Test: `tests/exact/path/to/test_file.py`

- [ ] Step 1: Write the failing test
  [complete test code]

- [ ] Step 2: Run test to verify it fails
  Command: `.venv/bin/python -m pytest tests/path/test.py::test_name -x -q`
  Expected: FAIL

- [ ] Step 3: Write minimal implementation
  [complete implementation code]

- [ ] Step 4: Run test to verify it passes
  Command: `.venv/bin/python -m pytest tests/path/test.py::test_name -x -q`
  Expected: PASS

- [ ] Step 5: Commit
  `git add <files> && git commit -m "feat: description"`
```

## No Placeholders — Ever

These are plan failures:
- "TBD", "TODO", "implement later"
- "Add appropriate error handling"
- "Write tests for the above" (without actual test code)
- "Similar to Task N" (repeat the code)
- Steps describing what to do without showing how
- References to types/functions not defined in any task

## Self-Review Checklist

After writing the plan:
1. **Spec coverage** — can you point to a task for each requirement?
2. **Placeholder scan** — any vague instructions or missing code?
3. **Type consistency** — do names/signatures match across tasks?

Fix issues inline. If a requirement has no task, add one.

## Plan Location

Save plans to `.kiro/specs/<feature-name>/tasks.md` (following Kiro spec conventions).
