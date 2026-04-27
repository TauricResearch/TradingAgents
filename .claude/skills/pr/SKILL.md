---
name: pr
description: Create a structured pull request description
context: fork
allowed-tools: Read, Grep, Glob, Bash
---

Create a PR description for the current branch against $ARGUMENTS (base branch, default: `main`).

**Steps:**
1. Run `git log --oneline $(git merge-base HEAD $BASE)..HEAD` to list commits.
2. Run `git diff $BASE --stat` to list changed files.
3. Read changed files for context.

**PR template:**

```
## Summary
<1-2 sentence description of what this PR does and why>

## Changes
- <grouped by package: cli/, agents/, dataflows/, graph/, llm_clients/, tests/>

## Testing
- <what was tested and how>
- <any manual verification steps>

## Checklist
- [ ] Tests pass (`pytest --tb=short`)
- [ ] New data sources registered in `dataflows/interface.py`
- [ ] New @tools re-exported in `agents/utils/agent_utils.py`
- [ ] New agent roles wired in `graph/setup.py`
- [ ] No secrets committed
```

Omit checklist items that don't apply to this PR.
