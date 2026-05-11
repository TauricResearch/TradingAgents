# Playbook: Git Workflow

## Principle
**Never merge to `main` until a PR has been reviewed and approved.**
Code on `main` must always be review-gated. No direct pushes to `main`.

## Workflow

```
dev → PR → review → fix → approve → merge → cleanup
```

### 1. Develop on a feature branch

```
git checkout -b feat/<short-description>
```

- Branch from `main`
- Keep commits focused: one logical change per commit
- Branch naming: `feat/`, `fix/`, `refactor/`, `docs/` prefixes

### 2. Open a PR early

```
gh pr create --title "<verb>: <what and why>" --body "<what changed, why>"
```

- Open the PR as soon as the feature is functional, not when it's perfect
- Include a clear title (imperative verb) and description
- Link to any relevant td issues

### 3. Review

- Reviewers leave comments on the PR
- **NO direct pushes to `main` during review**
- All review feedback is addressed on the feature branch

### 4. Fix review issues

```
# Make fixes on the same feature branch
git add -A
git commit -m "fix: address review feedback on <feature>"
git push origin feat/<short-description>
```

- Fixes go on the **feature branch**, not `main`
- Amend commits if they're small cosmetic fixes:
  ```
  git commit --amend --no-edit
  git push --force-with-lease
  ```
- For substantial review fixes, add a new commit so the history is clear

### 5. Approve and merge

```
# Once all review comments are resolved
gh pr merge --squash --delete-branch <pr-number>
```

- Squash merge keeps `main` linear
- `--delete-branch` cleans up the remote feature branch automatically

### 6. Cleanup

```
git checkout main
git pull origin main
git fetch --prune          # remove stale remote refs
git worktree prune         # if using worktrees
```

## What Not To Do

| Mistake | Why it's bad | Fix |
|---------|-------------|-----|
| Push to `main` before review | Bypasses review gate | Never do this |
| Rebase feature branch onto `main` *after* merging | PR shows zero diff, auto-closes | Rebase *before* merge only |
| Fix review issues on `main` | Makes review meaningless | Fix on feature branch |
| Merge then create a PR | Reverses the process | PR first, merge after |
| Force-push to `main` | Rewrites shared history | Never do this |

## Worktree Usage

When working on multiple features simultaneously:

```
# Create a worktree for a feature branch
git worktree add ../TradingAgents-feat/foo feat/foo

# When done, remove it
git worktree remove ../TradingAgents-feat/foo
git branch -d feat/foo        # local
git push origin --delete feat/foo  # remote (if not auto-deleted by merge)
```

## PR Checklist Before Requesting Review

- [ ] Branch is up to date with `main` (rebase if needed)
- [ ] `just check` passes (lint + type-check)
- [ ] Tests pass
- [ ] PR title uses imperative verb + concise description
- [ ] PR body explains what changed and why
- [ ] No debug code, commented-out blocks, or `console.log`
- [ ] No secrets or API keys in diffs

## Merge Criteria

- [ ] At least one reviewer approval
- [ ] All review comments resolved or dismissed
- [ ] CI checks pass (lint, type-check, tests)
- [ ] No conflicts with `main`

## td Integration

td tracks **what** needs doing. Git tracks **how** it was built.
The two link together at every stage:

```
  td add "Feature X" ─→ git checkout -b feat/x ─→ gh pr create
        ↑                                                    ↓
  td handoff ─→ code on feature branch ←── td start
        ↓
  td review ─→ git push fixes ─→ gh pr merge
        ↓
  td approve ─→ delete branch ─→ td closes issue
```

### Mapping td status to git state

| td status | git state | Action |
|-----------|-----------|--------|
| `open` | No branch or unmerged branch | `td start <id>` → `git checkout -b feat/<slug>` |
| `in_progress` | Feature branch, WIP commits | Code, commit, push |
| `in_review` | PR open, awaiting feedback | `td handoff <id>` + `gh pr create` |
| `done` | PR merged, branch deleted | `td approve <id>` + cleanup |

### Workflow commands (combined)

```bash
# 1. Pick up next issue
td next
td start td-XXXX

# 2. Create branch from issue ID
git checkout -b feat/td-XXXX-short-desc

# 3. Work normally (commit often, push regularly)

# 4. Open PR when ready for review
git push -u origin HEAD
gh pr create --title "$(td context td-XXXX | head -1)"

# 5. Signal review readiness
td handoff td-XXXX

# 6. Reviewer: check PR, test, then approve/reject
td review td-XXXX    # inspect
td approve td-XXXX   # or td reject td-XXXX

# 7. After merge: clean up
git checkout main && git pull origin main
git fetch --prune
git worktree prune
```

### Branch naming from td issues

- Include the td ID in the branch name: `feat/td-12345-feature-name`
- This makes it trivial to trace code back to the originating task
- GitHub PR body should reference the td issue

### Anti-patterns (td + git)

| Mistake | Why it's bad |
|---------|-------------|
| Commit to `main` without a td issue | No audit trail |
| `td handoff` without opening a PR | Reviewer has nothing to review |
| `td approve` before PR is merged | Issue is done but code isn't |
| Delete branch before `td approve` | Loses review context |
| Multiple td issues in one PR | Blames the wrong issue when things break |
