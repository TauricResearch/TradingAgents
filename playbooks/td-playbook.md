# TD Playbook — Multi-Agent Coordination Protocol

> This playbook defines how multiple AI agents coordinate work on the same branch
> without colliding. It lives inside the project silo so every agent sees it on arrival.
> **Every agent session is a distinct identity.** Multiple agents can work in parallel
> if they follow these rules.

---

## Core Principle

**Claim before touch.** Never edit a file until you have:
1. Claimed the owning task (`bun scripts/agent-claim.ts <id>`)
2. Verified no other session has claimed it
3. Linked your working files to the task

---

## Session Startup Checklist

Run at the start of every new session, in order:

```bash
# 1. Orient: see what's in flight
bun scripts/agent-orient.ts

# 2. Sync: check git state + collisions
bun scripts/agent-sync.ts

# 3. Get next action
bun scripts/agent-orient.ts --next
```

---

## Claiming Work

### Before touching any file

```bash
# Claim a task (checks collision, labels with session ID)
bun scripts/agent-claim.ts td-abc123

# Check what files the task owns
bun scripts/agent-sync.ts --collisions
```

### One epic per session

Each session works one epic at a time. Tag relevant tasks to your workspace:

```bash
td ws start "Epic: My Feature"
td ws tag td-abc123 td-def456
```

### If a task is already claimed

1. **Request handover** via comment:
   ```bash
   td comment td-abc123 "@ses_123456: I'd like to work on this — can you handoff?"
   ```
2. **Wait** for the owning agent to run `bun scripts/agent-handoff.ts td-abc123`
3. **Then** claim with `bun scripts/agent-claim.ts td-abc123`

---

## Logging Progress

After every substantive change, log it:

```bash
bun scripts/agent-log.ts td-abc123 "completed phase 1, found issue with X"
bun scripts/agent-log.ts td-abc123 "blocked on BRS-002 — waiting for drydock dir"
```

Use `--blocked` flag if you're stuck:
```bash
bun scripts/agent-log.ts td-abc123 "waiting on IG API token" --blocked
```

---

## Handoff Protocol

**Before closing a task**, capture structured context for the next agent:

```bash
bun scripts/agent-handoff.ts td-abc123 \
  --done "schema updated" \
  --done "CLI subcommands added" \
  --remaining "dashboard route" \
  --decision "used alerts table over separate conditions table"

# Then close
td close td-abc123
```

The handoff command creates a machine-readable record that `td show` will surface for the next agent.

---

## Ending a Session

```bash
# 1. Capture handoffs for all in-progress tasks
bun scripts/agent-handoff.ts td-abc123 --done "done" --remaining "next agent: finish X"
# ... repeat for all tasks

# 2. Sync and confirm no uncommitted work left behind
bun scripts/agent-sync.ts

# 3. End workspace (if using one)
td ws end
```

---

## Branch Hygiene

- **Never commit directly to `main`**
- **Always branch** before starting work: `git checkout -b feat/<name>`
- **One epic per branch** — stack if dependent
- **Run `just check`** before every commit

---

## TD Labels Convention

Use these labels on tasks to signal state:

| Label | Meaning |
|-------|---------|
| `claimed-by:<session>` | Active session working this task |
| `blocked` | Task is blocked, not available |
| `needs-review` | Ready for human review |

---

## Troubleshooting

### "Task already claimed by another session"
→ Don't force-claim. Comment on the task requesting handover.

### "I'm about to edit a file someone else is working on"
→ Check `bun scripts/agent-sync.ts --collisions` first. If there's a conflict, comment on the task before touching files.

### "I started work without claiming first"
→ Run `bun scripts/agent-claim.ts <id>` now, then `bun scripts/agent-log.ts <id> "retroactively claimed"` to backfill the log.

### "My session died mid-work"
→ On reconnect: `bun scripts/agent-sync.ts` to see what you had. Reclaim your tasks if they're still open.

---

## Related

- `AGENTS.md` — Project identity, coding rules, failure modes
- `debriefs/plans/current.md` — Current work plan and priority order
- `playbooks/conventions-playbook.md` — Coding conventions
