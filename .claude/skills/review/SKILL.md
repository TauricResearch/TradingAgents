---
name: review
description: Review code for correctness, security, responsibility boundaries, and rule compliance
context: fork
allowed-tools: Read, Grep, Glob, Bash
---

Review the file or diff provided in $ARGUMENTS (or the current git diff if no argument given).

**Steps:**
1. Run `git diff --staged` (and `git diff` if nothing is staged) to understand the changes.
2. Read each changed file in full for context.
3. Check against `.claude/rules/rules.md`.

**Evaluate for:**
- Logic bugs or incorrect behavior
- Security issues (injection, secrets in code, unvalidated input)
- Responsibility boundary violations:
  - `cli/` importing from `tradingagents/` is OK; reverse is not
  - `dataflows/` must not contain LLM calls or agent logic
  - `agents/` must delegate data fetching to `dataflows/` via `route_to_vendor()`
  - `graph/` must not do direct data fetching or prompt construction
  - `llm_clients/` must not contain business logic
- Missing or inadequate tests
- Naming convention violations
- Type safety gaps
- Unnecessary complexity or abstraction
- New data sources not registered in `dataflows/interface.py`
- New agent roles not wired in `graph/setup.py`
- New @tools not re-exported in `agents/utils/agent_utils.py`

**Output format — grouped by severity:**

### Critical
> Must fix before merge. Bugs, security issues, broken contracts.

### Warning
> Should fix. Code smell, rule violations, missing tests.

### Suggestion
> Optional improvements. Readability, style, minor refactors.

Be concise. Reference file and line numbers for every finding.
