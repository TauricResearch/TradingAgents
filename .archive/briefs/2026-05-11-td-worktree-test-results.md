# TD Worktree Integration — Test Results

**Date:** 2026-05-11  
**Script:** `scripts/worktree-init.ts` (Bun/TypeScript)  
**td version:** v0.44.0 (Marcus's Go version)

---

## Test Summary

✅ **All tests passed.** The shared database model works exactly as expected.

## Test Cases

### Test 1: Worktree creation with .td-root

```
$ bun scripts/worktree-init.ts alerts-test --base main

Created worktree: /Users/petersmith/Dev/GitHub/TradingAgents-alerts-test
Branch: alerts-test
Written: .td-root → /Users/petersmith/Dev/GitHub/TradingAgents

Shared .todos/ database at: /Users/petersmith/Dev/GitHub/TradingAgents/.todos/
```

- `.td-root` file written in worktree, pointing to repo root
- Git worktree list shows both main and worktree
- No separate `.todos/` created in worktree

### Test 2: td resolves shared database from worktree

```
# From worktree:
$ cd TradingAgents-alerts-test && td whoami
SESSION: ses_c4f670

# From main:
$ cd TradingAgents && td whoami
SESSION: ses_134041
```

- Different sessions (correct — session = branch + agent type)
- **Same database** (verified below)

### Test 3: Cross-write — worktree creates task, main sees it

```
# From worktree:
$ cd TradingAgents-alerts-test
$ td create "EO2E TEST: worktree writes shared DB" --type feature --priority P3
CREATED td-8c5772

# From main:
$ td list --status open
td-8c5772  [P3]  EO2E TEST: worktree writes shared DB  feature  [open]
```

✅ Task created in worktree **immediately visible** in main.

### Test 4: Cross-write — main creates task, worktree sees it

```
# From main:
$ td create "EO2E TEST: main writes to shared DB" --type feature --priority P3
CREATED td-71f531

# From worktree:
$ cd TradingAgents-alerts-test && td list --status open
td-8c5772  [P3]  EO2E TEST: worktree writes shared DB  feature  [open]
td-71f531  [P3]  EO2E TEST: main writes to shared DB  feature  [open]
```

✅ Task created in main **immediately visible** in worktree.

### Test 5: Same issue count from both locations

```
# From main:
$ td info | grep "Issues:"
Issues: 21 total

# From worktree:
$ td info | grep "Issues:"
Issues: 21 total
```

✅ Same count confirmed.

### Test 6: Cleanup — worktree deletion + branch cleanup

```
$ bun scripts/worktree-init.ts alerts-test --delete
Deleting worktree: /Users/petersmith/Dev/GitHub/TradingAgents-alerts-test
Removed worktree. Branch 'alerts-test' deleted.

$ git worktree list
/Users/petersmith/Dev/GitHub/TradingAgents  92c16a8 [feat/alerts-phase2]
```

✅ Clean deletion. No orphaned state.

---

## Mechanism

The solution relies on **existing td behavior** — no new features needed:

1. **`.td-root` file convention** — td resolves `.td-root` from CWD upward. Writing the repo root path in `.td-root` inside the worktree makes `td` find the shared `.todos/` at repo root automatically.

2. **No database copy** — The worktree never has its own `.todos/`. Every `td` command (in any worktree or in main) resolves to the same SQLite file at `.todos/issues.db` in the repo root.

3. **No merge step** — When a worktree is deleted, its `.td-root` goes with it. The shared database stays intact. Tasks, logs, handoffs from that worktree remain in the shared DB.

---

## Implementation

```bash
# Create worktree + write .td-root (our script)
git worktree add ../TradingAgents-<name> -b <name>
echo "/path/to/repo/root" > ../TradingAgents-<name>/.td-root

# That's it. Now td in that worktree auto-resolves to shared DB.
cd ../TradingAgents-<name>
td usage --new-session  # uses .todos/ at repo root
```

---

## Feature Request Simplification

The feature request reduces to: **"Make `td init` write `.td-root` automatically when run inside a git worktree."**

Current workaround: `scripts/worktree-init.ts` does this manually.  
Desired behavior: `td init` inside a worktree detects it's in a worktree (via git config or worktree metadata) and writes `.td-root` pointing to the parent repo root.

Alternatively, document the `.td-root` convention in td docs so users know to create it manually or via a helper script.

---

## Files Modified/Created

| File | Purpose |
|------|---------|
| `scripts/worktree-init.ts` | Worktree creation script with `.td-root` support |
| `briefs/2026-05-11-td-worktree-feature-request.md` | Feature request document |
| `Justfile` (updated) | `wt-create`, `wt-list`, `wt-delete` recipes |
| `playbooks/td-playbook.md` | Multi-agent protocol |
| `scripts/agent-*.ts` | Agent coordination scripts |

---

## Recommendation to Marcus

1. **Test the `.td-root` workaround** — it works today without any td changes
2. **Consider making `td init` auto-write `.td-root`** when run inside a worktree
3. **Document the convention** — users creating worktrees manually need to know to write `.td-root`
4. **No database copy needed** — the shared model (Option A) is simpler than per-worktree DBs

---

## Related

- marcus/td#94: "Limit of one work session at a time is restrictive" — worktrees solve this
- marcus/sidecar#221: "Worktree: Support scheduling tasks for agents"
- marcus/sidecar workspaces plugin — already creates worktrees, but without `.td-root` integration