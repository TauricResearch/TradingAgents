# Research Summary — Dashboard Foundation

## 🗂️ Bun/Hono JSX SSR

**What:** Server-side JSX rendering with Hono's built-in JSX runtime. No templating library, no build step.

**Highlights:**
- `/** @jsxImportSource hono/jsx */` pragma tells Bun to use Hono's JSX runtime
- `c.html(<Layout><View /></Layout>)` — type-safe composition, TypeScript catches errors at compile time
- `HX-Request` header detection: full page on direct load, partial on HTMX swap
- `.tsx` extension required — Bun doesn't parse JSX in `.ts` files
- `dangerouslySetInnerHTML` for inline scripts — no alternative in Hono JSX

**Pitfalls:**
- `hx-on::after-request` attribute breaks Bun's JSX parser — use `{...{ "hx-on::foo": "..." }}` spread syntax
- `import.meta.dir` resolves to the file's directory, not project root — need `dirname(dirname(import.meta.dir))` from routes

**Source:** [Hono JSX docs](https://hono.dev/docs/guides/jsx)

---

## 📡 HTMX + SSE Streaming

**What:** HTMX for tab navigation and partial swaps, SSE for real-time analysis progress.

**Highlights:**
- `hx-get="/path" hx-target="#content" hx-push-url="true"` — clean tab pattern with URL history
- `hx-swap="none"` prevents auto-swap — use when API returns JSON and JS handles rendering
- `streamSSE()` from hono/streaming is the right API for SSE endpoints
- Python `PYTHONUNBUFFERED=1` mandatory — otherwise stdout buffers and SSE events arrive in bursts
- `idleTimeout` max is 255 seconds in Bun — set to 240 for 4-minute analyses

**Pitfalls:**
- `hx-swap="innerHTML"` with JSON endpoints injects raw JSON into DOM — always use `none` + JS fetch for JSON APIs
- HTMX `afterOnLoad` event fires AFTER swap — too late to intercept JSON; use `beforeSwap` or `hx-swap="none"`
- Inline scripts with single quotes break HTMX parser — use CSS classes instead

**Source:** [HTMX docs](https://htmx.org/), [Hono streaming](https://hono.dev/docs/helpers/streaming)

---

## 🔤 Datatype Variable Font

**What:** OpenType variable font that renders text expressions as inline charts via GSUB ligature substitution.

**Highlights:**
- Three chart types: `{l:values}` sparkline, `{b:values}` bar chart, `{p:value}` pie chart
- Values must be 0–100 — normalize raw data before use
- `font-feature-settings: 'calt' 1, 'liga' 1` is mandatory — without it, you see raw text
- Variable font (82KB) required — static fonts from Fontsource have no GSUB table
- Row-level coloring: put signal class on parent div, children use `color: inherit`

**Pitfalls:**
- Fontsource CDN serves static fonts without GSUB — clone the repo for variable font
- SQLite returns numbers as strings — `parseFloat()` before arithmetic or you get `{p:NaN}`
- Pie chart with value 0 renders as empty circle — may be invisible on dark background
- Max 20 data points per expression

**Sources:** [Datatype site](https://franktisellano.github.io/datatype/), [GitHub repo](https://github.com/franktisellano/datatype), [Google Fonts](https://fonts.google.com/specimen/Datatype)

---

## 🗄️ SQLite + DatabaseFactory

**What:** Singleton connection factory enforcing WAL mode pragmas.

**Highlights:**
- WAL mode mandatory for concurrent read/write (dashboard + Python subprocess)
- Pragmas: `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`, `synchronous=NORMAL`, `mmap_size=0`
- `CREATE TABLE IF NOT EXISTS` on startup is safe — idempotent schema load
- Soft-delete pattern (status field) works well for positions

**Pitfalls:**
- Bun's SQLite returns `PRAGMA busy_timeout` as `{timeout: N}` not `{busy_timeout: N}`
- Database path must be absolute or relative to working directory — `./portfolio.db` works from project root

**Source:** [SQLite WAL mode docs](https://www.sqlite.org/wal.html), [playbooks/sqlite-playbook.md](./playbooks/sqlite-playbook.md)

---

## 🐍 Python Subprocess Bridge

**What:** Spawn TradingAgents Python subprocess, read JSON-line stdout, forward as SSE events.

**Highlights:**
- `spawn(python, [script, ...args], { cwd, env })` — clean process isolation
- Parse stdout line-by-line, `JSON.parse()` each line, forward as SSE event
- Auto-save: intercept `decision` event and write to signals table
- Position context injection via memory log synthetic entry

**Pitfalls:**
- Project root detection is fragile — use `TA_ROOT` env var or sibling directory pattern
- stderr from Python (warnings, tracebacks) must be captured separately — don't mix with JSON stdout
- Process exit code ≠ analysis success — check for `complete` event, not just exit code

**Source:** [TradingAgents repo](https://github.com/TauricResearch/TradingAgents), [Node child_process docs](https://nodejs.org/api/child_process.html)

---

## 🛠️ Tooling Decisions

| Tool | Choice | Rationale |
|------|--------|-----------|
| Runtime | Bun 1.3 | Native TSX, fast, built-in SQLite compatibility |
| Framework | Hono 4 | Lightweight, JSX support, streaming helpers |
| Frontend | HTMX 2.0 | No SPA, no build step, server-driven UI |
| Linter | Biome | Single binary for lint + format, fast |
| Task runner | `just` | Unified interface across Bun/Python/td |
| Task tracker | `td` | Local CLI, session-based, review workflow |
| Font | Datatype (variable) | Inline charts without JS/canvas/SVG |

---

## 🔑 Key Patterns Established

1. **Wrap, don't fork** — TradingAgents core untouched; position context injected via config/memory
2. **`pageOrPartial()` helper** — one function handles both full page and HTMX partial responses
3. **Direct `fetch()` for JSON** — bypass HTMX entirely when API returns JSON
4. **Schema auto-load on startup** — no migration tool needed for single-file schema
5. **SSE auto-save** — intercept decision events and persist to DB without separate API call
6. **Row-level color cascade** — one class on parent, `color: inherit` on all children
