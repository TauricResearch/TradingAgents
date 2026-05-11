# Debrief: Multi-Agent Worktree Infrastructure

**Session:** 2026-05-11  
**Duration:** ~2 hours  
**Branch:** `feat/alerts-phase2`

---

## What We Did

### 1. Identified the Problem

Multi-agent development on a single repo had a coordination gap:
- Agents share files → collisions
- No isolation → need fragile claim-before-touch protocol
- td session management is per-branch, not per-worktree

### 2. Researched SideCar + td

- **SideCar** creates git worktrees via `n` (create workspace), streams agent output
- **Marcus's td** has `-w` flag and `.td-root` resolution — existing infrastructure
- **The gap:** td doesn't auto-detect worktrees and write `.td-root`
- **The solution:** Write `.td-root` in each worktree pointing to repo root → shared `.todos/`

### 3. Built Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/worktree-init.ts` | Create/delete worktrees + write `.td-root` | ✅ |
| `scripts/agent-orient.ts` | Session startup: git + td + in-flight + collisions | ✅ |
| `scripts/agent-claim.ts` | Claim task (collision check, session label) | ✅ |
| `scripts/agent-log.ts` | Log progress with timestamp | ✅ |
| `scripts/agent-handoff.ts` | Structured handoff (done/remaining/decisions) | ✅ |
| `scripts/agent-sync.ts` | Sync: git state + collision detection | ✅ |

### 4. Updated Infrastructure

- **Justfile** — `[agent]` group (12 facade recipes), `[worktree]` group (wt-create, wt-list, wt-delete)
- **AGENTS.md** — Replaced dead `playbooks/td-playbook.md` link with actual protocol rules (Rule 0–5)
- **Playbooks** — `playbooks/td-playbook.md` rewritten with worktree model as primary

### 5. E2E Testing

Full end-to-end verification:
- ✅ Worktree creates task → main sees it immediately
- ✅ Main creates task → worktree sees it immediately
- ✅ Same issue count from both locations
- ✅ Cleanup works (delete + branch removal)
- ✅ Shared `.todos/` at repo root — no database copy, no merge step

### 6. Submitted Feature Request

[GitHub Issue #184](https://github.com/marcus/td/issues/184) filed against marcus/td:
> `td init` should write `.td-root` in git worktrees for multi-agent development

**Scope:** Single change — `td init` detects worktree context → writes `.td-root`. No new commands.

---

## Key Insights

### Multi-agent, not multi-user

td + worktrees enable **one person running multiple agents in parallel** on the same repo. Not a shared database across different users — that's a different problem. The convention is managed via session IDs and labels, not database access controls.

### The `.td-root` trick is the key

td already resolves `.td-root` recursively. By writing it in each worktree pointing to repo root, every `td` command in any worktree uses the same shared database. No new td features needed for this to work.

### Worktree isolation > protocol enforcement

The original approach (claim-before-touch + collision detection) is **reactive** — it catches problems after they start. Worktrees are **prophylactic** — the collision literally cannot happen because each worktree is a separate git directory. The claim protocol is still useful for task assignment, but the file-collision problem disappears.

### The feature request is small

Marcus doesn't need to build a worktree management system. He just needs `td init` to detect worktree context and write `.td-root`. That's a 10-line change. Our script proves the pattern.

---

## What Got Left Out

### Per-worktree `.todos/` (Option B)

Not needed. Shared `.todos/` at repo root works fine. Per-worktree DBs would require a sync/merge step that adds complexity without benefit.

### Full SideCar integration

We didn't integrate with SideCar's workspace creation (it already does `git worktree add`). We focused on the td side — `.td-root` auto-detection. If/when Marcus implements this, SideCar's workspaces would automatically get td integration.

### More than 3 worktrees

We set a soft limit of 3 (via `TD_MAX_WORKTREES` env var) to prevent repo sprawl. This is configurable and can be raised if needed.

---

## Files Created/Modified

### Created

| File | Purpose |
|------|---------|
| `scripts/worktree-init.ts` | Worktree management (create/delete/list) |
| `scripts/agent-orient.ts` | Session startup orientation |
| `scripts/agent-claim.ts` | Task claiming with collision check |
| `scripts/agent-log.ts` | Progress logging |
| `scripts/agent-handoff.ts` | Structured handoffs |
| `scripts/agent-sync.ts` | State sync + collision detection |
| `playbooks/td-playbook.md` | Multi-agent coordination protocol |
| `briefs/2026-05-11-td-worktree-feature-request.md` | Feature request document |
| `briefs/2026-05-11-td-worktree-test-results.md` | E2E test evidence |
| `briefs/2026-05-11-td-worktree-issue-draft.md` | Issue draft |

### Modified

| File | Change |
|------|--------|
| `Justfile` | `[agent]` group (12 recipes), `[worktree]` group (3 recipes) |
| `AGENTS.md` | Protocol rules + startup commands |
| `scripts/just-group-menu.ts` | Added `agent` group metadata |
| `briefs/INDEX.jsonl` | Added 4 new entries |
| `playbooks/REGISTRY.jsonl` | Added td-playbook.md |
| `decisions/INDEX.jsonl` | Added 007-barnacle-drydock-location.md |

---

## Next Steps

### Immediate
- [ ] Merge to main when ready (all checks pass)
- [ ] Use `just wt-create <name>` for future epic work
- [ ] Monitor marcus/td#184 for response

### When Marcus Implements the Feature
- [ ] Delete `scripts/worktree-init.ts` (or keep as wrapper for `--task` linking)
- [ ] Update `playbooks/td-playbook.md` to reference native `td init` behavior
- [ ] Remove worktree recipes from Justfile (or keep as shortcuts)

### Long-term
- [ ] Consider SideCar integration for workspace creation
- [ ] Explore `td ws` for cross-worktree task coordination
- [ ] Document multi-agent workflow in `docs/runbook.md`

---

## What Went Well

1. **The problem was clearly bounded** — not "fix multi-agent coordination" but "write `.td-root` in worktrees"
2. **E2E testing before submitting** — verified the solution works before asking Marcus to change anything
3. **Feature request is minimal** — one small change to td, proven by our script
4. **Clear terminology** — "multi-agent, not multi-user" avoids confusion about what problem we're solving

## What Could Be Better

1. **Should have tested `.td-root` auto-detection sooner** — the feature was already there, we just needed to use it
2. **Playbooks were a bit stale** — the `td-playbook.md` reference in AGENTS.md was broken for a while
3. **Index maintenance** — kept having to add missing entries to INDEX.jsonl files

---

## Session Log

- 07:44 — Session start, orientation
- 08:00 — Research: SideCar docs, Marcus's td vs Swatto's td
- 08:28 — Installed Marcus's td (`go install github.com/marcus/td@latest`)
- 08:30 — Discovered `.td-root` resolution already exists
- 08:45 — Wrote `scripts/worktree-init.ts` (first attempt)
- 09:00 — Debugging: `git worktree list --porcelain` has no trailing newline (bun trim issue)
- 09:30 — E2E test: worktree creates task → main sees it ✅
- 09:45 — E2E test: cross-write both ways confirmed ✅
- 09:55 — Cleanup test worktrees
- 10:00 — Updated Justfile, AGENTS.md, playbooks
- 10:15 — Submitted GitHub Issue #184 to marcus/td
- 10:20 — Wrote debrief