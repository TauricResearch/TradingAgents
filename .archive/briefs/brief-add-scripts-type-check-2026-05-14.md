# Brief: Add Scripts Type-Check Gate

**Date:** 2026-05-14
**Status:** Open

---

## Task: Add a CI gate for the scripts tier TypeScript config

**Objective:** The `tsconfig.scripts.json` config runs with `strict: false`, `noImplicitAny: false`, `strictNullChecks: false` — effectively disabling TypeScript for all 44 scripts. The playbook justifies this as "the right rigor for the right tier", but without any CI gate, scripts silently accumulate type errors until even basic refactoring becomes blind.

## What

- [ ] Add `just check-scripts` that runs `tsc --project tsconfig.scripts.json --noEmit` — even with relaxed settings, this catches: missing imports, wrong function arity, nonexistent module references, type mismatches in the code that IS annotated
- [ ] Add `just check-all` that runs both `just check` (server) and `just check-scripts` (scripts) sequentially
- [ ] Update `.github/workflows/` or CI config to run `just check-all` instead of `just check` (if CI exists)
- [ ] Fix any existing type errors in `scripts/` that `tsc --project tsconfig.scripts.json --noEmit` reveals — they will exist because the config has never been run
- [ ] Update the `tsconfig-tiered-playbook.md` to document the new gate and the expected strictness progression from lab → scripts → src

## How to Verify

- [ ] `just check-all` exits 0 on the current codebase (after fixing any revealed errors)
- [ ] `just check-scripts` catches a deliberate error (add a wrong import to a script, confirm it fails)
- [ ] `just check` (server-only) still passes independently
- [ ] No new type errors introduced in scripts going forward
- [ ] Edge case: `scripts/lab/` files are excluded from this check (they're Tier 0)

## Technical Notes

- The current `just check` command does NOT run `tsconfig.scripts.json` — it runs `tsconfig.server.json` via `tsc --project tsconfig.server.json --noEmit`. Adding `just check-scripts` is additive, not changing the existing gate.
- Expected initial errors: missing `@types/*` packages, implicit `any` in unannotated function parameters, wrong module resolution for `.js` files. Most can be fixed with minimal type annotations.
- The scripts tier intentionally has looser settings — this isn't about making scripts as strict as server code. It's about catching the class of errors that even loose TypeScript catches (import typos, wrong argument counts, nonexistent properties).
- Use `skipLibCheck: true` (already set) to keep checking fast — no need to type-check dependencies.

---

## Done

When all `[ ]` items are checked and verified.
