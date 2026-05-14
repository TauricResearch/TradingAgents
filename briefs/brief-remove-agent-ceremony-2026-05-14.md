# Brief: Remove Agent Coordination Ceremony

**Date:** 2026-05-14
**Status:** Open

---

## Task: Replace the 5-file, 678-line agent coordination system with a minimal alternative

**Objective:** The `agent-claim.ts` → `agent-log.ts` → `agent-handoff.ts` pipeline (5 scripts, 678 lines, 15 justfile recipes) is designed for 5+ agents concurrently editing the same files. For a solo or small-team project, this ceremony exceeds the problem it solves. Replace with a minimal alternative.

## What

- [ ] Audit current usage: check `.todos/` database, agent claim records, and handoff files to understand what's actually in flight
- [ ] Archive `scripts/agent-claim.ts`, `scripts/agent-log.ts`, `scripts/agent-handoff.ts`, `scripts/agent-sync.ts`, `scripts/agent-orient.ts` (move to `archive/` or remove)
- [ ] Replace the 15 justfile agent recipes (`just agent-claim`, `just agent-log`, `just agent-handoff`, etc.) with at most 2 recipes:
  - `just orient` — single script that shows: current branch, git status, last commit time (replaces 306-line agent-orient.ts)
  - `just sync` — `git fetch origin && git status --short` (replaces 105-line agent-sync.ts)
- [ ] Remove `AGENTS.md` references to the multi-agent coordination protocol (claim-before-touch, work sessions, handoff)
- [ ] Update `playbooks/td-playbook.md` if it references the old agent scripts
- [ ] Verify `just check` still works — it currently calls `bun scripts/td-orphans.ts || true` which depends on td state

## How to Verify

- [ ] Run `just check` — zero errors
- [ ] `just orient` shows branch, git status, last commit time in under 2s
- [ ] `just sync` shows remote vs local state
- [ ] No remaining references to `agent-claim`, `agent-handoff`, `agent-log`, `agent-sync`, `agent-orient` in `justfile` or `AGENTS.md`
- [ ] Edge case: `.todos/` database or td state is not corrupted — td commands (`td current`, `td list`) still work if used independently

## Technical Notes

- The original scripts are well-structured but solve a coordination problem that `git` already solves. Git's merge conflict resolution + `just check` as a pre-commit gate provides the same safety with less code.
- If multi-agent collaboration becomes a real bottleneck in the future, the scripts are in version history — they can be restored.
- The `agent-orient.ts --next` mode (300+ lines of TD session analysis, workspace queries, task prioritization) is a real product idea but not a necessary one for the current team size.

---

## Done

When all `[ ]` items are checked and verified.
