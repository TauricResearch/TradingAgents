# HTMX Playbook

**Lessons from migrating TradingAgents dashboard from HTMX auto-load to fetch().**

---

## Banned Patterns (Enforced by `just check`)

These patterns are **banned** in `server/views/*.tsx`. The `check-view-scripts.ts` gate fails the build if any appear.

| Pattern | Why banned | What to do instead |
|---|---|---|
| `dangerouslySetInnerHTML={{ __html: ... }}` | Non-cacheable, duplicated, unlintable | Extract to `server/static/scripts/*.js` |
| `<script>{`...`}</script>` | Hono HTML-encodes quotes, breaks JS | Extract to `server/static/scripts/*.js` |
| `function xxxScript(): string { return \`...\`; }` | Template-string wrapper is still inline | Extract to `server/static/scripts/*.js` |
| `<script>` without `src` attribute | Inline script — same problems as above | Add `src="/static/scripts/xxx.js"` |
| `serveStatic({ root: "./server" })` | Can leak source files | `serveStatic({ root: "./server/static" })` |

**Copy `playbooks/view-scaffold.tsx` when creating a new view.** It shows the correct pattern.

---

## Route HTML Builders → JSX Components

**The rule:** Routes that return HTML via `c.html()` must use JSX components, not string concatenation. No exceptions.

### The three-layer pattern

Every HTML-returning route follows this structure:

```
server/lib/{route}-data.ts     ← data layer (fetch, transform, cache)
server/views/{component}.tsx   ← JSX components (presentation only)
server/routes/{route}.tsx      ← thin route handler (wire data → JSX → response)
```

### Why JSX over string concat?

| String concat | JSX |
|--------------|-----|
| `html += '<div class="' + cls + '">'` | `<div class={cls}>` |
| Manual `esc()` on every dynamic value | Auto-escaped by compiler |
| Flat structure — parent/child hidden | Hierarchical — DOM structure visible |
| Typos in class names caught at runtime | Typos caught by TypeScript |
| XSS risk on every new field | Zero XSS risk |

### Extract data first

**Always** extract the data-fetching logic before writing the JSX. The data layer is reusable; the JSX is specific to one rendering.

```ts
// server/lib/signals-data.ts
export async function fetchSignalsWithHistory(
  ticker: string | undefined,
  platform: string | undefined,
): Promise<{ signals: Signal[]; priceData: Map<string, PriceWithHistory> }> {
  // ... DB queries, price fetches, caching ...
}
```

### Write JSX views

```tsx
// server/views/signals-view.tsx
export function SignalsViewHtml({ signals, priceData }: Props) {
  return (
    <table id="signals-table">
      <tbody>
        {signals.map((s) => (
          <SignalRow signal={s} priceData={priceData} />
        ))}
      </tbody>
    </table>
  );
}
```

### Thin route handler

```tsx
// server/routes/signals.tsx  ← note .tsx extension
import { SignalsViewHtml } from "../views/signals-view.tsx";

signalsRouter.get("/view/html", async (c) => {
  const { signals, priceData } = await fetchSignalsWithHistory(...);
  return c.html(<SignalsViewHtml signals={signals} priceData={priceData} />);
});
```

### Critical: file extension

Route files containing JSX **must** use `.tsx`, not `.ts`. Biome will produce misleading parse errors if you forget:

```
× expected `>` but instead found `data`
× Invalid assignment to `<SignalsViewHtml data`
```

**Fix:** Rename the file to `.tsx` and update the import in `server/index.tsx`.

### Critical: JSX style attribute

Hono JSX uses string values for `style`, not React objects:

```tsx
// ✅ Correct for Hono JSX
<div style="background:#fff3cd;color:#1a1a2e">

// ❌ React-style object (breaks in Hono)
<div style={{ background: "#fff3cd" }}>
```

### Critical: camelCase attributes

JSX uses camelCase for hyphenated/lowercase HTML attributes:

```tsx
// ✅ JSX camelCase
<td colSpan={7}>

// ❌ Standard HTML lowercase
<td colspan="7">
```

---

## Core Rule: HTMX and JSON APIs Don't Mix

HTMX expects HTML responses. JSON endpoints (`c.json(...)`) return `Content-Type: application/json`. When you use `hx-swap="innerHTML"` on a JSON endpoint, the browser dumps raw JSON into the DOM — useless.

**The fix:** Use `fetch()` directly in JavaScript for JSON APIs. Use HTMX only for HTML-responses.

```tsx
// ✅ JSON API — use fetch()
fetch('/api/positions')
  .then(r => r.json())
  .then(data => render(data));

// ❌ JSON API with HTMX — broken
<div hx-get="/api/positions" hx-swap="innerHTML" hx-trigger="load">
  // Renders: [{"ticker":"AAPL",...}] as raw text in DOM
```

---

## Pattern: pageOrPartial — Full Page vs. HTMX Partial

All routes use `pageOrPartial()` to serve the right response type:

```ts
function pageOrPartial(c: Context, view: any): Response | Promise<Response> {
  const isHtmx = c.req.header("HX-Request") === "true";
  if (isHtmx) return c.html(view);           // Partial: no Layout, no DOCTYPE
  return renderFullPage(<Layout>{view}</Layout>);  // Full page: Layout + DOCTYPE
}
```

- **Direct navigation** (browser URL bar): Full page with `<Layout>` and `<!DOCTYPE html>`
- **HTMX navigation** (tab click): Partial (just the view content, no Layout)

When returning a full page, you must manually prepend `<!DOCTYPE html>`:

```ts
function renderHtml(html: string): Response {
  return new Response(`<!DOCTYPE html>\n${html}`, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}
```

Hono's `c.html()` does NOT emit a DOCTYPE — it renders JSX starting from `<html>`. Without `<!DOCTYPE html>`, browsers fall into **Quirks Mode**, which breaks CSS and layout.

---

## DOCTYPE: The Quirks Mode Trap

**Symptoms:** `Page layout may be unexpected due to Quirks Mode` in browser devtools.

**Root cause:** Hono's `c.html()` doesn't emit `<!DOCTYPE html>`. JSX can't express a DOCTYPE — it's a declaration, not an element.

**Fix:** Wrap full-page renders in `renderHtml()` (above). HTMX partials don't need a DOCTYPE.

```ts
// index.tsx — all page routes
function renderHtml(html: string): Response {
  return new Response(`<!DOCTYPE html>\n${html}`, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

app.get("/portfolio", (c) => {
  const layout = String(<Layout><PortfolioView /></Layout>);
  return renderHtml(layout);
});

// For routes with pageOrPartial (HTMX-aware)
app.get("/holdings", (c) => {
  const isHtmx = c.req.header("HX-Request") === "true";
  if (isHtmx) return c.html(<HoldingsView />);
  const layout = String(<Layout><HoldingsView /></Layout>);
  return renderHtml(layout);
});
```

---

## Migration: JSON fetch → HTMX HTML partials

When a view needs dynamic data, you have two options. Only one is correct.

### Option A: HTMX + server-rendered HTML partials (correct)

The route returns HTML. HTMX swaps it into the DOM.

**Route:**
```tsx
// server/routes/holdings.ts
holdingsRouter.get("/positions/html", async (c) => {
  const positions = await getPositions();
  return c.html(<PositionsTable positions={positions} />);
});
```

**View:**
```tsx
// server/views/holdings.tsx
export function HoldingsView() {
  return (
    <section class="panel">
      <h3>Positions</h3>
      <div hx-get="/api/holdings/positions/html"
           hx-trigger="load"
           hx-swap="innerHTML">
        <div class="muted">Loading…</div>
      </div>
    </section>
  );
}
```

**When to use:** Any view that just displays data. The server renders the HTML. No client JS needed. This is the default.

### Option B: External JS file + fetch() (acceptable for interactivity)

When the view has client-side behaviour that HTMX can't handle (SSE event streams, complex form validation, drag-and-drop, canvas rendering).

**View:**
```tsx
export function AnalysisView() {
  return (
    <>
      <section class="panel">...</section>
      <script src="/static/scripts/analysis.js" />
    </>
  );
}
```

**External JS:**
```js
// server/static/scripts/analysis.js
document.getElementById('analysis-form').addEventListener('submit', function(e) {
  // ... complex SSE handling
});
```

**When to use:** Only when HTMX partials cannot express the interaction. Examples: SSE streaming, DataType sparkline generation from raw price arrays, form validation before submit.

### Option C: Inline dangerouslySetInnerHTML (banned)

```tsx
// ❌ NEVER DO THIS — non-cacheable, duplicated, unlintable
<script dangerouslySetInnerHTML={{ __html: holdingsScript() }} />
```

**Why banned:** See "Why we banned dangerouslySetInnerHTML for scripts" above. This pattern was used extensively and cost ~1,500 lines of duplicated, uncacheable JavaScript across 13 view files.

---

## hx-swap="none" — When You DO Want HTMX

`hx-swap="none"` is used when HTMX fires a request but you handle the result via JavaScript (e.g., on form submit to add a position):

```tsx
<form hx-post="/api/positions"
      hx-target="#positions-tbody"
      hx-swap="none"
      hx-on::after-request="loadPositions()">
```

This prevents HTMX from swapping content — your `hx-on::after-request` handler does the refresh via JS instead.

---

## JSX Attribute Typing — Watch Out

Hono JSX types follow React conventions. Some HTML attributes have surprising types:

| Attribute | JSX type | HTML |
|-----------|---------|------|
| `colspan` | `number` | `colspan="6"` → `colSpan={6}` |
| `class` | `string` (no issue) | Same |
| `onClick` | TypeScript function | Standard |

**Fix:** Use `colSpan={6}` (number) not `colspan="6"` (string) in JSX.

---

## HTMX + the Datatype Font

The Datatype font uses GSUB ligatures for chart rendering (`{l:...}`, `{b:...}`, `{p:...}`). When inserting Datatype expressions into the DOM via `innerHTML`, the `font-feature-settings: 'calt' 1, 'liga' 1` CSS rule must be applied to the container. See `playbooks/datatype-playbook.md`.

---

## Dynamic HTML Strings with Interpolation: Use data-action + Event Delegation

When building HTML dynamically in JavaScript (e.g. `html += '<button>Click</button>'`), any attribute that needs a runtime variable must use **data attributes + event delegation** — never `onclick` with string interpolation.

**Why:** `onclick="FUNC(' + var + ')'"` inside a JS string literal creates a triple-escaping recursion:
- TSX template literal `'` → Python `"` → JS `\'` → HTML `"...\'`... → infinite.
- Even when "fixed", the rendered HTML is `onclick="FUNC('' + ticker + '')"` which is syntactically valid but fragile.

**The fix: data attributes + delegation.**

```tsx
// ❌ Broken: onclick with JS string interpolation inside a template literal
html += '<button onclick="analyzeTicker(\'' + item.ticker + '\')">Analyze</button>';
// Renders as: onclick="analyzeTicker('' + item.ticker + '')" — escaping hell

// ✅ Correct: static data attributes + JS event delegation
html += '<button data-action="analyzeTicker" data-ticker="' + item.ticker + '">Analyze</button>';
```

**Delegation handler (runs once, handles all buttons):**

```tsx
function wireActions() {
  document.querySelectorAll('[data-action]').forEach(function(el) {
    el.addEventListener('click', function(e) {
      var action = e.currentTarget.dataset.action;
      if (action === 'analyzeTicker')   window.analyzeTicker(e.currentTarget.dataset.ticker);
      if (action === 'closePosition')   window.closePosition(e.currentTarget.dataset.id);
      if (action === 'viewPostMortem')  window.viewPostMortem(e.currentTarget.dataset.ticker);
    });
  });
}

// Call after every innerHTML assignment that contains [data-action] elements
el.innerHTML = html;
wireActions();
```

**Rules:**
- `data-action` — the function name (string, no parentheses or args)
- `data-ticker`, `data-id`, `data-date`, etc. — per-function arguments
- Call `wireActions()` after every `el.innerHTML = html` that injects buttons
- Static buttons with no args just use `data-action="closeAnalysisDetail"` — no extra data-* needed

**Files that use this pattern:** `workflow.tsx`, `history.tsx`, `holdings.tsx`, `prospects.tsx`.

---

## Unicode Characters in JS String Literals

When building HTML strings in Python to embed in a TSX `dangerouslySetInnerHTML` template, use actual Unicode characters — not Python escape sequences.

```python
# ❌ Written as Python escape → JS sees literal \\u20AC (broken)
html += 'Entry \u20AC' + price
# File contains two literal characters: backslash + u + 2 + 0 + A + C

# ✅ Written as actual character → JS sees € (valid unicode escape)
html += 'Entry €' + price
# File contains the single character € (UTF-8: E2 82 AC)
```

**The issue:** Python string `'\u20AC'` writes two literal characters to the file (backslash + `u20AC`). JS then parses `\u` as an escaped backslash, not a unicode escape.

**Fix an existing file with broken escapes:**
```python
with open('server/views/workflow.tsx', 'rb') as f:
    data = f.read()
replacements = {
    b'\\u20AC': '€'.encode('utf-8'),   # \u20AC → €
    b'\\u00B7': '·'.encode('utf-8'),   # \u00B7 → ·
    b'\\u2192': '→'.encode('utf-8'),   # \u2192 → →
    # ...etc
}
for old, new in replacements.items():
    data = data.replace(old, new)
with open('server/views/workflow.tsx', 'wb') as f:
    f.write(data)
```

**Verification:** Hex edit the TSX file — `€` is `E2 82 AC` (3 bytes), `\u20AC` is `5C 75 32 30 41 43` (6 bytes).

---

## HTML Injection in Dynamically-Built Strings

When building HTML via string concatenation (`html += '<div>' + data + '</div>'`), all dynamic values must be HTML-escaped. Unescaped content breaks the DOM parser when it contains `<`, `>`, or `"`.

**The rule:** every string that goes into HTML — whether as text content or an attribute value — must be escaped before concatenation.

```tsx
// ❌ Unescaped dynamic content — < or " in data breaks the DOM
html += '<div class="card-thesis">' + item.thesis + '</div>';
// If item.thesis = 'says "AI" is great' → DOM sees: class="card-thesis">says " → close quote, broken

// ✅ Escape < > & before inserting into HTML text
var _esc = function(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');};
html += '<div class="card-thesis">' + _esc(item.thesis) + '</div>';

// ✅ Escape attribute values too (escapes both quotes and angle brackets)
html += '<button data-ticker="' + _esc(item.ticker) + '">Analyze</button>';
// Quotes in ticker (e.g. "A.I.") would break: data-ticker="A.I." → closes attr early
```

**Also watch `split('\n')` vs real newlines:**
```js
// ❌ Literal backslash+n — not a newline!
var short = item.lesson.split('\n')[0];  // looks for \ + n (2 chars), not \n (newline)

// ✅ Use a regex with real newline or template literal
var short = item.lesson.split(/\r?\n/)[0];  // regex matches actual \n or \r\n
```

**Files that need escaping:** `workflow.tsx` (thesis, lesson), `exits.tsx` (thesis, invThesis, notes).

**Caution — `var` hoisting in loops:** If you define `_esc` inside a `for` loop but call it earlier in the same loop, `var` hoisting means the variable exists but is `undefined` until the assignment runs. Always define helpers before the loop that uses them:
```js
// ❌ _e defined inside loop, called before assignment (undefined!)
for (const item of items) {
  html += _e(item.text);   // called here — undefined
  var _e = function(s){...};  // defined here — too late
}

// ✅ helper defined before the loop
var _e = function(s){...};
for (const item of items) {
  html += _e(item.text);  // OK
}
```

---

## Anti-Patterns

**Don't use HTMX for polling JSON endpoints:**
```tsx
// ❌ HTMX doesn't handle JSON
<div hx-get="/api/positions" hx-trigger="load, every 30s" hx-swap="innerHTML">

// ✅ fetch() with setInterval
function refresh() {
  fetch('/api/positions').then(r => r.json()).then(render);
}
refresh();
setInterval(refresh, 30000);
```

**Don't use hx-get on select elements if you also have JS change listeners:**
```tsx
// ❌ Double-fires: HTMX fires a request AND JS handler fires fetch()
<select hx-get="/api/signals" hx-trigger="change"
        onchange="loadSignals(this.value)">

// ✅ Remove hx-get, use JS only
<select onchange="loadSignals(this.value)">
```

**Don't use onclick in dynamically-built HTML strings:**
```tsx
// ❌ Escaping hell — breaks at compile, runtime, or next edit
html += '<button onclick="analyzeTicker(\'' + ticker + '\')">Analyze</button>';

// ✅ data-action + delegation — never has quote/escape issues
html += '<button data-action="analyzeTicker" data-ticker="' + ticker + '">Analyze</button>';
```

---

## Quick Reference

| Pattern | Use when |
|---------|---------|
| `fetch()` + manual DOM | JSON APIs, polling, client-side rendering |
| `hx-post` + `hx-swap="none"` + JS handler | Form submissions where you need JS post-processing |
| `hx-get` + HTML swap | HTML-returning routes (e.g., `/api/positions/exits` returns HTML) |
| `pageOrPartial()` | Standard page routes (handles both HTMX and direct) |
| `renderHtml()` | Full-page responses that need `<!DOCTYPE html>` |
## No Backslash-Escape Sequences in dangerouslySetInnerHTML JS Strings

Hono's JSX compiler mishandles backslash sequences in `dangerouslySetInnerHTML` attribute values — they get stripped or turn into actual special characters, corrupting the JS source.

**What breaks:**
- `split('\\n')` → rendered as `split('` + LF + `')` — LF inside string literal = SyntaxError
- `indexOf('\\n')` → same issue
- `replace(/\\s/g, '')` → rendered as `replace(/s/g, '')` — backslash stripped
- `\\u20AC` → rendered as actual `\u20AC` → JS sees `\\u` = escaped backslash, not unicode escape

**Safe alternatives:**
```tsx
// Truncate without splitting on newlines
var short = item.lesson.substring(0, 80);

// Use regex LITERALS (not strings) — backslashes inside /.../ survive
var parts = text.split(/\s/);  // /\s/ is a regex literal — OK

// Use charCode to build special chars (no backslash in string)
var NL = String.fromCharCode(10);
html += text.split(NL)[0];
```

**Rule:** if you need special characters in JS strings inside a `dangerouslySetInnerHTML` attribute, write the actual bytes in the TSX source file (Python: `f.write('€'.encode('utf-8'))`) or use regex literals. Never use Python `'\\n'` or `'\\r'` escape sequences.

**Files affected and fixed:** `workflow.tsx`, `exits.tsx` — all now clean.

---

## Client-Side JS: External Files, Not Inline

**The rule:** Never embed client-side JavaScript inside TSX views. Put it in `server/static/scripts/*.js` and reference with `<script src>`.

**Why inline JS is wrong:**
- Scripts bloat every HTML response (100–300 lines per view)
- No browser caching — re-downloaded on every HTMX partial swap
- Helpers (`_esc`, `_fmt`, `_sparkline`) get copy-pasted into every view
- Violates the HTMX + SSR philosophy (server renders, client enhances)

**The correct architecture:**

```
server/static/scripts/
├── common.js          # shared helpers (_esc, _fmt, _norm, _sparkline, etc.)
├── layout.js          # tab sync, global listeners
├── portfolio.js       # portfolio-specific behaviour
├── analysis.js        # SSE event stream handling
└── ...
```

**Layout.tsx loads common.js once:**
```tsx
export function Layout(props: LayoutProps) {
  return (
    <html>
      <head>...</head>
      <body>
        {props.children}
        <script src="/static/scripts/common.js" />
        <script src="/static/scripts/layout.js" />
      </body>
    </html>
  );
}
```

**Per-view scripts load in the view component:**
```tsx
export function PortfolioView() {
  return (
    <>
      <section class="panel">...</section>
      <script src="/static/scripts/portfolio.js" />
    </>
  );
}
```

**serveStatic — absolute path + rewriteRequestPath:**

Hono's `serveStatic` joins `root` with the full request path. For a route `/static/*` and a request to `/static/style.css`, it resolves to `root + "/static/style.css"` — double-counting the `/static` prefix. Two fixes are required:

```tsx
import { serveStatic } from "hono/bun";
import { resolve } from "node:path";

const staticDir = resolve(import.meta.dir, "static");

app.use("/static/*", serveStatic({
  root: staticDir,
  rewriteRequestPath: (path) => path.replace(/^\/static/, ""),
  onFound: (_path, c) => {
    c.header("Cache-Control", "public, max-age=31536000, immutable");
  },
}));
```

1. **Absolute `root`** via `resolve(import.meta.dir, "static")` — eliminates cwd sensitivity (Bun's cwd may differ from where the process starts).
2. **`rewriteRequestPath`** strips the `/static` prefix so the middleware resolves `staticDir + "/style.css"` instead of `staticDir + "/static/style.css"`.

**Verification:**
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/static/style.css
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/static/scripts/layout.js
```

**What goes in common.js:**
```js
// server/static/scripts/common.js
function _esc(s) {
  if (s == null) return "";
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function _fmt(n, dec) { return n == null ? "\u2014" : n.toFixed(dec ?? 2); }
function _norm(vals) { /* ... */ }
function _sparkline(priceHistory) { /* ... */ }
```

**What stays inline (rare exceptions):**
- Tiny one-liners like `hx-on::after-request="loadSummary()"` — these are HTMX attributes, not scripts
- No exceptions for actual `<script>` blocks. If it's more than 5 lines, it belongs in a `.js` file.

---

## Why we banned dangerouslySetInnerHTML for scripts

This playbook previously taught `dangerouslySetInnerHTML={{ __html: functionName() }}` as the way to embed JS in Hono JSX views. This was a mistake.

**What happened:** Every view copied the pattern. Every view duplicated 6+ helper functions. View files grew to 200+ lines of non-cacheable JavaScript. The `server/scripts/*.ts` intermediate extraction (typed wrappers around template strings) was a half-measure that didn't solve the root problem.

**The fix:** Extract all JS to `server/static/scripts/*.js`, load with `<script src>`, and never look back.

**If you absolutely must inline (don't):**
Hono's JSX compiler encodes HTML entities inside `<script>{...}</script>` blocks. The old workaround was `dangerouslySetInnerHTML`. Do not use it. Move the code to an external file.

---

## Secret Sanitization Before DB Writes

Any user-facing or AI-generated text field entering the DB must be sanitized first. Secrets can leak via:
- User pasting API keys into form fields (thesis, notes, reasoning)
- AI-generated content accidentally including system prompt fragments or keys
- hLedger journal credentials in URL-embedded auth strings

**Pattern:** Use `sanitizeForDb()` from `server/lib/sanitize.ts` on every text field before INSERT.

```ts
import { sanitizeForDb } from "../lib/sanitize.ts"

// In any route handler before db.execute()/stmt.run():
const sanitizedThesis = sanitizeForDb(rawThesis);
const sanitizedNotes  = sanitizeForDb(rawNotes);
stmt.run(ticker, exchange, platform, quantity, avg_cost, sanitizedThesis, sanitizedNotes);
```

**What it strips:** OpenAI/Anthropic/Google API keys (`sk-...`), Bearer tokens, URL-embedded credentials, connection strings with secrets, private key blocks, long hex tokens.

**Python side:** `scripts/seed_database.py` has `sanitize_for_db()` applied to all text fields before INSERT.

**Files with sanitization wired:** `server/routes/analysis.ts`, `server/routes/portfolio.ts`, `server/routes/signals.ts`, `server/routes/prospects.ts`, `scripts/seed_database.py`.
