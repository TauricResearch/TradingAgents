# Debrief: Workflow, Hardening & Polish

**Date:** 2026-05-03
**Duration:** ~3 hours
**Goal:** Harden the workflow Kanban, fix broken views, add exit process descriptions, seed realistic simulation data, update about page.

---

## What Was Planned

1. Wire `/api/prices` into portfolio P&L columns
2. Per-platform governance rules
3. Prospects view platform filter
4. Seed script for hLedger with real accounts
5. Workflow Kanban: exit column → entry process (Approved), exit strategy (Pending Exit)
6. Fix broken views (workflow, exits, history, holdings, prospects)
7. Update About page
8. DataType font integration

---

## What Was Achieved

### Workflow Kanban (3-column)
Rebuilt `/workflow` from scratch. 3 columns:
- **◇ Approved** — open positions without exit plan. Cards show entry process: AI signal → position size → entry price → define exit plan (step 4 highlighted red).
- **◆ Holdings** — clean positions with exit plan, no urgency. Entry + stop only, no badges.
- **⚑ Pending Exit** — urgency-triggered positions (stop within 15%, targets hit, or time stop < 30d). Cards show exit strategy table: stop price + distance %, all targets with hit/pending state, time stop row. Urgency badges below the table.

Live prices fetched in the route (4 at a time, 8s timeout, 60s cache). `distanceToStopPct` computed correctly per position.

### Seed Data (scripts/seed_database.py)
Multi-table seeder with `--flags`: `--positions`, `--signals`, `--watchlist`, `--analyses`, `--exit-plans`, `--post-mortems`, `--all`.

Seeded: 14 positions (3 platforms: degiero, ibkr, test), 37 signals, 12 prospects, 4 analyses, 11 exit plan YAMLs, 4 post-mortems. Justfile recipes: `just seed-db`, `just seed-db-positions`, etc.

### Broken View Fixes
- **Exits route**: 11 parallel subprocesses hanging. Fixed: 60s per-ticker price cache, 30s full response cache, batched parallelism (4 at a time), 8s timeout per subprocess.
- **Flat YAML vs nested object**: `invalidation_price` (flat YAML) vs `invalidation.price` (computed). Normalization added to `positions.ts` and `exits.tsx` view.
- **HTMX `insertBefore` error**: `workflow.tsx` — regex `/\r?\n/` and `indexOf('\n')` corrupted inside `dangerouslySetInnerHTML` by Hono's JSX compiler. Fixed by removing the split logic (using `substring(0,80)` instead).
- **HTML injection**: `workflow.tsx` and `exits.tsx` — `thesis` and `lesson` fields embedded without escaping. Fixed with `_esc()` helper.
- **`_e` not a function**: `exits.tsx` — helper defined inside `for` loop but used before definition. Moved to top.
- **`onclick` quote escaping**: All 5 views (`workflow`, `history`, `holdings`, `prospects`, `exits`) had `onclick` with JS variable interpolation (`onclick="FUNC('' + ticker + '')"`). Replaced all with `data-action` + `data-ticker` + event delegation pattern.
- **`if` → `} else if` bug**: During 4th rewrite of `workflow.tsx`, the opening `if` was eaten by a replacement. Added back.

**Key fix**: The `dangerouslySetInnerHTML` quote-encoding problem. Hono JSX encodes both `'` → `&#39;` and `"` → `&quot;` inside `<script>{...}</script>` JSX blocks. This breaks any JS string containing quotes. **Solution**: Use `dangerouslySetInnerHTML={{ __html: functionName() }}` where `functionName` is a plain TypeScript function returning the script as a string. This bypasses Hono's JSX HTML-encoding pipeline entirely.

### About Page
Rewritten with current state: all 11 tabs working, 3 platforms documented, implementation notes, data layers table, updated commands.

### DataType Font Brief
Written `briefs/datatype-sparklines.md` — scoped proposal to wire existing `DatatypeChart` component into signals, portfolio, governance, and exits views. Agreement: dashboard is a glance app, no interaction needed, sparklines only.

---

## Key Decisions

| Decision | Rationale |
|---|---|
| 3-column Kanban (no exited) | Exited positions belong in Feedback tab as post-mortems, not in active pipeline |
| Exit strategy table in Pending Exit cards | Shows all targets at a glance, state (hit/pending), stop distance — better than badges alone |
| Live prices in workflow route | Needed for `distanceToStopPct` computation; 4-at-a-time batch keeps it fast |
| `dangerouslySetInnerHTML` + function pattern | Only reliable way to deliver inline JS without Hono's HTML encoding corrupting quotes |
| `data-action` delegation over `onclick` | Eliminates the JS string interpolation / quote escaping recursion entirely |
| Two-level response cache for exits | First load ~45s, subsequent ~0ms — user experience dominates |

---

## What's Left

- Wire portfolio P&L columns with `/api/prices`
- Per-platform governance rules (different limits per platform)
- Prospects platform filter (dropdown in view header)
- Seed script for hLedger (needs actual account credentials)
- DataType sparklines: signals view (step 1), then portfolio P&L (step 2)

---

## Session Notes

**What went wrong:** Spent too long in recursive debugging on `workflow.tsx`. Multiple overlapping edits (4 rewrites) turned a simple fix into a landmine. Lesson: if a file needs more than 2 edits, rewrite from scratch.

**What went right:** The `dangerouslySetInnerHTML` + function pattern was the right call — found it by studying `analysis.tsx` which was already working. Should have started there instead of trying to patch the broken approach.

**Aesthetic:** The 3-column workflow with entry-process/exit-strategy tables looks clean. Removing the exited column was the right call — it was noise in an active pipeline view.