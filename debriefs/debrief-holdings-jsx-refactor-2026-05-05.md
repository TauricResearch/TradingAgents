# Debrief: Holdings JSX Refactor (in progress)

**Date:** 2026-05-05
**Status:** Partially complete — foundation done, integration needs finishing

---

## What was done

### Architecture established

The refactor follows the right pattern:
- JSX components render HTML on the server
- HTMX handles partial page updates via `/api/holdings/positions/html`
- No `dangerouslySetInnerHTML` template literals

### Files changed

| File | What |
|------|------|
| `server/views/holdings.tsx` | Stripped client JS, added JSX components (`StopBadge`, `FreshnessBadge`, `Sparkline`, `PositionsTable`, `HoldingsPage`) |
| `server/routes/holdings.tsx` | Renamed from `.ts`, added `/api/holdings/positions/html` endpoint returning `c.html(<PositionsTable />)` |
| `server/index.tsx` | Import updated, route uses `HoldingsPage` |

### JSX components now working (verified)

- `GET /api/holdings/positions/html` returns pre-rendered HTML with SVG sparklines, freshness badges, stop badges
- `StopBadge`, `FreshnessBadge`, `Sparkline` render correctly

### What's working end-to-end

```
GET /api/holdings/positions/html → full positions table as HTML (SVG sparklines ✓, badges ✓)
GET /holdings → HoldingsPage renders (empty data, HTMX will fill)
```

---

## What's not yet done

1. **`/holdings` route passes empty data** — `HoldingsPage` is called with `holdingsData: { holdings: [], platforms: [], cash: [] }` and `positionsData: { positions: [] }`. This means the initial page render has no holdings or positions data. The HTMX refresh on `/api/holdings/positions/html` will populate positions, but holdings (from hledger) are still missing.

2. **Holdings section** (`/holdings` page) uses empty `holdingsData` — the hledger cash/holdings section renders as "No holdings found" instead of actual data.

3. **HTMX endpoint URL** — corrected to `/api/holdings/positions/html` (was `/api/holdings/positions` which returns JSON, not HTML).

---

## Next steps for next session

### Step 1: Verify `/api/holdings/positions/html` works
```bash
just serve  # start server
curl http://localhost:3000/api/holdings/positions/html | head -c 500
# Should show SVG sparklines, freshness badges, stop badges, position rows
```

### Step 2: Fix initial holdings data (HIGH PRIORITY)
The `GET /holdings` route needs to pass real data to `HoldingsPage`:
- Fetch holdings from hledger (`getHoldings()`)
- Fetch positions from SQLite (reuse logic from `/api/holdings/positions`)
- Pass both to `<HoldingsPage holdingsData={...} positionsData={...} />`

The route should be in `server/routes/holdings.tsx` alongside the existing endpoint, or in `server/index.tsx`.

### Step 3: Verify full page render
```bash
curl http://localhost:3000/holdings | grep -E "positions-body|NVDA|AAPL|sparkline"
```
Should show positions panel with real data, SVG sparklines.

### Step 4: Verify HTMX refresh
Navigate to `/holdings`, wait 60s, verify positions panel auto-refreshes without page flicker.

---

## Key files to know

| File | Role |
|------|------|
| `server/views/holdings.tsx` | All JSX components: `StopBadge`, `FreshnessBadge`, `Sparkline`, `PositionsTable`, `HoldingsPage` |
| `server/routes/holdings.tsx` | Route: `GET /api/holdings/positions/html` → `c.html(<PositionsTable />)` |
| `server/index.tsx` | Mounts holdingsRouter, has `/holdings` route with `HoldingsPage` |
| `server/lib/hledger.ts` | `getHoldings()` — fetches holdings from hledger |

---

## Anti-patterns to avoid (lesson learned)

- **No template literals with `<tags>` inside `.tsx` files** — the JSX parser chokes. Use JSX components directly or string concatenation with `String.fromCharCode(34)` for quotes.
- **No `dangerouslySetInnerHTML` with template literal strings** — replace with JSX components rendered via `c.html(<Component />)`.
- **No `innerHTML` string building in client-side scripts** — use JSX, let HTMX handle updates.

---

## Playbook updated

`playbooks/typescript-hono-playbook.md` captures:
- `.tsx` template literal rule
- `parseFloat()` on SQLite REAL columns
- HTMX + JSON API separation
- `DatabaseFactory` only
- Error response structure