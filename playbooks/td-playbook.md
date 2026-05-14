# TD Playbook — Solo Workflow

> This playbook defines how to work on the TradingAgents project using `td` for task management.
> For the archived multi-agent version, see `archive/playbooks/td-playbook.md`.

---

## Session Startup

At the start of every session:

```bash
just orient    # see branch, git status, last commit, in-flight tasks
git fetch origin
```

---

## Claiming Work

Before editing a file, claim its task:

```bash
td start td-abc123       # start work on a task
td log "started"         # log progress
```

If the task is claimed by another session, comment requesting handover:

```bash
td comment td-abc123 "I'd like to work on this — can you handoff?"
```

---

## Progress Logging

After substantive changes:

```bash
td log "completed phase 1, found issue with X"
```

---

## Pre-Commit Gate

Before every commit:

```bash
just check
```

---

## Ending Work

Capture context before closing:

```bash
td handoff td-abc123 --done "schema updated" --remaining "dashboard route"
td review td-abc123           # submit for review
```

---

## Branch Hygiene

- **Never commit directly to `main`**
- **Always branch** before starting work: `git checkout -b feat/<name>`
- **One epic per branch** — stack if dependent
- **Run `just check`** before every commit

---

## TD Labels Convention

| Label | Meaning |
|-------|---------|
| `claimed-by:<session>` | Active session working this task |
| `blocked` | Task is blocked, not available |
| `needs-review` | Ready for human review |

---

## Common Commands

```bash
td current              # what you're working on
td list                 # all open tasks
td list --status in_progress   # in-flight tasks
td next                 # highest priority open issue
td context td-abc123    # full context for a task
td ws start "Epic: X"   # start a work session for an epic
td ws tag td-abc123 ... # tag tasks to workspace
td ws end               # end current workspace
```

---

## Related

- `AGENTS.md` — Project identity and coding rules
- `playbooks/conventions-playbook.md` — Coding conventions