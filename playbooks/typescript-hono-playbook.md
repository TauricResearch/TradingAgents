# TypeScript + Hono + HTMX Playbook

## Project identity

| Layer | Tech | Notes |
|-------|------|-------|
| Server | Bun + Hono | `.tsx` files with JSX for SSR |
| Frontend | Server-rendered HTML via HTMX | No React/Vue/Svelte |
| Types | TypeScript | `tsconfig.server.json` only |
| Lint | Biome | `bunx biome check .` |

---

## File extensions

- `src/server/**/*.ts` — plain TypeScript (routes, lib utilities)
- `src/server/**/*.tsx` — Hono route handlers that return JSX (SSR views)
- `scripts/**/*.ts` — Bun scripts (run with `bun run scripts/...`)

---

## Architecture Invariants (Non-Negotiable)

These rules are enforced by `scripts/check-view-scripts.ts`. `just check` will fail if any are violated.

| Invariant | Enforcement |
|---|---|
| **No inline scripts in views** | `check-view-scripts.ts` scans `src/server/views/*.tsx` for `<script>` without `src`, `dangerouslySetInnerHTML`, and `function xxxScript()` |
| **serveStatic locked to `./src/server/static`** | `check-view-scripts.ts` verifies `src/server/index.tsx` contains `root: "./src/server/static"` |
| **HTML partials over JSON for display views** | Any view that just shows data must use `hx-get` to an `/api/.../html` route |
| **Client JS only in `src/server/static/scripts/*.js`** | Interactivity that HTMX cannot handle goes in external files, loaded via `<script src>` |

**If `just check` fails, you cannot commit. Fix the view first.**

---

## Rule 0: Always start with JSX

**If you need to render HTML, start with a JSX component. Always.**

Do not reach for string concatenation, template literals, or `dangerouslySetInnerHTML`. JSX is the first tool, not the last resort.

**Correct pattern — server-rendered HTML:**
```typescript
// Route returns JSX component as HTML
holdingsRouter.get("/positions/html", async (c) => {
  return c.html(<PositionsTable positions={enriched} />);
});

// View defines a JSX component
export function PositionsTable({ positions }: { positions: PositionRow[] }) {
  return (
    <table>
      {positions.map(pos => <PositionsTableRow pos={pos} />)}
    </table>
  );
}
```

**Correct pattern — client-side JS (when HTMX can't handle it):**
```typescript
// Put the JS in src/server/static/scripts/xxx.js, reference with <script src>
export function AnalysisView() {
  return (
    <>
      <section class="panel">...</section>
      <script src="/static/scripts/analysis.js" />
    </>
  );
}
```

**Wrong pattern — banned:**
```typescript
// ❌ Building HTML strings with innerHTML
el.innerHTML = '<table>' + rows.map(...).join('') + '</table>';

// ❌ Inline script via dangerouslySetInnerHTML — non-cacheable, duplicated
<script dangerouslySetInnerHTML={{ __html: someScript() }} />
```

**No exceptions for `<script>` blocks.** If a view needs client-side behaviour, use an external `.js` file. See `./htmx-playbook.md` → "Client-Side JS: External Files, Not Inline".

---

## Unicode escapes in JSX text — DO NOT USE

**Rule:** Never use `\uXXXX` JS string escapes in raw JSX text. They render as six literal characters (`\u00a3` → `\` `u` `0` `0` `a` `3`), not as the intended symbol.

**Why:** Hono JSX emits text between tags as literal HTML. Only inside `{ }` JS expressions does string escape processing occur.

**Bad — renders as `\u00a3100`:**
```tsx
// ❌ Raw JSX text — no JS string processing
<span>\u00a3100</span>
<span>\u2192 Next</span>
<span>\u2713 Done</span>
```

**Good — literal character:**
```tsx
// ✅ Type the symbol directly in JSX text
<span>£100</span>
<span>→ Next</span>
<span>✓ Done</span>
```

**Good — JS expression:**
```tsx
// ✅ JS string escape inside braces is processed by JS
<span>{"\u00a3"}100</span>
<span>{"\u2192"} Next</span>
<span>{"\u2713"} Done</span>

// ✅ Variable holding escape
const arrow = "\u2192"
<span>{arrow} Next</span>
```

**Good — HTML entity:**
```tsx
// ✅ Browser interprets HTML entity
<span>&pound;100</span>
<span>&rarr; Next</span>
<span>&#10003; Done</span>
```

### Quick reference: which symbols are affected

| Symbol | Escape | Used in views | Fix |
|--------|--------|-------------|-----|
| £ | `\u00a3` | portfolio-summary, intel-hero, intel-platforms | Replace with `£` |
| → | `\u2192` | prospects-view, analysis-report | Replace with `→` |
| ← | `\u2190` | analysis-report | Replace with `←` |
| ✓ | `\u2713` | workflow-kanban | Replace with `✓` |
| ✅ | `\u2705` | governance-view | Replace with `✅` |
| ✕ | `\u2715` | prospects-view | Replace with `✕` |
| ⚠ | `\u26a0` | workflow-kanban, governance-view | Replace with `⚠` |
| ⚠️ | `\u26a0\ufe0f` | intel-hero, exit-list | Replace with `⚠️` |
| ◇ | `\u25C7` | workflow-kanban | Replace with `◇` |
| ◆ | `\u25C6` | workflow-kanban | Replace with `◆` |
| ⏱ | `\u23F1` | workflow-kanban | Replace with `⏱` |
| — | `\u2014` | fmtPnl, signals-view | Replace with `—` |
| · | `\u00b7` | holdings | Replace with `·` |
| ▶ | `\u25b6` | analysis-view | Replace with `▶` |

**Test page:** Visit `/lab/currency` for a live comparison of all methods.

---

## Template literals in `.tsx` files — DO NOT USE

**Rule:** Do not use template literals (`` `...` ``) for strings containing HTML/JSX tags inside `.tsx` files.

**Why:** The TSX JSX parser applies to the entire file. Any `<tag>` inside a backtick string is misread as a JSX element, causing:
- `bun build` to silently produce wrong output
- `tsc` to throw `Expected ; but found ...` errors
- Runtime `SyntaxError: Unexpected string`

**Bad:**
```typescript
// ❌ Breaks in .tsx — <svg> inside backtick confuses JSX parser
function renderSparkline(values) {
  return `<svg width="${W}" ...><polyline .../></svg>`;
}
```

**Good (JSX component):**
```typescript
// ✅ Use a JSX component instead
function Sparkline({ values }: { values: number[] | null }) {
  if (!values?.length) return <span class="sparkline-muted">—</span>;
  return <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style="...">
    <polyline points={pts} ... />
  </svg>;
}
```

**Good (string concat only, no HTML tags):**
```typescript
// ✅ No <tags> = fine
var msg = `User ${name} has ${count} items`;
```

---

## HTMX partials — return HTML, not JSON

For HTMX-powered partial page updates, the endpoint must return HTML via `c.html()`:

```typescript
// ✅ HTMX endpoint returns HTML
holdingsRouter.get("/positions/html", async (c) => {
  return c.html(<PositionsTable positions={enriched} />);
});

// ❌ HTMX endpoint returns JSON (wrong — use hx-swap="none" + fetch instead)
holdingsRouter.get("/positions", async (c) => {
  return c.json({ positions: enriched });
});
```

In the view, use `hx-get` with the HTML endpoint:
```tsx
<div hx-get="/api/holdings/positions/html"
     hx-trigger="load,every 60s"
     hx-swap="innerHTML">
  <PositionsTable positions={positionsData.positions} />
</div>
```

---

## ParseFloat on SQLite REAL columns

SQLite returns all values as strings. REAL columns (prices, costs, quantities) must be wrapped in `parseFloat()` before arithmetic.

**Bad:**
```typescript
var costBasis = p.avg_cost * p.quantity;  // NaN — both are strings
```

**Good:**
```typescript
var costBasis = parseFloat(String(p.avg_cost)) * parseFloat(String(p.quantity));
```

---

## Error handling

Never hide errors from the UI. API responses use this structure:

```typescript
return c.json({
  error: "Short description",
  detail: (e as Error).message,
  hint: "What to do about it",
}, 500);

// For HTML/HTMX error responses:
return c.html(<div class="error-card"><strong>Error</strong><br />{(e as Error).message}</div>, 500);
```

---

## Database — DatabaseFactory only

All SQLite access goes through `src/server/lib/db.ts` → `DatabaseFactory`.
- Never use `new Database()` directly
- Always `parseFloat()` on SQLite REAL columns

---

## Route → View mapping

| Route pattern | View pattern |
|---------------|--------------|
| `GET /some/html` | `c.html(<SomeComponent data={...} />)` |
| `GET /api/some/json` | `c.json({ ... })` |
| Initial page load | `c.html(<PageComponent data={...} />)` |
| HTMX partial refresh | `c.html(<PartialComponent data={...} />)` |

---

## Quick reference

```bash
# Check TypeScript + lint
just check

# Lint only
just lint

# Auto-fix lint
just lint-fix

# Type-check only
tsc --project tsconfig.server.json --noEmit

# Server port (default 3000)
TA_DASHBOARD_PORT=3000 bun run src/server/index.tsx
```