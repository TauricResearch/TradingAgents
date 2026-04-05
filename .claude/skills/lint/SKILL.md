---
name: lint
description: Run ruff and mypy, then report issues with suggested fixes
disable-model-invocation: true
allowed-tools: Bash, Read
---

Run the full linting and type-check suite for $ARGUMENTS (or the whole project if omitted).

**Steps:**
1. Run ruff: `ruff check ${ARGUMENTS:-.} --output-format=concise`
2. Run mypy: `mypy src/ --ignore-missing-imports`
3. Group all findings by file with line numbers.
4. For each issue, provide a one-line explanation and a suggested fix.
5. Ask before applying any auto-fixes.

**Auto-fixable (only apply if user confirms):**
- `ruff check --fix` for safe auto-fixes.

**Report format:**
```
src/silvie_agent/domain/agent/services.py
  L14  [E501] Line too long (89 > 88) — shorten or wrap
  L22  [ANN201] Missing return type annotation — add `-> None`
```

Do not modify files unless explicitly asked.
