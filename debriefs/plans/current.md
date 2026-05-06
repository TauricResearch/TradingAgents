# Current Work Plan

**Last updated:** 2026-05-06 (mid-session pause)
**State:** All checks green. tsc ✓ lint ✓ PR #5 closed as redundant.

---

## Where We Are

### Epic td-0a1897 DONE ✓ — Route HTML Builders → JSX Components (8 routes)
- workflow → `workflow-data.ts` + `workflow-kanban.tsx` (390 → 45 lines)
- exits → `exits-data.ts` + `exit-list.tsx` (120 → 30 lines)
- signals → `signals-data.ts` + `signals-view.tsx` (460 → 70 lines)
- portfolio-intelligence → `portfolio-intel-data.ts` + `portfolio-intel.tsx` (520 → 70 lines)
- governance → `governance-data.ts` + `governance-view.tsx` (227 → 85 lines)
- prospects → `prospects-data.ts` + `prospects-view.tsx` (226 → 85 lines)
- feedback → `feedback-data.ts` + `feedback-view.tsx` (411 → 60 lines)
- benchmark → `benchmark-data.ts` + `benchmark-view.tsx` (275 → 55 lines)

### PR #5 forward-port DONE ✓ (commit 61c6e33)
- Aborted the 3-way merge; cherry-picked/rewrote all features instead
- Accounts table, allocation bar, spread bets, cash breakdown, manual balance
- `portfolio-balance.ts` route, schema migrations, seed data, `scripts/py/get_price.py`
- All `get_price.py` references unified to `scripts/py/get_price.py`
- PR #5 set to draft → closed as redundant

### Previous session fixes also done:
- Static assets 404 fixed — `serveStatic` with absolute path + `rewriteRequestPath`
- `/api/analyses/list/html` 404 fixed — DB router mount order before FS router
- Exits platform badge contrast fixed
- `:root` hex palette → oklch with original hex in trailing comments
- Language preference directive added to `AGENTS.md`
- `tsconfig.json` + `tsconfig.server.json` fixed — `"types": ["bun"]`
- Last 2 Biome `!` assertion warnings cleaned
- New tool: `scripts/color-tools/`

---

## Residual HTML String Builders (not yet JSX)

**NONE** — all route HTML string builders converted to JSX components.

No inline JS scripts remain in views. All runtime JS is external `<script src="...">`.

Completed extractions:
- `portfolio.ts` → `portfolio-data.ts` + `portfolio-summary.tsx` (commit 0210257)
- `analyses-db.ts` → `analysis-data.ts` + `analysis-report.tsx` (commit 5de84b0)

---

## Priority Order

### 1. Next Up: `td-56fd1b` Hygiene (remaining)

- `td-200cbd` — split `portfolio.ts` into `portfolio/` sub-router (309 lines)
  - Extract `computePortfolioSummary` + types → `server/lib/portfolio-data.ts`
  - Convert `buildPortfolioHtml` → `server/views/portfolio-summary.tsx` JSX component
  - Keep thin route in `server/routes/portfolio.ts`
- `td-18e84e` — price freshness badge per ticker in holdings
- `td-02ccec` — portfolio-intelligence was cleaned in this epic, but `portfolio.ts` still large

### 2. After hygiene

- `td-200cbd` depends on `td-0a1897` pattern — follow the same data-first, view-second approach.

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

---

## Reference

- Latest debrief: `debriefs/debrief-epic-route-html-to-jsx-2026-05-06.md`
- All TDs: `td list`
- Architecture: `ARCHITECTURE.md`
- Code rules: `AGENTS.md` → Working Principles + Language Preference sections
