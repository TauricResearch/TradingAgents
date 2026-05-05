# Current Work Plan

**Last updated:** 2026-05-05 (after 5304dce)
**State:** All checks green. 5 commits this session. td-41713c DONE.

---

## Where We Are

**Completed this session:**
- `td-41713c` DONE ✓ — `analyses.ts` (598 lines) split into 4 files:
  - `analyses-common.ts` (111 lines) — 8 shared helpers
  - `analyses-db.ts` (175 lines) — DB routes + renderEventSection
  - `analyses-fs.ts` (278 lines) — filesystem routes + LLM summary
  - `analyses/index.ts` (9 lines) — thin mount point
- `AGENTS.md` updated with `debriefs/plans/current.md` pointer

**Commit history (recent):**
```
5304dce refactor(analyses): split into analyses/ sub-router
c846e8b refactor(analyses): extract analyses-common.ts — shared helpers
b915667 refactor(analyses): extract analyses-db.ts — DB routes + renderEventSection
260a04b refactor(analyses): extract analyses-fs.ts — filesystem routes + LLM summary
b4efab7 docs(debriefs): add debrief for settings + script extraction session
7d339e8 docs(AGENTS): add Working Principles + Known Failure Modes
fdcf985 feat(settings): central config module + script extraction foundation
3cf1821 feat(holdings): JSX refactor foundation — components, HTMX partial
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

### 3. After: `td-56fd1b` - Remaining Hygiene (21pt)

Children (not ordered yet - plan which to do first):
- `td-984925` - `server/lib/types.ts`: move 20+ inline route interfaces to shared module
- `td-9dbbac` - server tests: route health checks, positions query, hledger output parsing
- `td-c79726` - standardize error responses: `{ error, detail?, hint? }` everywhere
- `td-200cbd` - split `portfolio.ts` into `portfolio/` sub-router
- `td-02ccec` - clean up `portfolio-intelligence.ts`: standardize interfaces, remove duplication

---

## What to Avoid (Known Failure Modes)

| Pattern | Why it breaks | Fix |
|---------|--------------|-----|
| Copy `.ts` scripts to `.js` for serving | Biome lints `.js` as JS; TS syntax causes parse errors | Keep scripts inline in views (typed, linted, colocated) |
| Modify `biome.json` without running `just lint` immediately | Invalid keys cause total biome failure before any linting | Always validate after config changes |
| Template literal inside template literal | `` `\`calt\` `` inside `\`.map(\`...\`) \`` is a syntax error, runtime silent | Use `String.fromCharCode(34)` for embedded quotes, or restructure |
| Forward-fix on a broken state | 45 min wasted vs 5 min revert | Revert first |

---

## Reference

- Latest debrief: `debriefs/debrief-settings-and-script-extraction-2026-05-05.md`
- All TDs: `td list`
- Architecture: `ARCHITECTURE.md`
- Code rules: `AGENTS.md` → Working Principles section