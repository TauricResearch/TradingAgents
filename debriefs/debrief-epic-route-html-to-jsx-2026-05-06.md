# Debrief: Epic — Route HTML String Builders → JSX Components

**Date:** 2026-05-06
**Epic:** td-0a1897
**Scope:** Convert all route-level HTML string concatenation to typed JSX components
**Outcome:** All 8 routes refactored. Biome clean, tsc clean, all endpoints verified.

---

## What We Did

Converted 8 route files from imperative `html += '<div>'` string concatenation to declarative JSX components. Each refactor followed a strict three-step pattern:

1. **Extract data layer** → `server/lib/{route}-data.ts`
2. **Build JSX view** → `server/views/{component}.tsx`
3. **Simplify route** → `server/routes/{route}.tsx` (note: `.tsx` extension)

### Routes Converted

| Route | Old Lines | New Lines | Reduction |
|-------|-----------|-----------|-----------|
| workflow | ~390 | ~45 | 88% |
| exits | ~120 | ~30 | 75% |
| signals | ~460 | ~70 | 85% |
| portfolio-intelligence | ~520 | ~70 | 87% |
| governance | ~227 | ~85 | 63% |
| prospects | ~226 | ~85 | 62% |
| feedback | ~411 | ~60 | 85% |
| benchmark | ~275 | ~55 | 80% |
| **Total** | **~2,629** | **~500** | **~81%** |

### Files Created (24)

**Data layers (8):**
- `server/lib/workflow-data.ts`
- `server/lib/exits-data.ts`
- `server/lib/signals-data.ts`
- `server/lib/portfolio-intel-data.ts`
- `server/lib/governance-data.ts`
- `server/lib/prospects-data.ts`
- `server/lib/feedback-data.ts`
- `server/lib/benchmark-data.ts`

**JSX views (8):**
- `server/views/workflow-kanban.tsx`
- `server/views/exit-list.tsx`
- `server/views/signals-view.tsx`
- `server/views/portfolio-intel.tsx`
- `server/views/governance-view.tsx`
- `server/views/prospects-view.tsx`
- `server/views/feedback-view.tsx`
- `server/views/benchmark-view.tsx`

**Route rewrites (8):**
- `server/routes/workflow.tsx` (was `.ts`)
- `server/routes/exits.tsx` (was `.ts`)
- `server/routes/signals.tsx` (was `.ts`)
- `server/routes/portfolio-intelligence.tsx` (was `.ts`)
- `server/routes/governance.tsx` (was `.ts`)
- `server/routes/prospects.tsx` (was `.ts`)
- `server/routes/feedback.tsx` (was `.ts`)
- `server/routes/benchmark.tsx` (was `.ts`)

### Files Removed (8)

All old `.ts` route files with string builders.

### Files Modified (1)

- `server/index.tsx` — 8 import path updates (`.ts` → `.tsx`)

---

## The Pattern

### Before (string concatenation)
```ts
function buildCardHtml(item: Item): string {
  let html = '<div class="card">'
  html += `<span class="ticker">${esc(item.ticker)}</span>`
  html += `<span class="platform-tag">${esc(item.platform)}</span>`
  html += '</div>'
  return html
}

route.get("/html", (c) => {
  return c.html(buildCardHtml(data))
})
```

### After (JSX components)
```tsx
function Card({ item }: { item: Item }) {
  return (
    <div class="card">
      <span class="ticker">{item.ticker}</span>
      <span class="platform-tag">{item.platform}</span>
    </div>
  )
}

route.get("/html", (c) => {
  return c.html(<Card item={data} />)
})
```

---

## Lessons Learned

### 1. The `.ts` → `.tsx` extension is non-negotiable

Biome will produce cryptic parse errors if a route file contains JSX but retains a `.ts` extension. The errors look like:
```
× expected `>` but instead found `data`
× Invalid assignment to `<WorkflowKanban data`
```

**Fix:** Rename the file to `.tsx` before running `just check`. The error messages are misleading — the parser is treating JSX as TypeScript class syntax.

### 2. Data extraction comes first

Extract the data-fetching and transformation logic into `server/lib/{route}-data.ts` *before* touching the HTML builder. This ensures:
- The route has something to import and render
- You can test the data layer independently
- The JSX component only concerns itself with presentation

**Anti-pattern:** Trying to write JSX components while the data is still inline in the route — you end up with half-extracted state.

### 3. JSX attributes with special characters need care

The `style` attribute in JSX accepts a string (not an object, unlike React):
```tsx
// ✅ Correct for Hono JSX
<div style="background:#fff3cd;color:#1a1a2e">

// ❌ React-style object (breaks in Hono)
<div style={{ background: "#fff3cd" }}>
```

CSS custom properties with `--` are fine:
```tsx
<div style="color:var(--text)">
```

### 4. `colSpan` not `colspan`

JSX uses camelCase for HTML attributes that are hyphenated or lowercase in standard HTML:
```tsx
// ✅ JSX camelCase
<td colSpan={7}>

// ❌ Standard HTML lowercase
<td colspan="7">
```

### 5. Unicode in JSX — prefer direct characters

Instead of `\u2014` (em-dash) in strings, use the actual character `—`. The JSX compiler handles UTF-8 correctly. If you must use escapes, verify the rendered HTML contains the actual byte sequence, not literal `\u2014`.

### 6. Re-export pattern for shared types

When a data layer uses types from another module (e.g. `benchmark.ts` → `benchmark-data.ts`), re-export them so consumers only need one import:
```ts
export { type BenchmarkPrice, fetchBenchmarkPrices, type PeriodReturn } from "./benchmark.ts"
```

This avoids consumers needing to import from both `benchmark.ts` and `benchmark-data.ts`.

### 7. Biome's `organizeImports` is your friend

After creating new files with many imports, run `bunx biome check . --write` to sort and deduplicate. Don't fight the formatter — let it fix the import order.

### 8. Fail-fast protocol works

Every route refactor followed:
1. Extract data → `just check`
2. Build JSX → `just check`
3. Swap route → `just check`
4. Verify endpoint → `just check`

If any step failed, fix before proceeding. No forward-fixing on broken state. Total time for 8 routes: ~45 minutes.

---

## Verification

All endpoints tested with `curl`:

| Endpoint | Status |
|----------|--------|
| `/api/workflow/html` | ✅ 200 |
| `/api/positions/exits/html` | ✅ 200 |
| `/api/signals/view/html` | ✅ 200 |
| `/api/portfolio/intelligence/html` | ✅ 200 |
| `/api/governance/violations/html` | ✅ 200 |
| `/api/governance/rules/html` | ✅ 200 |
| `/api/prospects/html` | ✅ 200 |
| `/api/feedback/accuracy/html` | ✅ 200 |
| `/api/feedback/post-mortems/html` | ✅ 200 |
| `/api/feedback/with-positions/html` | ✅ 200 |
| `/api/benchmark/table` | ✅ 200 |

All JSON endpoints continue to work unchanged.

---

## Stats

- **Commits this session:** ~20
- **New files:** 24 (8 data + 8 views + 8 routes)
- **Files removed:** 8 (old `.ts` routes)
- **Lines removed:** ~2,629 (string concatenation)
- **Lines added:** ~1,850 (typed JSX + data layers)
- **Net reduction:** ~779 lines
- **Type safety:** Complete — zero `any`, zero manual escaping
