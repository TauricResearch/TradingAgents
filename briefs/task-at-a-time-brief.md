# Task-at-a-Time + Context Re-Orientation Brief

**Date:** 2026-05-19  
**Inspired by:** GSD-2 / CDS-2 by TÂCHES (Lex Christopherson), gsd-build/GSD-2 (7K stars, MIT)
**Source:** `docs/momentum-trading-with-eodhd.md` (context), GitHub `gsd-build/GSD-2`
**Status:** Draft — awaiting approval

---

## Problem Statement

Current workflow: user picks a task from `td usage`, works on it across potentially many turns, accumulates context, may drift or lose orientation.

GSD-2's insight: **context rot is the primary failure mode** of long agent sessions. The solution is not better prompting — it's structural discipline:
- One task per context window
- Clear re-orientation between tasks
- Explicit handoff artifacts (what was done, what comes next)
- Monitor context usage and trigger re-orient proactively

---

## Core Principles (from GSD-2)

1. **Task must fit in one context window.** If it can't, split it.
2. **Fresh context per task.** No accumulated garbage from prior tasks.
3. **Re-orientation is explicit.** After completing a task, agent explicitly summarises what was done and what the next task requires.
4. **Context window monitoring.** Warn when context is 35% consumed; critical warning at 25%. Trigger re-orient when thresholds are hit.
5. **File-based state persists recovery.** If session dies mid-task, re-orient reads surviving artifacts.
6. **Stuck detection.** Repeated tool call patterns = stop, report, let user re-orient.

---

## Implementation Plan

### Phase 1 — Context Window Monitoring

**Files:** `playbooks/td-playbook.md` (update), `~/.pi/agent/AGENTS.md` (update)

Add to the agent instructions:

```
Context window thresholds:
- >65% used: normal — continue
- ≤35% remaining: warning — "Approaching context limit. Keep remaining work focused."
- ≤25% remaining: critical — summarise progress, prepare for /clear or re-orient
- ≤15% remaining: stop work, hand off cleanly before /clear

Re-orient trigger events:
- After completing a task (td done)
- When context reaches 25% remaining
- When tool call pattern repeats (stuck detection)
- On explicit user request
```

### Phase 2 — Re-Orientation After Task Completion

**File:** `playbooks/td-playbook.md`

After `td done` is called, agent produces a brief handoff summary:

```
## Task Handoff

Completed: [task name]
Key decisions: [1-3 bullets]
Next task: [from td usage]
Next task brief: [1-2 sentences on what the next task requires]

Context window: [X%] remaining — [status: normal / warning / critical]
```

This gives the Impartial Spectator a clean entry point for the next task.

### Phase 3 — Stuck Detection

**File:** `playbooks/td-playbook.md`

Monitor tool call patterns. If the same tool (Read/Edit/Bash) is called 10+ times with no file modification:
- Stop, summarise progress
- Ask user: continue, re-orient, or escalate

This is the "5 consecutive Read calls with no Edit" pattern from GSD-2 adapted for our use case.

### Phase 4 — Auto-Clear with Handoff (Future)

When context hits critical threshold automatically:
- Summarise current state to a handoff note
- Clear context
- Present handoff note as the start of the next session

This is analogous to GSD-2's "compact" command + session recovery.

---

## Changes to Existing Files

| File | Change |
|------|--------|
| `playbooks/td-playbook.md` | Add context window thresholds, re-orient procedure, stuck detection rules |
| `~/.pi/agent/AGENTS.md` | Add context monitoring + re-orient to Scottish Enlightenment instructions |
| `docs/data-sources.md` | Add reference to GSD-2 (source archive) |

---

## Not in Scope

- GSD-2's full agent framework (milestone/slice/task hierarchy, worktree isolation, parallel execution)
- LangGraph workflow changes in `tradingagents/`
- File-based state machine overhaul

**Scope is discipline, not architecture.** The pi agent harness already has fresh sessions per task. This brief adds the monitoring and re-orientation scaffolding.

---

## Testing

```bash
# Verify context monitoring fires at threshold
# Run a long task, check for warning at ~65% context

# Verify re-orientation fires after td done
td usage
# complete a task
td done <task-id>
# verify handoff summary appears

# Verify stuck detection
# perform repeated Read calls without Edit
# verify agent stops and asks for direction
```

---

## Reference

- GSD-2 source: https://github.com/gsd-build/GSD-2
- Key concepts: fresh context per task, task-must-fit-context-window, file-based recovery, context pre-loading, stuck detection, milestone/slice/task hierarchy
- GSD-2's `gsd-context-monitor.js` hook: injects context warnings at 35%/25% remaining
- GSD-2's context compaction: runs when context budget is exhausted

---

*Scottish Enlightenment Note: The problem is not the agent's capability — it is the context's integrity. Clean handoffs and explicit re-orientation are the Humean antidote to accumulated confusion.*