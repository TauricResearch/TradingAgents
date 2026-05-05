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

- `server/**/*.ts` — plain TypeScript (routes, lib utilities)
- `server/**/*.tsx` — Hono route handlers that return JSX (SSR views)
- `scripts/**/*.ts` — Bun scripts (run with `bun run scripts/...`)

---

## Rule 0: Always start with JSX

**If you need to render HTML, start with a JSX component. Always.**

Do not reach for string concatenation, template literals, or `dangerouslySetInnerHTML`. JSX is the first tool, not the last resort.

**Correct pattern:**
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

**Wrong pattern:**
```typescript
// ❌ Building HTML strings with innerHTML
el.innerHTML = '<table>' + rows.map(...).join('') + '</table>';
```

The only exception: very small inline scripts with no user input (e.g. `onclick` handlers for a single button). Even then, prefer a separate JSX component.

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

All SQLite access goes through `server/lib/db.ts` → `DatabaseFactory`.
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
TA_DASHBOARD_PORT=3000 bun run server/index.tsx
```