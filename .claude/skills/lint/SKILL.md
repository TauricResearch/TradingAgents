---
name: lint
description: Run ruff + mypy and report issues
allowed-tools: Bash, Read, Grep
---

Run linters on $ARGUMENTS (file or directory path, default: entire project).

**Steps:**
1. Run `ruff check $ARGUMENTS` for style and import issues.
2. Run `mypy $ARGUMENTS --ignore-missing-imports` for type errors.
3. Group findings by file.

**Report format:**
For each file with issues:
- File path and line number
- Issue description
- Suggested fix (if straightforward)

**Auto-fix:** If all issues are safe to auto-fix (import sorting, trailing whitespace, etc.), offer to run `ruff check --fix`.
