# Playbook: Task Management with td

**Tool:** `td` — local task management CLI
**Reference:** `td usage --new-session` for full command reference

---

## Core Workflow

```text
td start <id>      → begin work
td log "msg"       → log progress
td handoff <id>    → capture state (REQUIRED before stopping)
td review <id>     → submit for review
```

---

## Session Management

Run `td usage --new-session` at the start of every conversation (or after `/clear`).

```bash
td usage --new-session     # new session, see current tasks
td usage -q               # quiet (hide instructions after first read)
```

Sessions track identity — a reviewer cannot be the same session as the implementer.

---

## Task Lifecycle

```
open → in_progress → in_review → done/closed
         ↑
      td start <id>
```

| Command | When | Who |
|---|---|---|
| `td start <id>` | Begin work on an issue | Implementer |
| `td log "msg"` | Log progress, decisions | Implementer |
| `td handoff <id>` | Capture state before stopping | Implementer |
| `td review <id>` | Submit for review | Implementer |
| `td approve <id>` | Close in_review work | **Reviewer (different session)** |
| `td reject <id>` | Send back to open | **Reviewer (different session)** |

---

## The Review Constraint

**You cannot approve tasks you implemented.**

This is enforced by `td approve` and `td close`. The reviewer must be a different session identity.

### Solo context (one agent)

- Implementer: agent working on tasks
- Reviewer: **the user** approving via `td approve <id>`

The user is a separate td identity and can approve any task. Alternatively, start a second agent session as the reviewer:

```bash
# In a separate terminal — reviewer agent
td usage --new-session
td reviewable        # see tasks awaiting review
td approve <id>      # close approved work
```

### Team context (multiple agents)

Each agent has its own session. Agent A implements, submits for review (`td review`), Agent B approves.

---

## Epic Workflow

Large work is grouped into epics (briefs in `briefs/epic-*.md`).

```bash
# Create epic story tasks
td add "EPI-001-S01: Story title" --points 3 --labels feat
td add "EPI-001-S02: Story title" --points 5 --labels feat

# Track epic in debrief
echo "Epic: DASH-001 | Status: in_progress" >> debriefs/debrief-$(date +%Y-%m-%d).md
```

---

## Common Commands

```bash
td list                    # all tasks (default: open + in_progress)
td list --json             # machine-readable
td status --json           # session + review state
td next                    # highest priority open issue
td critical-path           # what unblocks the most work

td ws start "name"         # start a named work session (multi-issue)
td ws tag <ids>            # associate issues with current session
td ws handoff              # end session, generate handoffs for all tagged

td add "title" --points 3 --labels feat,backend  # create task
td add "title" --minor                          # self-reviewable task
td close <id> "reason"                          # admin closure (dups, won't-fix)
```

---

## Handoff Format

When `td handoff` is called, it captures:
- Git commit + changes since start
- Summary of what was done
- Next steps

For cross-agent handoffs, also record:
- Current file state (what changed)
- Outstanding questions or blockers
- Any decisions made that need to be preserved

```bash
# Before stopping work:
td handoff <id>
# This records state — reviewer can `td context <id>` to resume
```

---

## New Session Checklist

When starting a new session (or after `/clear`):

1. `td usage --new-session` — reset session context
2. `td list` — see what's in progress and open
3. `td ws current` — see current work session (if any)
4. Read `briefs/epic-*.md` — understand the epic context
5. Pick up where previous session left off using `td context <id>`

---

## Error Handling

**"Error: cannot approve: you were involved with implementation"**
→ The implementer cannot self-approve. Get a reviewer (user or separate agent).

**"Warning: No handoff recorded"**
→ `td ws handoff` wasn't called before ending a session. Resumable with `td ws start <session-id>`.

**"Warning: issue not found: message text"**
→ Second argument to `td close` was interpreted as an issue ID. Use: `td close <id> "reason string"` — issue ID comes first.

---

## Review Process for Solo Agent

When working alone:

1. Implementer agent completes a story
2. Implementer calls `td handoff <id>` to capture state
3. User reviews the work (reads the commit, checks the code)
4. User runs `td approve <id>` to close the task
5. If issues found, user runs `td reject <id>` with feedback — task goes back to `open`

The handoff captures everything the reviewer needs to evaluate the work.