# Playbook: Task Management with td (Multi-Agent)

**Tool:** `td` — local task management CLI
**Reference:** `td usage --new-session` for full command reference

**Assumption:** Multiple agents (and the user) collaborate on this codebase. Every agent session is a distinct identity. Work is handed off between sessions via `td ws handoff` and `td context <id>`.

---

## Core Rule: Always Use a Work Session

**Never work on individual tasks in isolation.** If a task belongs to an epic, or if you are doing more than one thing, use a work session (`td ws`).

**Why:** Work sessions group related issues. One `td ws handoff` captures state for all tagged issues. The next agent picks up the entire session, not a single task.

```text
# Correct — work session for an epic
td ws start "Epic name"     # create session
td ws tag <id1> <id2> ...  # tag all related tasks
td ws log "progress"        # log to all tagged tasks
td ws handoff               # hand off all tasks at once

# Wrong — individual task juggling (don't do this for epic work)
td start <id1>
td handoff <id1>
td start <id2>
td handoff <id2>
```

---

## When to Create a Work Session

| Scenario | Command |
|---|---|
| Epic with multiple stories | `td ws start "EPI-001: Description"` |
| Refactoring touching 3+ files | `td ws start "Refactor: xyz"` |
| Any task with obvious follow-ups | `td ws start "Feature: abc"` then tag follow-ups as you create them |
| Single isolated bugfix (< 30 min) | `td start <id>` is OK (no ws needed) |

**Rule of thumb:** If you think "I'll need to do X after this," create a work session and tag both tasks.

---

## Session Startup (Every Conversation)

```bash
# 1. Reset session context (always do this first)
td usage --new-session

# 2. See what's happening
#    - What work sessions exist?
#    - What tasks are in progress?
#    - What can I review?
td ws current               # any active work session?
td list                     # open + in_progress issues
td reviewable               # issues awaiting review

# 3. Resume work if there's an active session
#    (another agent may have handed off)
td context <epic-id>        # full epic context
td ws start <session-id>    # resume a specific session
```

**Critical:** If `td ws current` shows an active session, **you are continuing someone else's work**. Read the handoff before changing anything.

---

## Multi-Agent Workflow

```text
Agent A                              Agent B (or User)
─────────────────                    ─────────────────
td ws start "Epic: XYZ"
   ↓
td ws tag <id1> <id2> <id3>
   ↓
[implements...]
   ↓
td ws log "Finished id1, id2 in progress"
   ↓
td ws handoff          ────────→  [session ends]
                                      ↓
                                  td usage --new-session
                                      ↓
                                  td ws current
                                  [sees ws-eb65 handoff]
                                      ↓
                                  td ws start ws-eb65
                                      ↓
                                  [continues id2, id3]
                                      ↓
                                  td ws handoff
```

**Key principle:** An agent never "owns" a task. The work session owns the tasks. Agents borrow the session, do work, then hand it back.

---

## Work Session Commands

| Command | Purpose |
|---|---|
| `td ws start "name"` | Create a new work session |
| `td ws tag <ids...>` | Add issues to the current session |
| `td ws log "msg"` | Log progress to ALL tagged issues |
| `td ws current` | Show session status and tagged issues |
| `td ws handoff` | Hand off all tagged issues simultaneously |
| `td ws start <id>` | Resume a previous session by ID |

**Creating an epic with child tasks:**
```bash
td add "Epic: Refactor holdings" --epic --p1
td add "holdings: extract components" --task --p1 --parent <epic-id>
td add "holdings: add tests" --task --p1 --parent <epic-id>
td add "holdings: update docs" --task --p2 --parent <epic-id>

td ws start "holdings refactor"
td ws tag <child-id-1> <child-id-2> <child-id-3>
```

---

## Task Lifecycle (with Work Sessions)

```
open → in_progress ──→ in_review ──→ done
         ↑                 ↑
      td start /        td review
      td ws tag      (or auto-cascade)
```

**Auto-cascade:** When all child tasks in an epic are in_review, the epic automatically transitions to in_review.

---

## The Review Constraint

**You cannot approve tasks you implemented.** This is enforced by session identity.

| Who | Role | Commands |
|---|---|---|
| **Implementer agent** | Does the work | `td ws start`, `td ws tag`, `td ws log`, `td ws handoff` |
| **Reviewer agent / User** | Evaluates work | `td reviewable`, `td approve <id>`, `td reject <id>` |

**In practice:** The implementer hands off (`td ws handoff`). The user reviews the PR and approves (`td approve <id>`). Or a second agent session acts as reviewer.

---

## Handoff Protocol

**Before stopping work (mandatory):**
```bash
td ws log "Completed: X, Y. Blocked on: Z (needs API key)."
td ws handoff
```

**What the handoff captures:**
- Git state: commit hash, files changed, branch
- Session log: all `td ws log` messages
- Tagged issues: which tasks are in progress
- Implementer session: who did the work

**What the next agent does:**
```bash
td usage --new-session          # new identity
td ws current                   # see active sessions
td context <epic-id>          # read epic context
td ws start <session-id>       # resume session
```

---

## Error Handling

**"No active work session"**
→ You haven't created one. Use `td ws start "name"` before tagging issues.

**"Error: cannot approve: you were involved with implementation"**
→ The implementer cannot self-approve. The reviewer must be a different session. Start a new session (`td usage --new-session`) or let the user approve.

**"Warning: No handoff recorded"**
→ The previous agent didn't call `td ws handoff`. Resume with `td ws start <session-id>` and inspect git state manually.

**"Cannot transition from closed to in_review"**
→ A task was already closed (reviewed + approved). Don't try to review it again.

---

## Solo Agent Checklist

Even when working alone, use work sessions. It creates a clean handoff point for the user to review.

1. `td usage --new-session`
2. `td ws current` — any session to resume?
3. If resuming: `td ws start <session-id>` + `td context <id>`
4. If starting fresh: `td ws start "descriptive name"` + `td ws tag <ids>`
5. Do the work. Log progress: `td ws log "..."`
6. Before stopping: `td ws handoff`
7. User reviews: reads code, runs `td approve <id>`

---

## Quick Reference

```bash
# Startup (always)
td usage --new-session
td ws current
td list

# Work session management
td ws start "name"
td ws tag <id1> <id2>
td ws log "message"
td ws handoff

# Individual tasks (only for isolated work)
td start <id>
td log "message"
td handoff <id>
td review <id>

# Review
td reviewable
td approve <id>
td reject <id>

# Information
td next
td critical-path
td context <id>
```
