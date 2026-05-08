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

**Awaiting prioritization:**
- CLI portfolio command (terminal view of holdings/P&L)
- IG trade history command
- Price alert system
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
