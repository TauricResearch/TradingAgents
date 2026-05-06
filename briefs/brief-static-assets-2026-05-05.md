# Epic: Static Client-Side Scripts for Dashboard

**Date:** 2026-05-05
**Epic ID:** STATIC-001
**Status:** Done

---

## Vision

Every dashboard view that requires client-side interactivity (SSE event streams, form handling, DataType sparklines, dynamic table rendering) currently ships its JavaScript as an inline `<script>` block injected via `dangerouslySetInnerHTML`. This pattern:

- Bloats every HTML response by ~100–300 lines of non-cacheable JavaScript
- Prevents browser caching of client-side behaviour (re-downloaded on every HTMX partial swap)
- Duplicates the same helper functions (`_esc`, `_fmt`, `_fmtDate`, `_norm`, `_sparkline`, `_cls`) across 13 separate views
- Violates our own lint philosophy and makes view files unnecessarily large (~2,800 lines total)

We will extract all client-side behaviour into real `.js` files served statically by Hono via `serveStatic`, referenced with standard `<script src>` tags in the JSX layout or per-view. This aligns with Hono/Bun best practice and the HTMX + SSR architecture.

---

## Stories

### STATIC-001-S01 — Tighten static asset serving

**What:** Lock down `serveStatic` so it serves only from `server/static/`, not the entire `server/` tree. Add `Cache-Control: public, max-age=31536000, immutable` for static assets.

**Acceptance:**
- [ ] `app.use("/static/*", serveStatic({ root: "./server/static" }))` — no broader root
- [ ] Cache header set on every matched static request
- [ ] Request to `/static/style.css`, `/static/favicon.svg`, `/static/fonts/Datatype.woff2` still succeeds
- [ ] Request to `/static/../index.tsx` (path traversal) is blocked by Hono's built-in protection

**Estimate:** 0.25d

---

### STATIC-001-S02 — Common client-side helpers

**What:** Extract the six helper functions duplicated across almost every inline script into a single `server/static/scripts/common.js` file. Load it once in `Layout.tsx` so every page inherits it.

**Acceptance:**
- [ ] `server/static/scripts/common.js` created with: `Dash.esc`, `Dash.fmt`, `Dash.fmtDate`, `Dash.norm`, `Dash.sparkline`, `Dash.cls`
- [ ] `Layout.tsx` includes `<script src="/static/scripts/common.js"></script>` before page-specific scripts
- [ ] Existing inline scripts still work (backward-compatible) — helpers can be removed from them in S03–S08

**Estimate:** 0.25d

---

### STATIC-001-S03 — Extract portfolio + analysis scripts

**What:** Convert the two largest inline scripts (`portfolioScript()`, `analysisScript()`) into real `.js` files in `server/static/scripts/`. Remove the inline functions from the TSX views. Add `<script src>` references.

**Acceptance:**
- [ ] `server/static/scripts/portfolio.js` created — runnable, no TypeScript syntax
- [ ] `server/static/scripts/analysis.js` created — runnable, no TypeScript syntax
- [ ] `server/views/portfolio.tsx` no longer contains `portfolioScript()`; uses `<script src="/static/scripts/portfolio.js">`
- [ ] `server/views/analysis.tsx` no longer contains `analysisScript()`; uses `<script src="/static/scripts/analysis.js">`
- [ ] Portfolio page loads, P&L summary renders, positions table populates
- [ ] Analysis page loads, SSE events stream, form submission works

**Estimate:** 0.5d

---

### STATIC-001-S04 — Extract signals + history scripts

**What:** Same pattern for `signals.tsx` and `history.tsx`.

**Acceptance:**
- [ ] `server/static/scripts/signals.js` created and referenced
- [ ] `server/static/scripts/history.js` created and referenced
- [ ] Signals table loads with sparklines; history timeline renders
- [ ] Inline `signalsScript()` and `historyScript()` removed from views

**Estimate:** 0.5d

---

### STATIC-001-S05 — Extract feedback + workflow scripts

**What:** Same pattern for `feedback.tsx` and `workflow.tsx`.

**Acceptance:**
- [ ] `server/static/scripts/feedback.js` created and referenced
- [ ] `server/static/scripts/workflow.js` created and referenced
- [ ] Feedback accuracy panel, correlations, post-mortems load
- [ ] Workflow Kanban renders and drag/drop (if any) or card actions work
- [ ] Inline functions removed from views

**Estimate:** 0.5d

---

### STATIC-001-S06 — Extract holdings + intelligence scripts

**What:** Same pattern for `holdings.tsx` and `intelligence.tsx`.

**Acceptance:**
- [ ] `server/static/scripts/holdings.js` created and referenced
- [ ] `server/static/scripts/intelligence.js` created and referenced
- [ ] Holdings table with sparklines, freshness badges, stop badges renders
- [ ] Intelligence P&L summary and allocation charts load
- [ ] Inline functions removed from views

**Estimate:** 0.5d

---

### STATIC-001-S07 — Extract exits + prospects + governance + benchmark scripts

**What:** Same pattern for `exits.tsx`, `prospects.tsx`, `governance.tsx`, `benchmark.tsx`.

**Acceptance:**
- [ ] Four new `.js` files created and referenced
- [ ] Exit plans render with stop distances; prospects table loads
- [ ] Governance rules list loads; benchmark chart renders
- [ ] Inline functions removed from all four views

**Estimate:** 0.5d

---

### STATIC-001-S08 — Extract datatype-test + about + layout inline scripts

**What:** Convert remaining small inline scripts (`datatype-test.tsx`, `about.tsx`, and the `syncTab` inline block in `layout.tsx`).

**Acceptance:**
- [ ] `server/static/scripts/datatype-test.js` created and referenced
- [ ] `server/static/scripts/about.js` created and referenced
- [ ] `server/static/scripts/layout.js` created; `syncTab` logic moved out of `layout.tsx`
- [ ] All `dangerouslySetInnerHTML` usages for scripts are gone from the codebase
- [ ] `tsc --noEmit` passes
- [ ] `just lint` passes

**Estimate:** 0.5d

---

### STATIC-001-S09 — Cleanup orphaned artefacts

**What:** Remove the intermediate `server/scripts/*.ts` files and `server/scripts/check_file_lines.py` that were created as a stepping-stone but never wired up. Update `.gitignore` so `server/static/scripts/` is no longer ignored (these are now source-of-truth runtime files, not generated artefacts).

**Acceptance:**
- [ ] `server/scripts/` directory deleted entirely
- [ ] `.gitignore` line `server/static/scripts/` removed
- [ ] All `.js` files in `server/static/scripts/` are tracked by git
- [ ] `just check` passes (tsc + lint)

**Estimate:** 0.25d

---

## Done

| Story | Status |
|---|---|
| STATIC-001-S01 | ✅ |
| STATIC-001-S02 | ✅ |
| STATIC-001-S03 | ✅ |
| STATIC-001-S04 | ✅ |
| STATIC-001-S05 | ✅ |
| STATIC-001-S06 | ✅ |
| STATIC-001-S07 | ✅ |
| STATIC-001-S08 | ✅ |
| STATIC-001-S09 | ✅ |

## Exit Criteria

1. Zero inline `<script>` blocks via `dangerouslySetInnerHTML` remain in any `server/views/*.tsx` file.
2. All client-side behaviour is served as static `.js` files from `server/static/scripts/` via `serveStatic`.
3. `server/static/scripts/common.js` is loaded on every page and contains all shared helpers.
4. `serveStatic` root is locked to `./server/static` with immutable cache headers.
5. `just check` (tsc + lint) passes with no errors.
6. Manual smoke-test: every dashboard tab loads without console JS errors.

## Commit Discipline

**One commit per story.** Each commit must be small, focused, and reversible. If a story requires multiple files, that's fine — the commit message should name the story (e.g., `feat(scripts): extract portfolio + analysis to external JS files`).

**Never bundle unrelated changes.** If you find a bug while extracting a script, note it and fix it in a separate commit. Do not let scope creep into a script-extraction commit.

**Verify before each commit:** `tsc --noEmit` and `just lint` must pass. If they don't, fix in the same commit — do not leave broken code on the branch.

## Technical Notes

- Hono's `serveStatic` from `hono/bun` serves files as-is. The old `server/static/scripts/*.js` files contain TypeScript syntax (`export function`) and are invalid in a browser. They will be replaced with plain runnable JavaScript.
- The inline script content inside `xxxScript(): string { return \`...\`; }` is already plain JavaScript (uses `var`, no TypeScript types). Extracting it means stripping the TypeScript wrapper, not rewriting the logic.
- HTMX partial swaps (`pageOrPartial`) only swap `#content`. Since `<script>` tags in `#content` execute when swapped, per-page scripts loaded via `<script src>` inside the partial will re-execute on each swap. This is acceptable for now; if performance becomes an issue we can move page-specific scripts to load once in `Layout.tsx` and use `DOMContentLoaded` or `htmx:afterSwap` listeners.
- The `analysis.tsx` SSE event handling uses `EventSourcePolyfill` — ensure the external script still has access to this symbol (it comes from the inline script or a CDN). Check before committing.
