---
name: review
description: Review code for correctness, security, DDD boundaries, and rule compliance
context: fork
allowed-tools: Read, Grep, Glob, Bash
---

Review the file or diff provided in $ARGUMENTS (or the current git diff if no argument given).

**Steps:**
1. Run !`git diff` to get the current diff if no specific file was given.
2. Read each changed file in full for context.
3. Check against `.claude/rules/rules.md`.

**Evaluate for:**
- Logic bugs or incorrect behavior
- Security issues (injection, secrets in code, unvalidated input)
- DDD boundary violations (e.g. domain layer importing infrastructure)
- Missing or inadequate tests
- Naming convention violations
- Type safety gaps
- Unnecessary complexity or abstraction

**Output format — grouped by severity:**

### Critical
> Must fix before merge. Bugs, security issues, broken contracts.

### Warning
> Should fix. Code smell, rule violations, missing tests.

### Suggestion
> Optional improvements. Readability, style, minor refactors.

Be concise. Reference file and line numbers for every finding.
