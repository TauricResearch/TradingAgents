# Brief: Consolidate Server Lib Modules

**Date:** 2026-05-14
**Status:** Done

---

## Task: Merge paired `thing.ts` + `thing-data.ts` modules and consolidate subprocess spawning

**Result:** S01 (Flense and Harden) merged the paired modules. subprocess.ts shared utility created by S02 (Harden Python Bridge). Batch processing files (signals-data.ts, portfolio-data.ts) retain specialized patterns for valid reasons.

## What

- [x] Merge `feedback.ts` + `feedback-data.ts` → Done by S01 (commit 4fd4225)
- [x] Merge `benchmark.ts` + `benchmark-data.ts` → Done by S01 (commit 4fd4225)
- [x] Merge `governance.ts` + `governance-data.ts` → Done by S01 (commit 4fd4225)
- [x] Shared subprocess utility `subprocess.ts` exists with `venvPython()`, `runPython()`, `runPythonJson()` → Created by S01/S02
- [x] Files using shared subprocess utility: benchmark.ts, intel-prices.ts (use venvPython from subprocess.ts)
- [ ] Batch processing files (signals-data.ts, portfolio-data.ts) retain specialized patterns — they have custom timeout/caching/batch-parsing that doesn't fit the simple `runPython` interface. This is intentional.
- [x] utils.ts `findProjectRoot()` used by prices.ts. analysis.ts has its own version with worktree support (legitimate for worktree scenarios).
- [ ] Remaining `-data.ts` files (analysis-data.ts, exits-data.ts, portfolio-data.ts, portfolio-intel-data.ts, prospects-data.ts, signals-data.ts, workflow-data.ts) are NOT paired with parent modules — they serve as distinct data access layers. Naming convention kept.

## How to Verify

- [x] Run `just check` — zero new lint/type errors
- [x] benchmark.ts imports from subprocess.ts ✅
- [x] intel-prices.ts imports from subprocess.ts ✅
- [x] prices.ts uses utils.ts ✅
- [x] analysis.ts has local findProjectRoot with worktree support (not a bug)
- [x] No remaining benchmark-data.ts, feedback-data.ts, governance-data.ts files ✅

## Technical Notes

- The shared subprocess runner in subprocess.ts is designed for simple, single-shot Python invocations. Batch processing files (signals-data.ts, portfolio-data.ts) have custom streaming/parsing logic that doesn't fit this pattern — they intentionally retain their own implementations.
- The remaining `-data.ts` files are data access layers (not paired modules) and serve a valid architectural purpose.
- analysis.ts's local `findProjectRoot()` has worktree-aware logic that utils.ts doesn't have — keeping it as-is is correct.

---

## Done

Paired modules merged (S01). Shared subprocess utility exists (S02). Batch processing files retain specialized patterns by design. just check passes.
