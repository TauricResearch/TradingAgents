---
date: 2026-05-02
tags: [feature, ui, api, documentation, verification, phase2]
agent: pi
environment: local
---

## Debrief: Dashboard Phase 2 — LLM Summarisation, Cards, Datatype Font

## Accomplishments

- **LLM-powered analysis summarisation:** Added `POST /api/analyses/:ticker/:date/explain` endpoint that sends full analysis context (decision text + agent reports) to OpenRouter/GPT-5.4-mini. Returns structured JSON: signal, confidence, position size, entry strategy, risk management, time horizon, catalysts, risks, plain-English explanation. Responses cached as `summary_*.json` alongside log files.

- **Analysis card UI:** History tab now shows structured summary cards with Datatype pie chart (confidence), sparkline (confidence trend), labeled key points, agent verdicts table, and "Explain this analysis →" button (LLM) / "View full report →" button (raw markdown).

- **Datatype font fully integrated:** Replaced static font (no GSUB) with variable font from repo. All three chart types working: sparklines `{l:...}`, bar charts `{b:...}`, pie charts `{p:...}`. Row-level color cascade via parent class + `color: inherit`. Dedicated test page at `/test/datatype`.

- **Signals timeline:** Replaced CSS bars with Datatype sparklines + pies. Each row uniformly colored by signal type. Confidence values properly parsed from SQLite strings (`parseFloat`).

- **Error propagation:** All API errors now propagate to the UI with structured messages (error, detail, hint). Added `.error-card` CSS for visible error display. Fixed hidden errors in HTMX JSON swap issue.

- **Pipeline automation:** `scripts/summarize_analyses.py` — standalone script to generate LLM summaries for all uncached analyses. `just summarize` and `just summarize-all` recipes. Auto-summarize triggered after each analysis completes in the SSE endpoint.

- **Hono JSX SSR:** Full migration from string templates to `.tsx` components. `pageOrPartial()` helper detects `HX-Request` header for full page vs partial responses. `/** @jsxImportSource hono/jsx */` pragma required per file.

- **Research summary:** `debriefs/research-summary-2026-05-02.md` — 6 cards covering Bun/Hono JSX SSR, HTMX+SSE, Datatype font, SQLite, Python bridge, tooling decisions.

- **Analysis cards:** `debriefs/analysis-cards-2026-05-02.md` — TKA.DE and AAPL analysis summaries with signal, confidence, trend, key levels, sources.

## Problems

- **Static font had no GSUB table:** Fontsource `latin-400-normal.woff2` (51KB) showed raw text `{l:30,70,50}` instead of charts. Cloned github.com/franktisellano/datatype repo, used `fonts/variable/Datatype[wdth,wght].woff2` (82KB) which has full `calt` + `liga` ligature substitution.

- **Pie charts rendered as `{p:NaN}`:** SQLite returns confidence as string `"0.85"`, `Math.round("0.85" * 100)` = `NaN`. Fixed with `parseFloat(s.confidence)` before arithmetic.

- **HTMX injected raw JSON into DOM:** `hx-swap="innerHTML"` on `/api/signals` response swapped raw JSON directly into tbody. Fixed by switching to `hx-swap="none"` + direct `fetch()` in JS — completely bypassed HTMX for JSON endpoints.

- **Server zombie processes:** `kill` didn't fully stop bun; multiple processes accumulated on port 3000. Fix: `pkill -9 -f bun` before restart.

- **`extractKeyPoints` not defined:** Summary endpoint referenced undefined function. Was `extractActions`. Fixed by renaming response field to `keyPoints: actions`.

- **Errors hidden from UI:** Generic "Failed to load summary" message instead of actual error. Fixed by checking `response.ok`, extracting `error`/`detail` from JSON body, displaying in `.error-card`.

- **dotenv not loaded in server:** `OPENROUTER_API_KEY` not available for LLM calls. Fixed by adding `import { config } from "dotenv"; config();` to analyses route.

## Lessons Learned

- **Never hide errors:** Propagate the actual error to the UI. "Failed to load" is useless; "OPENROUTER_API_KEY not configured" tells you exactly what to fix.

- **Variable font ≠ static font:** Datatype's chart ligatures require the full GSUB table. Static fonts from CDN services strip this. Always verify with fontTools: `GSUB in f` and `calt` in features.

- **SQLite returns strings for numeric columns:** Always `parseFloat()` or `Number()` before arithmetic, even for columns defined as REAL.

- **HTMX + JSON APIs don't mix well:** Use `hx-swap="none"` and handle JSON in JS, or use a dedicated fetch. HTMX expects HTML responses.

- **Bun dev server needs clean restart:** Background processes accumulate. Always `pkill -9 -f bun` before restarting.

- **LLM summarisation should be cached:** Every analysis summary costs an API call. Cache as JSON next to the log file. Auto-generate after analysis completes, regenerate on demand.

- **Row-level color cascade:** Put the signal class on the parent `<div>`, children use `color: inherit`. Don't repeat classes on every element.

## Post-Debrief Checklist

- [x] Debrief created in `debriefs/` with proper frontmatter (date, tags, agent, environment)
- [x] Brief archived: `briefs/brief-dashboard-phase2-2026-05-02.md` remains for reference
- [x] Research summary created: `debriefs/research-summary-2026-05-02.md`
- [x] Analysis cards created: `debriefs/analysis-cards-2026-05-02.md`
- [ ] CHANGELOG.md update needed
- [ ] amalfa watcher for knowledge graph ingestion
