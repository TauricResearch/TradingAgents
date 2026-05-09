# Current Work Plan

**Last updated:** 2026-05-07
**State:** All epics from May 6-7 sessions are complete. Open for next prioritization.

---

## Completed (Previous Sessions)

### Epic UNIFIED-CLI-001 DONE ✓ — Unified Trading CLI
- S01-S04: Framework, platform config, shares calc, spreadbet calc
- S05: Script wrappers (seed, sync, backup, summarize)
- S06: Config management (~/.tradingagents/config.json)
- Entry point: `trading <command>` with 9 subcommands

### Epic DEBATE-001 DONE ✓ — Debate Mechanism Fix
- S01: Counter safety (.get("count", 0))
- S02/S03: Adversarial prompt strengthening
- S04: Debate quality metrics (rounds, stance extraction, contested flag)

### PR #9 MERGED ✓ (88 commits, 12,897 additions)
- Tiered directory restructure (src/, scripts/lab/)
- Unicode fixes, IG API client, trade calculator with tests
- Registry system, silo template, conceptual lexicon v2

---

## Current TD Status

**IN_REVIEW:**
- `td-a67291` [P1] DOCS-CLEANUP-2: Fix remaining path drift from review of td-f42750 (impl: ses_02a5c6)
- `td-dc35e0` [P2] CLI-PORTFOLIO: Style trading portfolio with Gum and add just recipe (impl: ses_02a5c6)
- `td-3fda84` [P2] IG-HISTORY: Add trading ig history command for IG platform activity (impl: ses_02a5c6)
- `td-68d979` [P2] ALERTS-PHASE1: Exit plan alerts from existing YAML plans + SQLite prices (impl: ses_02a5c6)
- `td-2be009` [P2] BUYLIST: Contingency playbook - watchlist items with fair value targets (impl: ses_02a5c6)

**Awaiting prioritization:**
- `td-cc1eb9` [P2] CANONICAL-REGISTRY: Build portable playbook and script registry
  - S01: Create canonicals/ directory and seed with existing canonical playbooks
  - S02: Build reg-mine.ts — extraction mechanism
  - S03: Build reg-import.ts — import mechanism
  - S04: Build reg-promote.ts — feedback mechanism
  - S05: Script registry — index reusable scripts
  - S06: Documentation and just recipes
- Price alert system Phase 2: custom user-defined alerts (alerts table, CRUD CLI)
- Price alert system Phase 3: continuous monitoring daemon + dashboard
- Further dashboard UX improvements

---

## Mandatory Before/After

**Every session starts:**
```bash
just check                 # tsc + lint — must be green
```

**Every change:**
```bash
just check                 # clean before touching
# ... make change ...
just check                 # must pass before commit
git commit -m "type(scope): what"
```

---

## What to Avoid (Updated Failure Modes)

| Pattern | Fix |
|---------|-----|
| Route `.ts` with JSX | Rename to `.tsx`, update imports |
| React-style `style={{...}}` | Use `style="background:#fff3cd"` (CSS string) |
| Extracting JSX before data layer | Always extract `lib/{route}-data.ts` first |
| Forward-fix on broken state | Revert to last known-good, then diagnose |
| `server/` paths in tests/docs | Use `src/server/` |
