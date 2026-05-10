# Current Work Plan

**Last updated:** 2026-05-10
**State:** Open for next prioritization.

---

## Completed

### Epic DEMO-EXEC-001 DONE ✓ — Demo Execution Pipeline (ses_a9b880)
- S01: `--yes` flag for non-interactive execution
- S02: `--dry-run` for plan preview without order placement
- S03: Stop/limit distances use plan values (`entry - stopLoss`, `target1 - entry`)
- S04: `analysis_id` column added to `trades` table + `--analysis-id` arg
- S05: `trading analyze --execute` chains analysis → IG execution
- Commit: `c6fcf00`

### Epic CANONICAL-REGISTRY DONE ✓ — Portable playbook + script registry
- S01: `canonicals/` created, seeded with 15 playbooks (ses_0dd889)
- S02: `reg-mine.ts` — extraction mechanism
- S03: `reg-import.ts` — import mechanism
- S04: `reg-promote.ts` — promotion review
- S05: Script registry `reg-sync-scripts.ts`
- S06: Just recipes + canonical docs updated
- Commits: `50e46c2` → `c707c4f`

### Epic UNIFIED-CLI-001 DONE ✓ — Unified Trading CLI
- S01-S06 complete. Entry: `trading <command>` with 12+ subcommands.

---

## TD Status (ses_a9b880)

**In review:**
- `td-030156` DEMO-EXEC-001-S01 (approved, pending merge)
- `td-31d9b2` DEMO-EXEC-001-S03 (approved, pending merge)
- `td-53f14e` DEMO-EXEC-001-S05 (approved, pending merge)

**Closed this session:**
- `td-a237a5` DEMO-EXEC-001-S02 (dry-run) ✓
- `td-ceded2` DEMO-EXEC-001-S04 (analysis_id column) ✓

---

## Open Epics — Next Prioritization

| Epic | Description | Priority |
|------|-------------|----------|
| **ALERTS-PHASE2** | Custom user-defined alerts (alerts table, CRUD CLI, dashboard view) | P1 |
| **ALERTS-PHASE3** | Continuous monitoring daemon + dashboard alert feed | P2 |
| Dashboard UX | Further UI improvements | P3 |

---

## Mandatory Protocol

**Session start:**
```bash
git status && git branch -v   # confirm on feature branch, not main
just check                    # must be green
td usage --new-session        # new identity
td ws current                 # any active work to resume?
td reviewable                 # what needs your review?
```

**Branching rule:**
- On `main` with code to write → `git checkout -b feat/<name>` first
- Never commit directly to `main` (even if you're the only reviewer)
- Merge via PR → forces pre-PR checklist

**Every change:**
```bash
just check   # clean before touching
# ... make change ...
just check   # must pass before commit
git commit -m "type(scope): what"
```

---

## What to Avoid

| Pattern | Fix |
|---------|-----|
| Route `.ts` with JSX | Rename to `.tsx`, update imports |
| React-style `style={{...}}` | Use `style="background:#fff3cd"` (CSS string) |
| Extracting JSX before data layer | Always extract `lib/{route}-data.ts` first |
| Forward-fix on broken state | Revert to last known-good, then diagnose |
| `server/` paths in tests/docs | Use `src/server/` |
| Working on `main` directly | Always branch first |

---

## Active Branches

- `main` — current (clean, two commits ahead of origin)
- `ses_a9b880` — current work session (DEMO-EXEC-001 complete)
- `ses_0dd889` — previous work session (CANONICAL-REGISTRY complete)