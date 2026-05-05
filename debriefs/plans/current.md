# Current Work Plan

**Last updated:** 2026-05-05 (end of session)
**State:** All checks green. tsc ✓ lint ✓ 15 smoke tests pass.

---

## Where We Are

**Completed this session:**
- `td-b86d5a` DONE ✓ — all 12 views refactored from `dangerouslySetInnerHTML` + template literal strings to JSX `<XxxScript />` components.
- `td-41713c` DONE ✓ — `analyses.ts` (598 lines) split into 4 files
- `td-984925` DONE ✓ — `server/lib/types.ts` with `PriceResult`, re-exports from benchmark.ts
- `td-9dbbac` DONE ✓ — `tests/test_server_lib.py` (10 smoke tests, 11 pass, 2 skip gracefully)
- `td-c79726` DONE ✓ — standardized error shapes (c.text(404) → c.json, hint on 500)
- `settings.ts` + `settings.json` — central config module
- `AGENTS.md` — Working Principles + Known Failure Modes + pointer to current.md
- `debriefs/plans/current.md` — restart orientation doc

**Commit history (recent):**
```
1c3afdc fix(errors): standardize error response shape
c104252 test(server): add test_server_lib.py — smoke tests for routes and lib
c276941 refactor(types): create server/lib/types.ts with shared interfaces
fc39811 fix(views): restore refactored workflow, exits, prospects, governance
```
391f6e6 refactor(benchmark.tsx): benchmarkScript() → BenchmarkScript JSX component
f341943 refactor(exits.tsx): exitsScript() → ExitsScript JSX component
020f1ce refactor(workflow.tsx): workflowScript() → WorkflowScript JSX component
9498c55 docs(plans): update current.md — td-41713c DONE
```

---

## Mandatory Before/After

**Every session starts:**
```bash
just check          # tsc + lint + (if configured) file-lines
```

**Every TD starts:**
```bash
just check          # must be clean before touching anything
# ... make the change ...
just check          # must pass before committing
git commit -m "type(scope): what"
```

**If checks fail:** revert immediately, diagnose second. Never pile fixes on a broken state.

---

## Priority Order

### 1. Next Up: `td-b86d5a` - JSX View Refactor (13pt, 12 children) ✅ [was: analyses split]

**Why:** 12 views have inline `XXXScript()` template literals. The goal is clean JSX components instead of HTML-in-template-literals. Start with the smallest ones to establish the pattern.

**Children (priority order by size):**

| Order | TD | File | Points | Notes |
|-------|-----|------|--------|-------|
| 1 | `td-08850c` | `workflow.tsx` | 1 | 3-line script, no state, pattern baseline |
| 2 | `td-14e078` | `exits.tsx` | 1 | simple script, no state |
| 3 | `td-4c401c` | `benchmark.tsx` | 1 | simple script |
| 4 | `td-8691e1` | `governance.tsx` | 1 | simple script |
| 5 | `td-281296` | `feedback.tsx` | 1 | small, no state |
| 6 | `td-ee5419` | `datatype-test.tsx` | 1 | small |
| 7 | `td-5c015d` | `history.tsx` | 1 | medium - has HTMX, watchlist |
| 8 | `td-2376f3` | `prospects.tsx` | 1 | medium - stages array |
| 9 | `td-bd65e0` | `signals.tsx` | 1 | medium |
| 10 | `td-c4f672` | `intelligence.tsx` | 1 | had the `font-feature-settings` bug - watch carefully |
| 11 | `td-34a955` | `portfolio.tsx` | 2 | large - had the template-in-template bug |
| 12 | `td-3dddc1` | `analysis.tsx` | 2 | large - SSE streaming |

**Pattern:** Each refactor replaces:
```tsx
function XxxScript(): string {
  return `<script>...<\/script>`;
}
// ...
<div dangerouslySetInnerHTML={{ __html: XxxScript() }} />
```
with a JSX component:
```tsx
function XxxScript() {
  return <script>{`...`}</script>;
}
// ...
<XxxScript />
```

**One TD per view, one commit per TD, checks green before next.**

---

## What's Next: `td-56fd1b` Hygiene (remaining)

- `td-200cbd` — split `portfolio.ts` into `portfolio/` sub-router (309 lines)
- `td-02ccec` — clean up `portfolio-intelligence.ts`: standardize interfaces, remove duplication (376 lines)

**Done this session:**
- `td-984925` DONE ✓ — `server/lib/types.ts` created with `PriceResult`, `BenchmarkPrice`, `PeriodReturn`
- `td-9dbbac` DONE ✓ — `tests/test_server_lib.py` (10 smoke tests, 11 pass)
- `td-c79726` DONE ✓ — standardized error shapes in analyses-fs and analysis routes

---

## What to Avoid (Known Failure Modes)

| Pattern | Why it breaks | Fix |
|---------|--------------|-----|
| Copy `.ts` scripts to `.js` for serving | Biome lints `.js` as JS; TS syntax causes parse errors | Keep scripts inline in views (typed, linted, colocated) |
| Modify `biome.json` without running `just lint` immediately | Invalid keys cause total biome failure before any linting | Always validate after config changes |
| Template literal inside template literal | Backtick-quoted strings inside template literals are syntax errors | Use `String.fromCharCode(34)` for embedded quotes, or restructure |
| Forward-fix on a broken state | 45 min wasted vs 5 min revert | Revert first |
| Run `git checkout <old-commit> -- .` after refactor commits | Reverts committed refactors | Never run checkout-to-old-commit after making new commits

---

## Reference

- Latest debrief: `debriefs/debrief-settings-and-script-extraction-2026-05-05.md`
- All TDs: `td list`
- Architecture: `ARCHITECTURE.md`
- Code rules: `AGENTS.md` → Working Principles section