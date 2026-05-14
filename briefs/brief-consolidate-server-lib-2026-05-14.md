# Brief: Consolidate Server Lib Modules

**Date:** 2026-05-14
**Status:** Open

---

## Task: Merge paired `thing.ts` + `thing-data.ts` modules and consolidate subprocess spawning

**Objective:** The `src/server/lib/` directory has 32 files with an inconsistent `-data.ts` suffix convention that creates fragmentation without value — merge the three paired modules and extract the duplicated Python subprocess spawn pattern into a shared utility.

## What

- [ ] Merge `feedback.ts` (184 lines, filesystem post-mortem logic) + `feedback-data.ts` (251 lines, SQL correlations + re-exports) into a single `feedback.ts` — the split adds no value, and `feedback-data.ts` has its own `computeCorrelations()` that doesn't reuse `computeSignalAccuracy()` from its paired module
- [ ] Merge `benchmark.ts` (158 lines, yfinance fetch + period returns) + `benchmark-data.ts` (188 lines, batch price fetch + live portfolio + DUPLICATE `computePeriodReturns`) into a single `benchmark.ts` — `benchmark-data.ts` has a near-identical copy of `computeReturns()` renamed to `computePeriodReturns()`, which is a bug farm
- [ ] Merge `governance.ts` (267 lines, rules engine) + `governance-data.ts` (73 lines, orchestration) into a single `governance.ts` — this one is already thin enough that the merge is trivial
- [ ] Extract a shared `subprocess-runner.ts` or similar utility for Python subprocess spawning — currently duplicated in at least 5 places (benchmark.ts, benchmark-data.ts, feedback-data.ts, prices.ts, analysis.ts) all with the same stdout parsing, error handling, and cache logic
- [ ] Inline or expand the 9-line `utils.ts` (single function: `findProjectRoot()`) — a 9-line file with one export is a cognition tax. Either inline it at call sites or expand it to hold all truly generic utilities
- [ ] Remove the `-data.ts` suffix convention from the codebase — any remaining `-data.ts` files that aren't manually paired should be either merged into their logical parent or renamed if they genuinely serve a separate concern

## How to Verify

- [ ] Run `just check` — zero new lint/type errors
- [ ] `GET /api/benchmark` returns identical data before and after
- [ ] `GET /api/feedback/with-positions` returns identical data before and after
- [ ] `GET /api/governance` returns identical data before and after
- [ ] All Python subprocess callers use the shared utility — grep for `spawn("python3"` or `spawn(venvPython()` should return only the utility itself
- [ ] No files remain in `src/server/lib/` with the `-data.ts` suffix
- [ ] Edge case: empty positions table doesn't crash benchmark or governance endpoints

## Technical Notes

- The shared subprocess runner should be a thin wrapper: `runPython(script: string, args: string[], opts?: {timeout, cache?}): Promise<{stdout, stderr, exitCode}>`
- The existing `priceCache` in `cache.ts` is already referenced by multiple callers — the subprocess runner should accept a cache key as an option rather than embedding caching logic
- No behavioural changes beyond merging — this is pure structural refactoring
- Risk: route files that import from both `foo.ts` and `foo-data.ts` will need single imports. Grep all routes for dual-import patterns

---

## Done

When all `[ ]` items are checked and verified.
