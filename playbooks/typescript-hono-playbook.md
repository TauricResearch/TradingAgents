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

**Good:**
```typescript
// ✅ String concatenation works fine
function renderSparkline(values) {
  var svg = '<svg width="' + W + '" ...>' +
            '<polyline points="' + pts + '" .../>' +
            '</svg>';
  return svg;
}

// ✅ Template literal with no HTML tags is fine
var msg = `User ${name} has ${count} items`;
```

**Alternative:** Move HTML-heavy helpers to a `.ts` file (not `.tsx`) and import them.

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

Apply this rule consistently in all route handlers that read from SQLite.

---

## HTMX + JSON APIs don't mix

HTMX expects HTML responses. If an endpoint returns JSON, use `hx-swap="none"` with a direct `fetch()` call in JavaScript. Never `hx-swap="innerHTML"` on a JSON endpoint.

---

## Error handling

Never hide errors from the UI. API responses use this structure:

```typescript
return c.json({
  error: "Short description",
  detail: (e as Error).message,
  hint: "What to do about it",
}, 500);
```

---

## Database — DatabaseFactory only

All SQLite access goes through `server/lib/db.ts` → `DatabaseFactory`.
- Never use `new Database()` directly
- Always `parseFloat()` on SQLite REAL columns

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