---
date: 2026-05-13
updated_by: ses_208dea
tags: [debrief]
---

# Debrief: Fix multi-line import parsing in reg-enrich — 2026-05-13

## Context

Reviewing PR#13 server feedback and fixing the `stripPrefix()` bug in
`scripts/reg-enrich.ts`. The original loop broke on any non-import/export line
regardless of whether we were mid-block, leaving intermediate lines of
multi-line imports in the residual and polluting JSDoc extraction.

## Accomplishments

- **Fixed the PR#13 finding correctly:** Added `!inBlock` guard to the break
  condition and ensured all block lines are tracked in the drop set. The fix
  is in commit `1f1693b`.
- **Refactored the loop:** Instead of a patch on the existing tangled state
  machine, rewrote `stripPrefix()` as a linear 3-branch state machine. The
  fix is simpler and more maintainable than the minimal patch.
- **Found and fixed adjacent bugs:** Shebang lines weren't sliced from the
  array after removal (leaked into residual). Pragma detection used
  `startsWith("*/")` which failed on single-line pragmas
  (`/** @jsxImportSource */`). Pragma slice had an off-by-one error.
- **14-test suite:** Synthetic cases covering shebangs, multi-line braced
  imports, `@jsxImportSource` pragmas, `export type`, and real-file tests
  for `db.ts`, `governance.tsx`, `main.ts`, `index.tsx`. All pass.

## Problems

- **Patched instead of refactoring first:** The PR finding described a surgical
  fix (`!inBlock` to break condition). I applied it literally, which made the
  function worse — more state, more overlapping branches. A full refactor was
  the right call; the minimal patch was wrong.
- **Test script diverged from the real pipeline:** My test called
  `extractDocComment(residual)` on `main.ts` and failed, prompting an hour of
  investigation. The real script calls `extractCittyMeta(content)` (original,
  not residual), which works fine. Should have verified the real extraction
  path before writing tests.
- **`pos`/`lines.slice` state mismatch:** The function tracks `pos` against
  a `lines` array that can be sliced. After slicing, `pos` resets to 0 but
  `drop` was populated with original indices. This caused the off-by-one in
  the pragma handler (fixed in commit).
- **Pre-existing test failure masked investigation:** `agent-orient.ts`
  crashes on `prs.map is not a function` — unrelated to this work but wasted
  orientation time and made it harder to trust the agent setup.

## Lessons Learned

- **Refactor before you patch.** If a fix looks like it's adding conditions to
  an existing state machine, the state machine is wrong. A rewrite into a
  linear 3-branch structure (inBlock → import/export → break) is cleaner than
  patching overlapping branches.
- **Test against the real script, not a mental model.** Verify the actual
  extraction pipeline before writing tests. In this case: `main.ts` has a
  citty fallback that extracts the description from original content, not
  residual. Knowing this earlier would have avoided the `main.ts` false
  failure.
- **`pos` + array slicing is a footgun.** Tracking indices against a shrinking
  array requires extreme care. Prefer direct array indexing (no `pos`
  variable) where possible, and test edge cases when slicing.
- **The right regression test is an observable property.** "No import lines in
  residual" is the thing that was actually broken. That's the test to write
  — not testing specific implementation details.
- **Minimal patches on complex code are usually wrong.** When a reviewer says
  "just add `!inBlock`", the correct response is "let me look at the whole
  function first." One-line fixes on tangled state machines rarely fix the
  root cause.

## Open Questions

- The `agent-orient.ts` script has a pre-existing crash (`prs.map is not a
  function`). Should be fixed separately.
- Should `scripts/reg-enrich.ts` have a dedicated test file rather than the
  inline test harness used during development?

## Related

- PR: https://github.com/pjsvis/TradingAgents/pull/13
- File: `scripts/reg-enrich.ts` (stripPrefix function)
- Playbook: `playbooks/conventions-playbook.md` (updated)