# Brief: Collapse Registry Tooling

**Date:** 2026-05-14
**Status:** Open

---

## Task: Reduce 10 registry management scripts to 1-2 utilities

**Objective:** The `scripts/reg-*.ts` family (10 files: reg-check, reg-enrich, reg-import, reg-list, reg-migrate, reg-mine, reg-promote, reg-state, reg-sync, reg-sync-scripts) manages JSONL indexes of the project's own documents. This is a documentation tool that has spawned more maintenance code than the documents it indexes. Collapse to 1-2 scripts.

## What

- [ ] Audit which registry scripts are actually used (check `justfile` recipes, recent git history, and `briefs/INDEX.jsonl`)
- [ ] Identify the essential functions: (a) listing registry contents, (b) syncing indexes from disk, (c) checking for stale entries
- [ ] Collapse into at most 2 scripts:
  - `scripts/reg.ts` with subcommands: `reg list <registry>`, `reg sync`, `reg check`
  - Optionally a separate `reg-enrich.ts` or `reg-mine.ts` if they provide distinct value that can't be subcommand'd
- [ ] Archive unused scripts (`reg-import.ts`, `reg-migrate.ts`, `reg-promote.ts`, `reg-mine.ts`, `reg-state.ts`, `reg-sync-scripts.ts`) — move to `archive/` or mark as deprecated
- [ ] Update `justfile` registry recipes to use the new scripts
- [ ] Remove `barnacle-scan.ts` — it exists to find stale conventions in the registry system itself. If the registry system is simplified, the barnacle scanner has no job.
- [ ] Verify `just check` still passes — it currently calls `reg-sync.ts --all`

## How to Verify

- [ ] Run `just check` — zero errors
- [ ] `just reg-decisions` and `just reg-briefs` and `just reg-debriefs` still produce the same output
- [ ] `bun scripts/reg.ts list briefs` shows same data as old `bun scripts/reg-list.ts briefs`
- [ ] `bun scripts/reg.ts sync` updates indexes without errors
- [ ] Archived scripts are not callable from justfile or any documented workflow
- [ ] Edge case: empty registry produces `[]` not a crash

## Technical Notes

- The registry JSONL format is simple: one JSON object per line with a `file` field. The new `reg.ts` can be a thin wrapper that reads the JSONL and formats it for terminal output.
- The `barnacle-scan.ts` script is well-intentioned but is a solution to a problem caused by the registry system's own complexity. Simplify the system, and the barnacle scan becomes unnecessary.
- Keep `REGISTRY.jsonl` and `INDEX.jsonl` files as-is — this is about the tooling, not the data format.

---

## Done

When all `[ ]` items are checked and verified.
