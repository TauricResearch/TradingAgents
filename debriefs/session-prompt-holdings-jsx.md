# Next session prompt: Finish Holdings JSX Refactor

**Branch:** `fix/portfolio-reset-and-seed-alignment`
**PR:** https://github.com/pjsvis/TradingAgents/pull/6

---

## What works

```bash
# Start server
just serve

# These work:
curl http://localhost:3000/api/holdings/positions/html
# Returns pre-rendered HTML with SVG sparklines ✓, freshness badges ✓, stop badges ✓

# HoldingsPage renders (but with empty data):
curl http://localhost:3000/holdings
```

The JSX components (`StopBadge`, `FreshnessBadge`, `Sparkline`, `PositionsTable`, `HoldingsPage`) are all in `server/views/holdings.tsx`.
The HTML endpoint (`GET /api/holdings/positions/html`) is in `server/routes/holdings.tsx`.

---

## What needs finishing

### 1. Pass real data to HoldingsPage on GET /holdings

The route in `server/index.tsx` currently passes empty data:

```typescript
// server/index.tsx line 106
app.get("/holdings", (c) => pageOrPartial(c,
  <HoldingsPage
    holdingsData={{ holdings: [], platforms: [], cash: [] }}
    positionsData={{ positions: [] }}
  />
));
```

**Fix:** Fetch real data in the route handler:
- Call `getHoldings()` from `server/lib/hledger.ts` for `holdingsData`
- Reuse the positions query logic (or call the existing SQLite query) for `positionsData`
- Pass both to `HoldingsPage`

The data fetching logic is already written in `server/routes/holdings.tsx` (the `/api/holdings` and `/api/holdings/positions` endpoints). Extract it into a shared function.

### 2. Verify HTMX refresh

After step 1, verify:
- `GET /holdings` renders with real holdings data AND positions data
- After 60s, positions panel auto-refreshes via `hx-get="/api/holdings/positions/html"`
- No flicker, no page reload

---

## Files involved

| File | What to change |
|------|----------------|
| `server/index.tsx` | Fetch real data, pass to `HoldingsPage` |
| `server/routes/holdings.tsx` | May need to extract data-fetching logic into reusable functions |
| `server/views/holdings.tsx` | Already done — no changes needed |

---

## Run checklist

```bash
just check                          # must exit 0
just serve &
sleep 2

# 1. Check HTML endpoint
curl http://localhost:3000/api/holdings/positions/html | grep "sparkline\|position-row"

# 2. Check full page (should show positions, not "No open positions")
curl http://localhost:3000/holdings | grep -E "positions-body|NVDA|AAPL|sparkline"

# 3. Wait 65s, check positions auto-refreshed
# (manual check in browser or curl twice)

pkill -9 -f "bun run server"
```

---

## Anti-patterns (don't repeat)

- **No template literals with `<tags>` in `.tsx`** → use JSX components
- **No `innerHTML` string building** → use JSX, let HTMX handle updates
- **HTMX endpoints return `c.json()`** → must use `c.html(<Component />)`
- **No `dangerouslySetInnerHTML` with template literals** → use `c.html()`

See `playbooks/typescript-hono-playbook.md` for full rules.

---

## Epic tasks (td)

```
td-8dd762  epic: Holdings view refactor
  td-057b9e  task: StopBadge, FreshnessBadge, Sparkline as JSX components   [DONE]
  td-64ddd7  task: PositionsPartial JSX component                          [DONE]
  td-4765e1  task: /api/holdings/positions/html → c.html(PositionsTable)   [DONE]
  td-a0bbd4  task: HTMX refresh on positions panel                         [DONE]
  td-00571e  chore: strip dangerouslySetInnerHTML                          [in_progress]
  td-4cf10f  task: HoldingsPage with real data                           [todo]
  td-84a488  task: verify GBP conversion in API                          [todo]
  td-786aae  task: full e2e verification                                   [todo]
```

---

## When done

Commit with message: "feat(holdings): complete JSX refactor — HTMX partials, pre-converted GBP values"

Update PR description, verify CI passes, hand off for review.