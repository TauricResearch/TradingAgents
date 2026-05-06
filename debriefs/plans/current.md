# Current Work Plan

**Last updated:** 2026-05-06 (session complete, on feat/price-freshness)
**State:** 33 stale TDs closed. 5 valid TDs remain open. Branch clean, checks green.

---

## Completed This Session

### Epic td-0a1897 DONE ✓ — Route HTML Builders → JSX Components (10 routes)
All route HTML string concatenation eliminated. All client-side JS external.

| Route | Data Layer | View Component |
|-------|-----------|----------------|
| workflow | `workflow-data.ts` | `workflow-kanban.tsx` |
| exits | `exits-data.ts` | `exit-list.tsx` |
| signals | `signals-data.ts` | `signals-view.tsx` |
| portfolio-intelligence | `portfolio-intel-data.ts` | `portfolio-intel.tsx` |
| governance | `governance-data.ts` | `governance-view.tsx` |
| prospects | `prospects-data.ts` | `prospects-view.tsx` |
| feedback | `feedback-data.ts` | `feedback-view.tsx` |
| benchmark | `benchmark-data.ts` | `benchmark-view.tsx` |
| portfolio | `portfolio-data.ts` | `portfolio-summary.tsx` |
| analyses-db | `analysis-data.ts` | `analysis-report.tsx` |

### PR #5 Forward-Port DONE ✓ (merged via PR #7)
Accounts, allocation bar, spread bets, cash breakdown, manual balance. All in JSX architecture.

### Infrastructure DONE ✓
Static assets 404, analyses route 404, CSS badge contrast, oklch palette, tsconfig bun types, DB migrations.

---

## TD Status (cleaned)

**CLOSED this session (33 items):** All completed epics, script refactors, HTML builder conversions, HTML partial routes, and miscellaneous done tasks. See `td list --closed` for full history.

**REMAINING OPEN (5 items):**

| ID | Priority | Title | Status | Notes |
|----|----------|-------|--------|-------|
| `td-984925` | P1 | Move inline route interfaces into `server/lib/types.ts` | `in_review` | `types.ts` exists but many interfaces still inline in routes |
| `td-56fd1b` | P1 | Codebase hygiene epic | `open` | Parent of remaining cleanup; should be broken into smaller tasks |
| `td-9dbbac` | P2 | Server tests (route health, positions query, hledger parsing) | `in_review` | No automated TS route tests exist yet |
| `td-18e84e` | P2 | Price freshness badge per ticker | `open` | **Next up — branch `feat/price-freshness` created for this** |
| `td-02ccec` | P2 | Clean up `PortfolioIntel` interface (16 fields too large) | `open` | Split into smaller view-specific types |

---

## Current Branch

`feat/price-freshness` — created from `main`, pushed to origin.
Intended for `td-18e84e`: add a `last_updated` timestamp badge per ticker in the holdings/portfolio views.

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
| Route `.ts` with JSX | Rename to `.tsx`, update imports in `index.tsx` |
| React-style `style={{...}}` | Use `style="background:#fff3cd"` (CSS string) |
| Extracting JSX before data layer | Always extract `lib/{route}-data.ts` first |
| `colspan` instead of `colSpan` | Use camelCase: `colSpan`, `fontFeatureSettings` |
| Forward-fix on broken state | Revert to last known-good, then diagnose |
| Forward-porting PR written against old architecture | Abort merge >15 conflicts, cherry-pick ideas, rewrite |
| Script path updates piecemeal | Update ALL references in single commit |
| `tsconfig.json` missing `"types": ["bun"]` | Required in BOTH `tsconfig.json` and `tsconfig.server.json` |
| `serveStatic` without `rewriteRequestPath` | Use `rewriteRequestPath: (p) => p.replace(/^\/static/, "")` |

---

## Reference

- Latest debrief: `debriefs/debrief-session-2026-05-06-pr5-merge.md`
- Previous epic debrief: `debriefs/debrief-epic-route-html-to-jsx-2026-05-06.md`
- Architecture: `ARCHITECTURE.md`
- HTMX patterns: `playbooks/htmx-playbook.md`
- TS/Hono rules: `playbooks/typescript-hono-playbook.md`
- Code rules: `AGENTS.md`
