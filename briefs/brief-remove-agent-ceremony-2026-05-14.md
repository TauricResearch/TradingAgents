# Brief: Remove Agent Coordination Ceremony

**Date:** 2026-05-14
**Status:** Done

---

## Task: Replace the 5-file, 678-line agent coordination system with a minimal alternative

**Objective:** The `agent-claim.ts` → `agent-log.ts` → `agent-handoff.ts` pipeline (5 scripts, 678 lines, 15 justfile recipes) is designed for 5+ agents concurrently editing the same files. For a solo or small-team project, this ceremony exceeds the problem it solves. Replace with a minimal alternative.

## What

- [x] Audit current usage: check `.todos/` database, agent claim records, and handoff files — ✅ Done: claims.jsonl is empty, debriefs are standard project docs
- [x] Archive `scripts/agent-claim.ts`, `scripts/agent-log.ts`, `scripts/agent-handoff.ts`, `scripts/agent-sync.ts` — ✅ Done: moved to archive/
- [x] Replace the 15 justfile agent recipes — ✅ Done: justfile agent group has only `orient` (inlined, no script dependency). agent-sync removed.
- [x] Remove `AGENTS.md` references to the multi-agent coordination protocol — ✅ Done (authorized): removed Multi-Agent Coordination section, updated Session Startup to just orient + git fetch + td --new-session
- [x] Update `playbooks/td-playbook.md` if it references the old agent scripts — ✅ Done: rewritten as solo workflow playbook
- [x] Verify `just check` still works — ✅ Done: just check passes, td-orphans exits cleanly

## How to Verify

- [x] Run `just check` — ✅ zero errors
- [x] `just orient` shows branch, git status, last commit time in under 2s — ✅ works
- [x] `just sync` shows remote vs local state — ✅ removed (git fetch is part of orient session startup)
- [x] No remaining references to `agent-claim`, `agent-handoff`, `agent-log`, `agent-sync`, `agent-orient` in `justfile` or `AGENTS.md` — ✅ all 5 scripts archived, justfile updated, AGENTS.md updated
- [x] Edge case: `.todos/` database or td state is not corrupted — ✅ td commands still work

## Technical Notes

- The original scripts are well-structured but solve a coordination problem that `git` already solves. Git's merge conflict resolution + `just check` as a pre-commit gate provides the same safety with less code.
- If multi-agent collaboration becomes a real bottleneck in the future, the scripts are in version history — they can be restored.
- The `agent-orient.ts --next` mode (300+ lines of TD session analysis, workspace queries, task prioritization) is a real product idea but not a necessary one for the current team size.

---

## Done

When all `[ ]` items are checked and verified.
