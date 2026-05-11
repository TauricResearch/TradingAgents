# Current Work Plan

**Last updated:** 2026-05-11
**State:** BARNACLE-SCRUBBER next, awaiting multi-agent ops conventions (ses_134041)
**Session:** ses_134041

---

## Completed (This Session — ses_a9b880)

### DEMO-EXEC-001 ✓ — Demo Execution Pipeline
- S01: `--yes` flag for non-interactive execution
- S02: `--dry-run` for plan preview without order placement
- S03: Stop/limit distances use plan values
- S04: `analysis_id` column added to `trades` table
- S05: `trading analyze --execute` chains analysis → IG execution
- Commit: `c6fcf00`

### Runbook + Ops Infrastructure ✓ — ses_a9b880
- `trading/justfile` — dedicated ops CLI with IG credentials from skate
- `docs/runbook.md` — full operations manual
- `trading/README.md` — quick reference card
- `.gitignore` — fixed `/Justfile` pattern
- AGENTS.md — branching protocol added
- All committed to `main` (0101eaa)

### Registry Infrastructure ✓ — ses_0dd889
- Playbook registry scripts: `reg-mine.ts`, `reg-import.ts`, `reg-promote.ts`, `reg-sync-scripts.ts`
- Just recipes for registry operations
- Templates created for briefs, debriefs, decisions, playbooks

---

## Completed (This Session — ses_06bd59)

### ALERTS-PHASE2 ✓ — Custom User-Defined Alerts
- SQLite `alerts` table with condition types: price_below/above, pct_change_day/week, price_cross
- CRUD CLI: `trading alerts create|list|delete|check` subcommands
- Alert matching engine (`alerts-engine.ts`) — pure function, no I/O
- Telegram dispatch (`telegram.ts`) — Bot API, MarkdownV2, graceful degradation
- Dashboard `/alerts` route + HTMX view with triggered banner + create form
- `just check-alerts` / `just check-alerts --fire` recipes
- Commit: `75f2263`

---

## Open Epics — Next Prioritization

### BARNACLE-SCRUBBER [P1] — Barnacle Removal System
**Next epic.** Non-interactive scrubber for playbook documentation.
- Decisions resolved: drydock at `decisions/drydock/`, OpenRouter/Gemini2.5-flash, Gum escalation pipeline
- Brief: `briefs/barnacle-scrubber-plan.md` | Decision: `decisions/007-barnacle-drydock-location.md`
- TD epic: `ws-ab7d` (BRS-001 through BRS-007)
- **Awaiting:** multi-agent ops conventions before coding starts

### ALERTS-PHASE3 [P2] — Continuous Monitoring Daemon
- `barnacle-scan.ts` monitoring daemon
- Polling loop with configurable interval
- Dashboard alert feed / SSE stream

### Dashboard UX [P3]
- Further UI improvements

---

## Known Context

- **IG Demo**: Live, connected via skate credentials
- **Communication channels**: Telegram account available — integration point for alerts
- **Demo account balance**: CFD £10,062 | Spreadbet £10,000
- **Decision record:** `decisions/007-barnacle-drydock-location.md` — drydock at `decisions/drydock/`

---

## Mandatory Protocol

**Session start:**
```bash
git status && git branch -v   # confirm on feature branch, not main
just check                    # must be green
td usage --new-session        # new identity
td ws current                 # any active work?
td reviewable                 # what needs review?
```

**Branching rule:**
- On `main` with code to write → `git checkout -b feat/<name>` first
- Never commit directly to `main`
- Merge via PR → forces pre-PR checklist

**Every change:**
```bash
just check   # must be clean before touching
# ... make change ...
just check   # must pass before commit
```

---

## What to Avoid

| Pattern | Fix |
|---------|-----|
| Route `.ts` with JSX | Rename to `.tsx`, update imports |
| React-style `style={{...}}` | Use `style="background:#fff3cd"` (CSS string) |
| Extracting JSX before data layer | Always extract `lib/{route}-data.ts` first |
| Forward-fix on broken state | Revert to last known-good, then diagnose |
| Working on `main` directly | Always branch first |
