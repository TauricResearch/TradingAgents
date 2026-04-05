---
name: pr
description: Create a pull request with a structured summary from the current branch diff
disable-model-invocation: true
allowed-tools: Bash
---

Create a pull request for the current branch against $ARGUMENTS (default: `main`).

**Steps:**
1. Run !`git log main..HEAD --oneline` to list all commits in this branch.
2. Run !`git diff main...HEAD --stat` for a file-level overview.
3. Derive the PR title: `<type>(<scope>): <summary>` — max 70 characters.
4. Write the PR body using this structure:

```
## Summary
- <bullet 1>
- <bullet 2>
- <bullet 3>

## Changes
- <domain/file>: <what changed>

## Test plan
- [ ] Unit tests pass: `pytest --tb=short`
- [ ] No ruff/mypy errors: `ruff check . && mypy src/`
- [ ] Manually verified: <describe scenario>
```

5. Run: `gh pr create --title "<title>" --body "<body>" --base ${ARGUMENTS:-main}`
6. Return the PR URL.

**Do not push** if the branch is not already on remote — ask the user first.
