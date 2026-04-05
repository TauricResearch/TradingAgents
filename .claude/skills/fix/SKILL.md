---
name: fix
description: Diagnose and fix a bug from an error message, failing test, or description
disable-model-invocation: true
---

Fix the bug described in $ARGUMENTS (error message, test name, or plain description).

**Steps:**
1. If a test name is given, run it: `pytest <test> -x --tb=long` and read the full traceback.
2. Identify the root cause — read the relevant source files before touching anything.
3. Apply the **minimal** change that fixes the issue. Do not refactor surrounding code.
4. Re-run the failing test to confirm it passes.
5. Run the full suite `pytest --tb=short` to confirm no regressions.
6. Summarize: what was wrong, what was changed, and why.

**Do not:**
- Add unrelated cleanups or improvements.
- Suppress errors with broad try/except.
- Skip hooks or tests to force a passing state.
