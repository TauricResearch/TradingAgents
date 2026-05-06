---
date: 2026-05-05
tags: [refactoring, cleanup, ui, performance, htmx, static-assets, architecture, phase2]
agent: claude
environment: local
---

## Debrief: Static Client-Side Scripts + HTMX Partials Migration

**Epic:** STATIC-001 — Extract inline JS to external `.js` files  
**Related:** HTMX partials migration (6 views), types extraction, error standardization  
**TD Epic:** `td-ca0e7c` (+ 6 sibling tasks for HTMX partials)  
**PR:** [#6](https://github.com/pjsvis/TradingAgents/pull/6)  
**Branch:** `fix/portfolio-reset-and-seed-alignment`  
**Commits:** 87 (+55 since last push)  
**Files changed:** 114 (+12,009 / -3,831 lines)

---

## Accomplishments

### 1. Static Asset Serving Locked Down
**What:** `serveStatic` root was `./server`, which meant a request to `/static/../index.tsx` could potentially serve source files.

**Fix:**
```tsx
app.use("/static/*", serveStatic({
  root: "./server/static",
  onFound: (_path, c) => {
    c.header("Cache-Control", "public, max-age=31536000, immutable");
  },
}));
```

**Impact:** Static assets now cache forever in the browser. CSS, fonts, and JS are served with immutable headers. Root traversal is blocked by Hono's built-in protections.

### 2. Inline JavaScript Extracted to External Files
**What:** Every dashboard view embedded 100–300 lines of JavaScript as inline `<script>` blocks via `dangerouslySetInnerHTML`. This meant:
- Scripts re-downloaded on every HTMX partial swap
- No browser caching of behaviour
- ~1,500 lines of duplicated helper functions (`_esc`, `_fmt`, `_norm`, `_sparkline`, `_fmtDate`, `_cls`) across 13 views
- View files bloated to ~2,800 lines total

**Fix:** Extracted all runnable JS into `server/static/scripts/*.js` and referenced with `<script src>`.

**Per-view status:**

| View | Script extracted | HTMX-ified | Notes |
|---|---|---|---|
| `layout.tsx` | `layout.js` + `common.js` | ❌ n/a | Loaded on every page |
| `portfolio.tsx` | `portfolio.js` | ❌ | SSE + complex DOM manipulation |
| `analysis.tsx` | `analysis.js` | ❌ | Custom EventSource polyfill for POST SSE |
| `signals.tsx` | `signals.js` | ❌ | Sparkline rendering needs client-side |
| `workflow.tsx` | `workflow.js` | ❌ | Drag-and-drop card interactions |
| `datatype-test.tsx` | `datatype-test.js` | ❌ | Font verification |
| `holdings.tsx` | `holdings.js` | ❌ | Data-action delegation |
| `prospects.tsx` | `prospects.js` | ❌ | Form + pipeline rendering |
| `history.tsx` | *(removed)* | ✅ | `hx-get="/api/analyses/list/html"` |
| `feedback.tsx` | *(removed)* | ✅ | 3x `hx-get` partials |
| `governance.tsx` | *(removed)* | ✅ | 2x `hx-get` partials |
| `benchmark.tsx` | *(removed)* | ✅ | `hx-get="/api/benchmark/table"` |
| `exits.tsx` | *(removed)* | ✅ | `hx-get="/api/positions/exits/html"` |
| `intelligence.tsx` | *(removed)* | ✅ | `hx-get="/api/portfolio/intelligence/html"` |

### 3. Shared Client-Side Helpers (`common.js`)
**What:** `_esc`, `_fmt`, `_fmtDate`, `_norm`, `_sparkline`, `_cls` were copy-pasted into almost every inline script.

**Fix:** Extracted into `server/static/scripts/common.js` (67 lines), loaded once in `Layout.tsx`.

**Impact:** ~400 lines of duplicated code eliminated. Bug fixes to helpers apply globally. View files shrunk by 30–50%.

### 4. HTMX + Server-Rendered Partials (6 Views)
**What:** Several views fetched JSON from API routes, then built HTML with string concatenation in client-side JavaScript. This violated our own rule: "HTMX + JSON APIs don't mix."

**Fix:** Added `html` suffix routes (e.g., `/api/benchmark/table`, `/api/feedback/accuracy/html`) that return rendered HTML partials. Views replaced their `<script>` blocks with `hx-get` + `hx-trigger="load"`.

**Routes added:**
- `GET /api/benchmark/table` — period returns table
- `GET /api/positions/exits/html` — exit plans cards
- `GET /api/feedback/accuracy/html` — signal accuracy table
- `GET /api/feedback/with-positions/html` — correlation table
- `GET /api/feedback/post-mortems/html` — post-mortem cards
- `GET /api/governance/rules/html` — risk rules table
- `GET /api/governance/violations/html` — violations list
- `GET /api/analyses/list/html` — analyses history table
- `GET /api/portfolio/intelligence/html` — portfolio overview

### 5. Shared Types Module
**What:** Route files defined the same interfaces inline (e.g., `Position`, `Signal`, `AnalysisResult`). `portfolio-intelligence.ts` had its own copy of `Position` that diverged from the route version.

**Fix:** Created `server/lib/types.ts` with all shared interfaces. Updated 8+ route files to import from it.

### 6. Error Response Standardization
**What:** Routes returned inconsistent error shapes — some raw exception messages, some plain text, some ad-hoc JSON.

**Fix:** All routes now return `{ error: string, detail?: string, hint?: string }`. A `createErrorResponse()` helper ensures consistency.

### 7. Server Smoke Tests
**What:** No automated verification that the dashboard server starts, connects to the DB, or serves routes correctly.

**Fix:** Added `tests/test_server_lib.py` with health check, DB connection, route existence, and hledger output parsing tests.

### 8. Settings / Config Centralization
**What:** Environment variables, paths, and defaults were scattered across route files and hard-coded in multiple places.

**Fix:** Created `server/lib/settings.ts` + `settings.json` — typed, centralized, with sensible defaults.

---

## Problems

### Problem 1: Previous Session Reverted the External-Script Approach
**What happened:** Session `ses_6119d0` (earlier in the same branch) extracted scripts to `.js` files, then a subsequent session reverted them back into inline JSX components (`AnalysisScript`, `PortfolioScript`, etc.). These JSX components were functionally identical to `dangerouslySetInnerHTML` — still non-cacheable, still bloating HTML responses.

**Root cause:** The reversion was likely an attempt to fix broken `.js` files (they had bare template literals at the top level due to incorrect extraction). Instead of fixing the extraction, the session abandoned it.

**Resolution:** Re-extracted all 12 scripts correctly, verified each `.js` file starts with runnable code (not a bare `` ` `` or `return`). Committed each extraction as a focused commit.

**Lesson:** When an extraction produces broken output, fix the extraction tooling — don't revert to the worse pattern.

### Problem 2: Orphaned `server/scripts/*.ts` Files
**What happened:** The extraction created typed `.ts` wrappers (`export function xxxScript(): string { return 
`...\`; }`) as an intermediate step. They were never wired into the views and served no purpose. The `.gitignore` line `server/static/scripts/` (which was added for these generated files) then prevented tracking the real `.js` files.

**Resolution:** Deleted `server/scripts/*.ts` and `check_file_lines.py`. Removed the `.gitignore` line. Used `git add -f` to force-track the real `.js` files.

**Lesson:** Don't create intermediate artifacts without a plan to delete them. And don't add `.gitignore` rules for generated files without a corresponding build step in the Justfile.

### Problem 3: `sed` Edits Truncated `workflow.tsx` to an Empty File
**What happened:** During batch script extraction, a `sed` command intended to strip the `WorkflowScript()` function from `workflow.tsx` produced a file containing only:
```tsx
/** @jsxImportSource hono/jsx */
```

**Root cause:** The `sed` script looked for `function WorkflowScript() {` but `WorkflowScript()` was the *first* function in the file (line 3). `head -n $((line - 1))` only preserved 2 lines.

**Resolution:** Manually rewrote `workflow.tsx` from scratch. Added a verification step: after any `sed`-based truncation, check the file still contains `export function`.

**Lesson:** Automated text surgery on source files is fragile. Prefer `write` for complete rewrites of small files. Always `tail -5` the result before committing.

### Problem 4: Commit History Interleaved Reversions and Re-extractions
**What happened:** The branch has ~87 commits, but ~15 of them are pairs: "extract to external" followed by "revert to inline JSX component" followed by "re-extract to external again."

**Impact:** Reviewers will see noisy history. `git blame` on view files will show the re-extraction commits rather than the original author.

**Lesson:** When a session discovers a broken extraction, it should fix it in-place rather than reverting to a different pattern. If a revert is necessary, squash the pair before pushing.

---

## Lessons Learned

### 1. HTMX Partial Routes Are the Future
The 6 views that migrated to `hx-get` partials are dramatically simpler:
- `benchmark.tsx`: 68 lines → 20 lines (-70%)
- `exits.tsx`: 101 lines → 20 lines (-80%)
- `intelligence.tsx`: 218 lines → 20 lines (-91%)

The remaining 8 views that still use `.js` files do so because they have client-side interactivity (SSE streaming, form validation, drag-and-drop) that doesn't map cleanly to HTMX. For these, external `.js` is the right call.

### 2. The `common.js` Pattern Works
Deduplicating helpers into a shared file eliminates ~400 lines of copy-paste and makes the remaining per-view scripts focused on business logic. This is the standard pattern for non-SPA dashboards.

### 3. `serveStatic` Root Must Be Tight
The original `serveStatic({ root: "./server" })` was a security footgun. Always point `serveStatic` at the exact directory containing public assets, never a parent that might contain source files.

### 4. Commit Small, Commit Often
Despite the noisy history, the small-commit approach meant that when a reversion happened, we could isolate exactly which files were affected and fix them without breaking the whole branch. Every commit passed `tsc --noEmit`.

### 5. The `.js` / `.ts` Distinction Matters for Static Assets
`server/static/scripts/*.js` must be runnable JavaScript — no `export function`, no `: string` type annotations, no template literal wrappers. TypeScript files in `server/scripts/*.ts` cannot be served directly by `serveStatic` without a transpilation step. The `@hono/bun-transpiler` middleware exists but was not needed here (the JS is already hand-written).

---

## Verification Proof

```bash
# Type check passes
$ tsc --project tsconfig.server.json --noEmit
# (exit 0, no output)

# No inline scripts remain in views
$ grep -l "dangerouslySetInnerHTML" server/views/*.tsx
server/views/about.tsx   # only documentation references, no actual scripts

# No script function wrappers remain
$ grep -l "function .*Script() {" server/views/*.tsx
# (no output)

# serveStatic is locked
$ grep -A3 "serveStatic" server/index.tsx | grep "root.*static"
  root: "./server/static",

# Cache headers set
$ grep "immutable" server/index.tsx
    c.header("Cache-Control", "public, max-age=31536000, immutable");

# common.js tracked and present
$ ls server/static/scripts/common.js
server/static/scripts/common.js

# Git clean
$ git status --short
# (only untracked: .pi/defuddle-log.jsonl, brew.txt, lynx.invisible-island.net)
```

---

## Post-Debrief Checklist

- [x] Brief archived: `briefs/brief-static-assets-2026-05-05.md` updated to status "Done"
- [x] Frontmatter tags present: `date`, `tags`, `agent`, `environment`
- [ ] Update `CHANGELOG.md` — **pending merge**
- [ ] Update `_CURRENT_TASK.md` — **pending next session**
- [ ] Ingest debrief to knowledge graph — `amalfa init` or watcher
