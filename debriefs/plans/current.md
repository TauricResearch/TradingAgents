# Current Work Plan

**Last updated:** 2026-05-08 (session: ses_f5f225, branch: feat/price-freshness)
**State:** All previous hygiene + price-freshness TDs closed. Docs cleanup epic in progress.

---

## Completed (Previous Sessions)

### Epic td-0a1897 DONE ✓ — Route HTML Builders → JSX Components (10 routes)
All route HTML string concatenation eliminated. All client-side JS external.

### PR #5 Forward-Port DONE ✓ (merged via PR #7)
Accounts, allocation bar, spread bets, cash breakdown, manual balance. All in JSX architecture.

### Epic td-56fd1b DONE ✓ — Codebase Hygiene (PR #8, 8 stories)
- td-1cb416: settings.ts + settings.json centralized config ✓
- td-984925: types.ts — inline interfaces consolidated ✓
- td-e8ee98: view scripts → typed .ts modules ✓
- td-200cbd: portfolio.ts split into sub-router ✓
- td-02ccec: PortfolioIntel interface cleaned up ✓
- td-9dbbac: server tests (route health, positions, hledger) ✓
- td-b86d5a: JSX view refactor — inline Script() eliminated ✓
- td-c79726: error response standardization ✓

### td-18e84e DONE ✓ — Price Freshness Badge
Timestamp badge per ticker in holdings/portfolio views.

---

## Current TD Status

**OPEN (this session):**

| ID | Priority | Title | Status |
|----|----------|-------|--------|
| `td-2391f4` | P1 | DOCS-CLEANUP epic (path drift, TA_DASHBOARD_PORT, hygiene decompose) | `open` |
| `td-43957e` | P1 | DOCS-CLEANUP-S01: Fix documentation path drift | `in_progress` |
| `td-db480c` | P1 | DOCS-CLEANUP-S02: Wire TA_DASHBOARD_PORT | `in_progress` |
| `td-4e2ae8` | P1 | DOCS-CLEANUP-S03: Decompose td-56fd1b (found already closed) | `in_progress` |

**OPEN from other sessions (not blocking):**

| ID | Priority | Title | Status |
|----|----------|-------|--------|
| `td-d19b7c` | P2 | Unified Trading CLI | `in_progress` |
| `td-6db19f` | P2 | UNIFIED-CLI-001-S05: Existing Script Wrappers | `in_progress` |
| `td-bcf920` | P2 | UNIFIED-CLI-001-S06: Config Management | `in_progress` |
| `td-52914f` | P2 | Fix 7 pre-existing bugs from CodeRabbit review | `in_progress` |
| `td-880766` | P2 | Fix TradingAgents Debate Mechanism | `open` |
| `td-b6bbe8` | P2 | DEBATE-001-S04: Debate quality metrics | `open` |

**AWAITING REVIEW:** 11 CLI/citty tasks from ses_1b7e1c.

---

## Current Branch

`feat/price-freshness` — accumulating docs cleanup commits. Price freshness work (td-18e84e) already completed on this branch.

---

## Mandatory Before/After

**Every session starts:**
```bash
td usage --new-session    # new identity
just check                 # tsc + lint — must be green
```

**Every TD starts:**
```bash
just check                 # clean before touching
# ... make change ...
just check                 # must pass before commit
git commit -m "type(scope): what"
```

**If checks fail:** revert immediately, diagnose second. Never pile fixes on a broken state.

---

## What to Avoid (Updated Failure Modes)

| Pattern | Fix |
|---------|-----|
| Route `.ts` with JSX | Rename to `.tsx`, update imports in `src/server/index.tsx` |
| React-style `style={{...}}` | Use `style="background:#fff3cd"` (CSS string) |
| Extracting JSX before data layer | Always extract `lib/{route}-data.ts` first |
| `colspan` instead of `colSpan` | Use camelCase: `colSpan`, `fontFeatureSettings` |
| Forward-fix on broken state | Revert to last known-good, then diagnose |
| Forward-porting PR written against old architecture | Abort merge >15 conflicts, cherry-pick ideas, rewrite |
| Script path updates piecemeal | Update ALL references in single commit |
| `tsconfig.json` missing `"types": ["bun"]` | Required in BOTH `tsconfig.json` and `tsconfig.server.json` |
| `serveStatic` without `rewriteRequestPath` | Use `rewriteRequestPath: (p) => p.replace(/^\/static/, "")` |
| Documentation paths stale after restructure | All `server/` → `src/server/`, `cli/` → `src/cli/` |

---

## Reference

- Latest debrief: `debriefs/debrief-session-2026-05-06-pr5-merge.md`
- Architecture: `ARCHITECTURE.md`
- HTMX patterns: `playbooks/htmx-playbook.md`
- TS/Hono rules: `playbooks/typescript-hono-playbook.md`
- Code rules: `AGENTS.md`
