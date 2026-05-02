# Debrief: Dashboard Foundation — 2026-05-02

## Summary
Built a full TradingAgents web dashboard — Bun/Hono backend, HTMX frontend, SSE streaming, SQLite persistence, Datatype font integration. 11 commits to main on pjsvis/TradingAgents.

## Architecture

```
Browser ← HTMX/SSE ← Bun/Hono ← Python subprocess ← TradingAgents
                              ↓
                        SQLite (WAL)
```

**Stack:** Bun 1.3, Hono 4, HTMX 2.0, SQLite, `marked`, Datatype variable font
**Frontend:** JSX SSR (no SPA, no build step), HTMX-driven tab swapping
**Backend:** Python subprocess bridge to TradingAgents graph, SSE event streaming

## What Worked Well

### Bun/Hono JSX SSR
- `.tsx` files with `/** @jsxImportSource hono/jsx */` pragma
- `c.html(<Layout><View /></Layout>)` — type-safe, zero templating
- `pageOrPartial()` helper — detects `HX-Request` header to return full page or partial
- Hot reload via Bun dev server (after killing zombie processes)

### HTMX Tab Navigation
- `hx-get="/path" hx-target="#content" hx-push-url="true"` — clean tab swapping
- `hx-swap="none"` + JS fetch — when API returns JSON, don't let HTMX auto-swap raw JSON
- Direct `fetch()` is simpler than fighting HTMX for JSON endpoints

### SSE Streaming
- `streamSSE()` from hono/streaming works cleanly
- Python subprocess → JSON lines → SSE events pipeline is reliable
- `PYTHONUNBUFFERED=1` is mandatory for real-time streaming
- `idleTimeout: 240` (max 255) for long-running analyses

### Datatype Font
- Variable font (82KB) has GSUB with `calt` + `liga` — all three chart types work
- `font-feature-settings: 'calt' 1, 'liga' 1` is mandatory
- Three types: `{l:values}` sparkline, `{b:values}` bar chart, `{p:value}` pie chart
- Row-level coloring via parent class + `color: inherit` on children — clean cascade

### SQLite + DatabaseFactory
- WAL mode singleton works correctly
- Schema auto-loaded on server startup
- Soft-delete pattern (status field) works well for positions

## What Broke (and How We Fixed It)

### 1. PRs created on wrong repo
**Problem:** `gh pr create` defaulted to TauricResearch/TradingAgents (upstream) instead of pjsvis/TradingAgents (fork)
**Fix:** Always use `--repo pjsvis/TradingAgents` explicitly

### 2. .gitignore `lib/` pattern blocked `server/lib/`
**Problem:** Python .gitignore has `lib/` which matches `server/lib/` recursively
**Fix:** Add `!server/lib/` negation pattern

### 3. Bun SQLite pragma returns `{timeout: N}` not `{busy_timeout: N}`
**Problem:** Test expected `{busy_timeout: 5000}` but Bun returns `{timeout: 5000}`
**Fix:** Destructure the correct key name

### 4. findProjectRoot() path resolution off by one level
**Problem:** `dirname(import.meta.dir)` in `server/routes/analysis.ts` goes from `server/routes/` to `server/`, then `../TradingAgents` gives wrong path
**Fix:** Go up 2 levels: `dirname(dirname(import.meta.dir))`

### 5. Static font had no GSUB table — no chart ligatures
**Problem:** Fontsource `latin-400-normal.woff2` (51KB) has no GSUB — shows raw text `{l:30,70,50}`
**Fix:** Clone github.com/franktisellano/datatype, use `fonts/variable/Datatype[wdth,wght].woff2` (82KB)

### 6. Pie charts rendered as `{p:NaN}`
**Problem:** SQLite returns confidence as string `"0.85"`, `Math.round("0.85" * 100)` = `NaN`
**Fix:** `parseFloat(s.confidence)` before arithmetic

### 7. HTMX `hx-swap="innerHTML"` injected raw JSON into DOM
**Problem:** `/api/signals` returns JSON, HTMX swaps it directly into tbody → page shows raw JSON
**Fix:** `hx-swap="none"` + direct `fetch()` in JS — completely bypass HTMX for JSON endpoints

### 8. HTMX chokes on escaped quotes in inline scripts
**Problem:** `font-feature-settings:'calt' 1` with escaped quotes inside `<script>` caused `insertBefore` error
**Fix:** Remove inline styles from JS-generated HTML; use CSS classes instead

### 9. Bun static file server returned 0-byte woff2
**Problem:** `Content-Length: 0` for Datatype.woff2 (later discovered HEAD request quirk, file served correctly on GET)
**Lesson:** Don't trust `curl -I` for body size; test with actual GET

### 10. Server zombie processes on port 3000
**Problem:** `kill` doesn't always work; multiple bun processes accumulate
**Fix:** `pkill -9 -f bun` before restart

### 11. Duplicate headers in layout + partials
**Problem:** Every partial had `<h2>` that duplicated the tab label
**Fix:** Remove `<h2>` from all partials — active tab provides context

### 12. Row coloring didn't cascade
**Problem:** Signal class on child spans, not parent div — siblings don't inherit from siblings
**Fix:** Put class on parent `<div class="timeline-row status-buy">`, children use `color: inherit`

## Process Failures

1. **No debriefs until now** — lost context between sessions
2. **Self-approval loop** — created new td sessions to approve own work
3. **Task state drift** — implemented tasks still showing as OPEN
4. **Wrong repo for PRs** — first two PRs went to upstream, had to close and recreate

## File Structure

```
server/
├── index.tsx              ← Hono entry, JSX SSR, route wiring
├── lib/
│   ├── db.ts              ← DatabaseFactory (WAL, singleton)
│   ├── markdown.ts        ← marked renderer + analysis report formatter
│   └── schema.sql         ← 5-table schema (positions, trades, signals, watchlist, analyses)
├── routes/
│   ├── portfolio.ts       ← Position CRUD API
│   ├── analysis.ts        ← SSE /analyze (spawn Python, stream events, auto-save signals)
│   ├── signals.ts         ← Signal history API
│   ├── analyses.ts        ← Past analyses listing + rendered reports
│   └── prices.ts          ← Price fetcher stub
├── views/
│   ├── layout.tsx         ← Shell with tab nav
│   ├── portfolio.tsx      ← Positions table + add form
│   ├── analysis.tsx       ← Analysis form, SSE progress, position context banner
│   ├── signals.tsx        ← Signal table + Datatype timeline
│   ├── history.tsx        ← Past analyses list → rendered markdown
│   ├── datatype-test.tsx  ← Font test page (all 3 chart types + axes)
│   └── datatype.tsx       ← JSX helper (unused — inline JS is simpler)
└── static/
    ├── style.css          ← Dashboard styles + Datatype classes
    └── fonts/
        └── Datatype.woff2 ← Variable font (82KB, GSUB with calt+liga)

scripts/
└── analyze_stream.py      ← TradingAgents wrapper, JSON-line output, position context injection
```

## What's Not Done

- Portfolio table doesn't show current price or P&L
- Analysis page doesn't render markdown (just shows raw events)
- History page shows list but no markdown rendering verification
- No authentication or access control
- No error boundary for Python subprocess failures
- Datatype JSX helper component (`datatype.tsx`) was created but never used — inline JS is simpler for now

## Commands Reference

```bash
# Start server
cd /Users/petersmith/Dev/GitHub/TradingAgents
bun run server/index.tsx

# Kill all server processes
pkill -9 -f bun

# Seed test data
curl -s -X POST http://localhost:3000/api/signals \
  -H "Content-Type: application/json" \
  -d '{"ticker":"TKA.DE","date":"2026-05-02","signal":"Overweight","confidence":0.85,"reasoning":"Test"}'

# Run analysis (SSE)
curl -s -N -X POST http://localhost:3000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"ticker":"TKA.DE","analysts":"market","debates":1}'
```
