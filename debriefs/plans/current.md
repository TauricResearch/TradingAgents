# Current Work Plan

**Last updated:** 2026-05-06 (session complete, on main)
**State:** PR #7 merged. All HTML string builders eliminated. `just check` green.

---

## Where We Are

### Epic td-0a1897 DONE ✓ — Route HTML Builders → JSX Components (10 routes)
- workflow → `workflow-data.ts` + `workflow-kanban.tsx`
- exits → `exits-data.ts` + `exit-list.tsx`
- signals → `signals-data.ts` + `signals-view.tsx`
- portfolio-intelligence → `portfolio-intel-data.ts` + `portfolio-intel.tsx`
- governance → `governance-data.ts` + `governance-view.tsx`
- prospects → `prospects-data.ts` + `prospects-view.tsx`
- feedback → `feedback-data.ts` + `feedback-view.tsx`
- benchmark → `benchmark-data.ts` + `benchmark-view.tsx`
- portfolio → `portfolio-data.ts` + `portfolio-summary.tsx`
- analyses-db → `analysis-data.ts` + `analysis-report.tsx`

### PR #5 Forward-Port DONE ✓ (merged via PR #7)
- Accounts table, allocation bar, spread bets, cash breakdown, manual balance
- `portfolio-balance.ts` route, schema migrations, seed data
- `scripts/py/get_price.py`, all references unified

### Infrastructure DONE ✓
- Static assets 404 fixed
- Analyses route 404 fixed
- CSS badge contrast fixed
- `:root` hex → oklch palette
- `tsconfig` bun types fixed
- All DB migrations in place

---

## Zero Residual HTML String Builders

All route HTML string concatenation has been eliminated. All client-side JS is external.

---

## Priority Order

### 1. Next: `td-56fd1b` Hygiene (remaining)

- `td-18e84e` — price freshness badge per ticker in holdings
- `td-02ccec` — clean up `portfolio-intel-data.ts` interfaces (16-field `PortfolioIntel` is too large)
- Types consolidation: inline route interfaces → `server/lib/types.ts`

### 2. After hygiene

- `td-9dbbac` — server tests: route health checks, positions query, hledger output parsing
- Seed script split: `scripts/seed/` directory, one file per domain
- Migration tooling: extract ad-hoc ALTER TABLE blocks from `server/index.tsx`

---

## Mandatory Before/After

**Every session starts:**
```bash
just check          # tsc + lint
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

## What to Avoid (Known Failure Modes)

| Pattern | Why it breaks | Fix |
|---------|--------------|-----|
| Copy `.ts` scripts to `.js` for serving | Biome lints `.js` as JS; TS syntax causes parse errors | Keep scripts inline in views (typed, linted, colocated) |
| Modify `biome.json` without running `just lint` immediately | Invalid keys cause total biome failure before any linting | Always validate after config changes |
| Template literal inside template literal | Backtick-quoted strings inside template literals are syntax errors | Use `String.fromCharCode(34)` for embedded quotes, or restructure |
| Forward-fix on a broken state | 45 min wasted vs 5 min revert | Revert first |
| Run `git checkout <old-commit> -- .` after refactor commits | Reverts committed refactors | Never run checkout-to-old-commit after making new commits |
| `serveStatic` with relative path + no `rewriteRequestPath` | Double-counts `/static` prefix → 404 | Absolute path + `rewriteRequestPath: (p) => p.replace(/^\/static/, "")` |
| Mount parameterized router before exact-match router | Greedy `/:ticker/:date` swallows `/list/html` | Exact routes first, parameterized routes last |
| Duplicate CSS class definitions | Later definition silently overrides earlier | Search before defining; use specific selectors (`.exit-card .platform-tag`) |
| `tsconfig.json` pointing to non-existent `src/` | TS18003 "No inputs were found" | Match `include` to actual source directory |
| Missing `"types": ["bun"]` in tsconfig | `import.meta.dir` and `bun:sqlite` unknown to tsc | Add to both `tsconfig.json` and `tsconfig.server.json` |
| **Route file with JSX retaining `.ts` extension** | Biome parse errors: "expected `>` but instead found `data`" | Rename to `.tsx` before running `just check` |
| **React-style `style={{...}}` in Hono JSX** | Hono JSX expects `style` as string, not object | Use `style="background:#fff3cd"` (CSS string) |
| **Extracting JSX before data layer** | Half-extracted state, can't test components | Always extract `lib/{route}-data.ts` first |
| **`colspan` instead of `colSpan`** | JSX attribute case sensitivity | Use camelCase: `colSpan`, `fontFeatureSettings` |
| **Forward-porting a PR written against old architecture** | Resolving string-concat vs JSX conflicts is impossible | Abort merge, cherry-pick ideas, rewrite into new architecture |
| **Script path updates done piecemeal** | Runtime "file not found" errors only in production | Update ALL references in a single commit |

---

## Reference

- Latest debrief: `debriefs/debrief-session-2026-05-06-pr5-merge.md`
- All TDs: `td list`
- Architecture: `ARCHITECTURE.md`
- Code rules: `AGENTS.md` → Working Principles + Language Preference sections
