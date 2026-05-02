# Playbook: td — Local-First Task Management

**Essential context, process, and agent coordination tool.**

---

## Why td?

We use `td` because:

1. **Context preservation** — Sessions track work across agent invocations. No "where was I?"
2. **Process visibility** — Issues, handoffs, and reviews make the workflow explicit
3. **Agent coordination** — Multiple agents can work in the same issue space without collision
4. **Local-first** — SQLite in `~/.config/.todos/`. No server, no sync, no vendor lock-in

> We miss it when it's not there. It's that fundamental.

---

## Core Concepts

| Concept | Purpose |
|---------|---------|
| **Issue** | A unit of work. Has ID, title, tags, priority, status |
| **Session** | A work context. Tracks who did what, when |
| **Workspace** | Groups issues for a project or sprint |
| **Handoff** | Captures state when transitioning between agents |
| **Review** | Formal approval before closing |

---

## Essential Commands

```bash
# Start a new session (do this at conversation start)
td usage --new-session

# Create an issue
td add "Implement user auth" --tags auth,backend --priority P1

# Start working
td start <issue-id>

# Log progress
td log "Implemented login endpoint" --result

# Blocked on something?
td log "Waiting for API spec" --blocker

# Mark a decision
td log "Using JWT for auth tokens" --decision

# Done with your part, need review
td handoff <issue-id>
td review <issue-id>

# Someone else reviews and approves
td approve <issue-id>   # Complete
# or
td reject <issue-id>     # Send back
```

---

## Multi-Agent Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ Agent A (Builder)                                               │
│   td add "Build user service" --priority P1                    │
│   td start td-123                                              │
│   ... builds ...                                                │
│   td log "Service complete" --result                            │
│   td handoff td-123                                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Agent B (Operator) — reviews, tests, deploys                    │
│   td review td-123        # Agent A's handoff                   │
│   ... tests ...                                                  │
│   td approve td-123       # Complete the issue                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Session Management

```bash
# New session (clears context tracking)
td usage --new-session

# Label current session
td session "sprint-42"

# View current state
td ws current

# Handoff entire workspace
td ws handoff

# Next priority issue
td next

# Critical path analysis
td critical-path
```

---

## Issue Lifecycle

```
     ┌─────────┐
     │  TODO   │ ← td add
     └────┬────┘
          │ td start
          ↓
     ┌─────────┐
     │ IN PROG │ ← td log (progress, blockers, decisions)
     └────┬────┘
          │ td handoff
          ↓
     ┌─────────┐
     │ REVIEW  │ ← td review
     └────┬────┘
          │ td approve / td reject
          ↓
     ┌─────────┐
     │ DONE    │ ← Complete
     └─────────┘
```

---

## Priority Levels

| Priority | Use |
|----------|-----|
| `P0` | Blocker — everything stops |
| `P1` | This sprint — critical path |
| `P2` | Next — important but can wait |
| `P3` | Backlog — nice to have |

---

## Tags

Tags are free-form. Conventions we use:

- `infra` — Infrastructure
- `docs` — Documentation
- `bug` — Bug fix
- `feat` — New feature
- `refactor` — Code improvement
- `review` — Needs review

---

## Tips

### Start every session fresh
```
td usage --new-session
```
This establishes session identity for review tracking.

### Log decisions, not just progress
```bash
td log "Chose PostgreSQL over MySQL" --decision
```
Later agents know *why*, not just *what*.

### Use blockers sparingly but honestly
```bash
td log "API spec not ready" --blocker
```
Blocks surface early, before they cascade.

### Handoff with context
```
td handoff <issue-id>
```
Include: what was done, what's left, known unknowns.

---

## Troubleshooting

### "No focused issue"
```bash
td start <issue-id>
# or
td ws start "my-workspace"
```

### "Cannot approve issue I implemented"
Correct. External review prevents self-review bias.
Close with self-close exception: `td close <issue-id> --self-close-exception "Reason"`

### Session diverged from reality
```bash
td usage --new-session
td context <issue-id>   # Restore context for an issue
```

### "database is locked" or "database malformed"

**Root cause (historical):** SQLite WAL corruption under concurrent access was fixed by Marcus in td core. If you encounter this, update td to the latest version.

**Recovery:**
```bash
# Reset database if needed
rm -rf .todos
td init
```

---

## Testing

### Smoke Test

Run the full workflow test:
```bash
just td-test
```

This tests 12 steps:
1. Initialize
2. Create issues
3. Start work
4. Log progress
5. Block issues
6. Create dependencies
7. List issues
8. Check blocked
9. Check dependencies
10. Status check
11. Handoff
12. Review submission

**Status:** ✅ Passed — all 12 steps verified working.

---

## Assessment: Uses of td Database

### Current Usage (Coordination Layer)

| Use | Value |
|-----|-------|
| Issue tracking | High — coordination tool |
| Session management | Medium — context continuity |
| Review workflow | High — prevents self-review bias |
| Agent coordination | High — prevents collision |

### Potential Future Uses

| Use Case | Effort | Opinion |
|----------|--------|---------|
| **Time tracking** — log hours per issue | Low | Valuable. We already log progress; add `--hours` flag. |
| **Sprint velocity** — issues completed per week | Low | Useful for retrospectives. |
| **Review turnaround** — handoff → approve latency | Low | Good ops metric. |
| **Agent performance** — error rates, retry counts | Medium | Interesting but requires td schema changes. |
| **Knowledge graph** — issue relationships | High | Overkill. Git + briefs already cover this. |

### Principle

The database should do one thing well: **coordination**. It is persistent, local-first SQLite. Treat it as infrastructure — it works, it persists, move on.

---

## Decision Framework

```
Is td working?          → Use it normally
Is td outdated?         → Update td (SQLite WAL bugs were fixed in recent versions)
Is td completely gone?  → Use git + logs as fallback, reinstall td
```

**Rule:** td serves the work. The work does not depend on td.

---

## Related

- [Edinburgh Protocol Playbook](edinburgh-protocol-playbook.md) — Decision framework
- [Briefs/Debriefs Pattern](briefs-playbook.md) — Pre/post work documentation
- [Agent Ops Playbook](agent-ops-playbook.md) — Human/agent coordination
