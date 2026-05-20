# Brief: Task-at-a-Time + Context Re-Orientation

**Date:** 2026-05-19  
**Inspiration:** GSD-2 by TÂCHES (gsd-build/GSD-2, MIT)  
**Status:** Implementation brief

---

## Goal

Add context window monitoring and explicit re-orientation to the existing td-based solo workflow. No new files, no architecture changes. Two file edits only.

---

## Changes

### 1. `playbooks/td-playbook.md` — add three sections

**A. Context Window Monitoring** (add after "Session Startup")

```markdown
## Context Window Monitoring

Context window thresholds — apply to every session:

| Remaining | Status | Action |
|-----------|--------|--------|
| >35% | Normal | Continue normally |
| ≤35% | Warning | "Approaching context limit. Keep remaining work focused." |
| ≤25% | Critical | Summarise progress, prepare for /clear or re-orient |
| ≤15% | Stop | Complete current atomic step, stop, re-orient before continuing |

These thresholds are *advisory* — the agent uses judgment. But when context is critical,
the agent must not start new complex work without a clean handoff.

Re-orient trigger events:
- Context reaches critical threshold (≤25%)
- Tool call pattern repeats without progress (stuck detection — see below)
- User request

Re-orient means: summarise current state, show what was done, show what comes next,
confirm direction with user before continuing.
```

**B. Stuck Detection** (add after "Progress Logging")

```markdown
## Stuck Detection

During task execution, if the same tool (Read/Edit/Bash) is called 8+ times
with no file modification or state change:

1. Stop current operation
2. Summarise: what was attempted, what happened, what state the files are in
3. Ask user: "Continue in the same direction?", "Change approach?", "Re-orient to next task?"

This prevents the agent from burning context in loops without producing output.
The threshold is 8 — not 5 — to allow for legitimate multi-read phases (searching,
understanding). Below 8, use judgment.
```

**C. Re-Orientation After Task Completion** (add after "Ending Work")

```markdown
## Re-Orientation After td done

After completing a task (`td done`):

1. Produce a brief handoff summary (2-4 lines):
   - What was completed (concise)
   - Key decisions made
   - State of affected files
   - What the next task requires

2. Show context window status: "Context at ~X% — [normal / warning / critical]"

3. Present the next task from `td next` with a 1-line brief

4. Confirm direction with user before continuing

This gives the Impartial Spectator a clean entry point for the next task,
preventing context bleed from the previous task.
```

---

### 2. `~/.pi/agent/AGENTS.md` — add to Scottish Enlightenment instructions

Add to the OPERATIONAL GUIDELINES section, after the existing items:

```markdown
- **Context integrity over momentum.** Do not keep working simply because
  work is in progress. When context reaches critical (≤25% remaining) or
  a task is complete, stop and re-orient. Clean handoffs are more valuable
  than continuous operation.
- **Task-must-fit-context-window.** If a task requires more context than
  remains, complete the current atomic step and hand off. Never start
  complex new work with insufficient context budget.
- **Stuck = stop.** Repeated tool calls with no state change = stop, report,
  ask for direction. Do not burn context in loops.
```

---

## Implementation Steps

1. Edit `playbooks/td-playbook.md` — add sections A, B, C above
2. Edit `~/.pi/agent/AGENTS.md` — add context integrity rule to OPERATIONAL GUIDELINES
3. `just check` — verify no lint/type errors
4. Test: run a session, complete a task, verify re-orientation summary appears

---

## Files Changed

| File | Change |
|------|--------|
| `playbooks/td-playbook.md` | +3 sections (~25 lines) |
| `~/.pi/agent/AGENTS.md` | +3 rules (~5 lines) |

---

## Not in Scope

- Auto-clear with handoff to disk (Phase 4 — future)
- Changes to `tradingagents/` package
- New files or new tooling

---

*One task. Clean handoff. Fresh context. Move on.*