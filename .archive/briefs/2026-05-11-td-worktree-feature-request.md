# Feature Request: td Worktree Integration

**Status:** Submitted as [GitHub Issue #184](https://github.com/marcus/td/issues/184)  
**Date:** 2026-05-11  
**Script:** `scripts/worktree-init.ts`

---

## Request

When `td init` runs inside a git worktree, it should write a `.td-root` file in the worktree root pointing to the parent repo root.

This makes the shared-database model work automatically — no new commands, no flags, no merge step.

**Full E2E test results:** `briefs/2026-05-11-td-worktree-test-results.md`

---

## How It Works

```
TradingAgents/                    ← repo root
├── .todos/                       ← SHARED database (all worktrees)
│   └── issues.db
├── .git/
└── ...

TradingAgents-feature-x/          ← worktree
├── .td-root                     ← "/Users/petersmith/Dev/GitHub/TradingAgents"
└── (no .todos/ — uses repo root's)
```

Every `td` command in any worktree resolves to the shared `.todos/issues.db` at repo root.

**No database copy. No merge step.** When a worktree is deleted, `.td-root` goes with it. The shared database stays intact.

---

## Why This Matters

- **Multi-agent on single-user** — one person running multiple agents in parallel, each in its own worktree
- **No coordination friction** — agents see each other's tasks automatically via shared DB
- **Clean cleanup** — worktree deletion removes `.td-root`, nothing else changes
- **Existing infrastructure** — `.td-root` resolution already exists in td (`-w` flag + recursive search)

---

## Related

- marcus/td#94: "Limit of one work session at a time is restrictive"
- marcus/sidecar#221: "Worktree: Support scheduling tasks for agents"
- SideCar workspaces plugin — already creates worktrees, td integration completes the loop

---

## Current Workaround

Until Marcus implements the auto-detection, use `scripts/worktree-init.ts`:

```bash
bun scripts/worktree-init.ts <name> --base main
# Creates worktree + writes .td-root + links TD task

just wt-list   # show all worktrees
just wt-delete <name>  # clean deletion
```

Or via just recipes:

```bash
just wt-create my-epic          # create
just wt-list                    # list
just wt-delete my-epic          # delete
```