# Draft: GitHub Issue for marcus/td

## Title

`td init` should write `.td-root` in git worktrees for multi-agent development

## Body

**Context**

Running multiple AI coding agents in parallel on the same repo is a common pattern (one agent per epic, isolated via git worktrees). Each agent needs its own `td` session, but they should share the same task database — so work done in one worktree is immediately visible to all others.

Currently `td` walks up from CWD to find `.todos/`, which means an agent in a worktree either:
- Finds the shared `.todos/` at repo root (if `.td-root` is written manually)
- Or creates a separate `.todos/` in the worktree (isolated, confusing)

**Solution**

When `td init` runs inside a git worktree (detected via `git rev-parse --is-inside-work-tree`), it should write a `.td-root` file in the worktree root pointing to the parent repo root.

This makes the shared-database model work automatically, without any new commands or flags.

**Example**

```bash
# Create worktree
git worktree add ../TradingAgents-feature-x -b feature-x

# Inside worktree — td init writes .td-root automatically
cd ../TradingAgents-feature-x
td init
# → Created: .td-root → /path/to/repo-root

# Now td in worktree resolves to shared .todos/ at repo root
td whoami      # new session
td list        # sees all tasks from all worktrees
```

**Evidence**

Tested and documented: [briefs/2026-05-11-td-worktree-test-results.md](./briefs/2026-05-11-td-worktree-test-results.md)

E2E verification:
- Worktree creates task → main sees it immediately
- Main creates task → worktree sees it immediately
- Same issue count from both locations
- Cleanup works cleanly (delete worktree, `.td-root` goes with it)

**Related**

- #94 ("Limit of one work session at a time is restrictive") — worktrees solve the parallelism problem
- SideCar workspaces plugin already creates worktrees; this completes the td integration

**Scope**

Single change: `td init` detects worktree context → writes `.td-root`. All other td behavior unchanged. No new commands needed.

**Notes for Marcus**

- `.td-root` resolution already exists in td (`-w` flag + recursive search)
- We're using this today via a helper script (`scripts/worktree-init.ts`) — works fine, but `td init` auto-detection would make it frictionless
- No database copy needed — shared `.todos/` at repo root is the right model for multi-agent on single-user

---

*Multi-agent, not multi-user: td + worktrees enable one person running multiple agents in parallel on the same repo. Each agent gets its own td session but they cooperate via the shared database. No database sync or merge step needed — worktrees share one `.todos/` at repo root.*