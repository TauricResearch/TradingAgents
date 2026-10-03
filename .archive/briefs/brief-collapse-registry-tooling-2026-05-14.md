# Brief: Collapse Registry Tooling

**Date:** 2026-05-14
**Status:** Done

---

## Task: Reduce 10 registry management scripts to 1 main utility + 4 supporting scripts

**Result:** Created `scripts/reg.ts` with subcommands (list, sync, check, enrich, mine, import, promote, state, scripts). Archived 6 unused scripts. Updated justfile registry recipes. Deleted barnacle-scan.ts.

## What

- [x] Audit which registry scripts are actually used — Done: justfile uses reg-list (5 registries), reg-sync, reg-enrich, reg-mine, reg-import, reg-promote, reg-state, reg-sync-scripts, reg-check
- [x] Identify essential functions: list, sync, check (other ops can be direct script calls)
- [x] Create `scripts/reg.ts` with subcommands: `reg list <registry>`, `reg sync [--fix]`, `reg check`, `reg enrich`, `reg mine`, `reg import`, `reg promote`, `reg state`, `reg scripts`
- [x] Retain individual scripts for backward compat: reg-list.ts, reg-check.ts, reg-enrich.ts, reg-sync.ts (used by just check gate)
- [x] Archive unused scripts → moved to archive/scripts/: reg-import.ts, reg-migrate.ts, reg-promote.ts, reg-mine.ts, reg-state.ts, reg-sync-scripts.ts
- [x] Update `justfile` registry recipes (14 updated, 2 removed: barnacle-scan, barnacle-watch)
- [x] Remove `barnacle-scan.ts` — deleted (not archived), registry system simplified
- [x] Verify `just check` still passes — calls reg.ts enrich and reg.ts sync

## How to Verify

- [x] Run `just check` — zero errors
- [x] `just reg-list briefs` works (justfile updated to call reg.ts)
- [x] `bun scripts/reg.ts list briefs` shows same data as old reg-list.ts briefs
- [x] `bun scripts/reg.ts sync` updates indexes without errors
- [x] Archived scripts in archive/scripts/ not callable from justfile
- [x] Edge case: empty registry produces `[]` not a crash

## Technical Notes

- Individual reg-*.ts scripts retained for backward compat (analyze, scripts, etc. may call them directly)
- The reg.ts command provides the canonical interface; individual scripts are fallback/advanced options
- barnacle-scan.ts deleted (not archived) — the registry simplification makes it unnecessary

---

## Done

All items checked. 6 scripts archived, 1 deleted, reg.ts with 9 subcommands created. just check passes.
