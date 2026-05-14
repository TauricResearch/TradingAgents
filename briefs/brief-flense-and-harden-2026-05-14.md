# Brief: Flense and Harden Prior to Folder Reorganisation

**Date:** 2026-05-14
**Status:** Open

---

## Task: Remove barnacles, enforce existing conventions, and add drift-detection gates

**Objective:** Before any folder reorganisation, remove dead code, fix convention violations, and add automated gates so the restructured codebase doesn't immediately start accumulating new barnacles. This is the precondition for a clean re-org.

---

## What

### Phase 1 — Flense (Remove Dead & Duplicated Code)

- [ ] **Delete `src/server/lib/registry-types.ts`** — zero imports across the entire codebase. If it has content worth keeping, inline it into the one file that actually needs those types.
- [ ] **Merge `benchmark.ts` + `benchmark-data.ts`** — `benchmark-data.ts` contains a near-duplicate of `computeReturns()` from `benchmark.ts` (named `computePeriodReturns`). Consolidate into a single `benchmark.ts`. All current importers of `benchmark-data.ts` must be updated.
- [ ] **Merge `feedback.ts` + `feedback-data.ts`** — `feedback-data.ts` re-exports from `feedback.ts` AND has its own `computeCorrelations()` that doesn't reuse `computeSignalAccuracy()` from the paired file. Consolidate into a single `feedback.ts`. Verify `GET /api/feedback/with-positions` returns identical data.
- [ ] **Merge `governance.ts` + `governance-data.ts`** — Thinest pair (73-line data file). Straightforward merge into `governance.ts`. Verify `GET /api/governance` returns identical data.

### Phase 2 — Harden (Fix Violations of Existing Rules)

- [ ] **Fix import boundary violations** — 15 CLI commands import from `src/server/lib/`. The primary offender is `settings.ts` (imported by 11 CLI commands). Move `settings.ts` (and optionally `settings.json`, `types.ts`) from `src/server/lib/` to `src/lib/` (shared layer). Update all import paths in both server and CLI. The `src/README.md` boundary table says `src/cli/` can import from `src/lib/` — after this move, those imports become legal.
  - Affected commands: `alerts-check`, `alerts-create`, `alerts-delete`, `alerts-list`, `benchmark`, `buylist`, `export`, `import`, `portfolio`, `research`, `signals`, `spreadbets`, `status`, `trades`, `watchlist`
  - Also move `alerts-db.ts` and `alerts-engine.ts` if CLI commands genuinely need them, OR make the CLI commands talk to the dashboard API instead of directly importing data layer modules.
  - Move `telegram.ts` if needed, or remove the notification call from CLI commands.
- [ ] **Fix `__dirname` in `settings.ts`** — Replace with `import.meta.dir` (Bun ESM compatible). Currently line 50.
- [ ] **Fix hardcoded `localhost:3000` in `src/cli/commands/status.ts`** — Replace with the configured port from `settings.ts`.

### Phase 3 — Add Drift Detection Gates

- [ ] **Create `scripts/check-import-boundaries.ts`** — Following the pattern of `check-database-usage.ts`, read all source files and verify that imports comply with the boundary table in `src/README.md`. Specifically:
  - `src/cli/` must not import from `src/server/` or `src/server/lib/`
  - `src/server/` must not import from `src/cli/`
  - `scripts/` must not import from `src/server/` or `src/cli/`
  - Fail with specific file + import line on violation.
- [ ] **Wire `reg-enrich` into `just check`** — Add `bun scripts/reg-enrich.ts` to the check pipeline so the code registry is automatically updated from JSDoc on every check. Currently enrichment is a manual step that gets forgotten.
- [ ] **Add `check-import-boundaries` to `just check`** — After the gate is created, add it to the quality pipeline so new violations are caught at commit time.
- [ ] **Catch up the conceptual lexicon** — Add missing terms from the playbook/code audit:
  - Architectural: `compartment`, `workbench`, `registry`, `index`, `schema`, `silo`
  - Code patterns: `DatabaseFactory`, `pageOrPartial`, `hledger`, `justfile`, `reg-sync`
  - Process: `friction`, `barnacle`, `tidy-first`
  - Consolidate the 7 duplicate CTX entries (oh-040 vs factored-design, etc.) into canonical single entries
  - Fix broken `related` links (terms that reference non-existent entries)

### Phase 4 — Verify

- [ ] Run `just check` — zero errors
- [ ] Run full test suite — `just test-smoke` passes
- [ ] Start `just serve-test` — dashboard loads all 11 tabs without errors
- [ ] `GET /api/benchmark`, `GET /api/governance`, `GET /api/feedback/with-positions` return identical data to pre-flense
- [ ] `bun scripts/check-import-boundaries.ts` exits 0 with zero violations
- [ ] `jq -r '.file' code/INDEX.jsonl | sort` shows expected files (registry-types.ts removed, no unexpected changes)
- [ ] `jq -r '.file' silo-conceptual-lexicon.jsonl | grep -E 'compartment|DatabaseFactory|pageOrPartial|hledger'` returns matches for newly added terms
- [ ] Edge case: CLI commands that previously imported from `src/server/lib/settings.ts` now import from `src/lib/settings.ts` without error
- [ ] Edge case: fresh checkout + `bun install && just install && just check` passes without manual steps

## Technical Notes

- **Phase 1 and 2 can be parallelised** — the file moves and merges are independent of each other. The gate creation (Phase 3) depends on Phase 2 being complete (the boundary script will fail until the violations are fixed).
- **Risk of merging feedback.ts:** `feedback-data.ts` has 251 lines including `computeCorrelations()` which does SQL queries + live price fetching. `feedback.ts` has 184 lines of filesystem-based post-mortem logic. These are genuinely different concerns. A merge will create a ~435-line file with two distinct responsibilities. The alternative is to rename the pair to clarify the split (`feedback-postmortems.ts` + `feedback-correlations.ts`) rather than merging — evaluate which creates a cleaner structure.
- **The `check-import-boundaries.ts` gate** should be strict (exit 1 on violation, no `|| true` escape hatch). If there's a legitimate cross-boundary import, the rule in `src/README.md` should be updated, not the gate bypassed.
- **Archive the old just-playbook recipe counts** — after this brief, the justfile overhaul brief becomes easier because the codebase is clean and the boundaries are enforced.

---

## Done

When all checkboxes in Phases 1-4 are verified, the codebase is ready for folder reorganisation without dragging barnacles into the new structure.
