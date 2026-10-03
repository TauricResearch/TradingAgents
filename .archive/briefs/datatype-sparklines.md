# Brief: DataType Font Integration for Dashboard Charts

**Date:** 2026-05-03
**Status:** Required
**Author:** Agent

---

## Background

The dashboard has a `DatatypeChart` component (`server/views/datatype.tsx`) that wraps the DataType variable font. The font supports three chart types encoded as text:

- **{l:values}** — sparkline (line chart)
- **{b:values}** — bar chart
- **{p:value}** — pie chart

The font is at `server/static/fonts/Datatype.woff2` with GSUB ligatures enabled. CSS sets `font-feature-settings: 'calt' 1, 'liga' 1` and the `{...}` syntax activates chart rendering.

**Current state:** `datatype.tsx` exists but is unused. Views use emoji or CSS bars as chart placeholders.

**Decision:** Use DataType sparklines for price trend display. No interaction required — trend at a glance only.

---

## Data Source

`GET /api/prices/:ticker` returns:
```json
{
  "ticker": "AAPL",
  "price": 280.14,
  "history": [
    { "date": "2026-04-14", "close": 258.83 },
    ...
  ],
  "timestamp": "2026-05-03T17:09:17Z"
}
```

`history[]` contains the last ~20 closes in chronological order (oldest first). **Reverse before passing to `DatatypeChart`** so the sparkline trends left-to-right with most recent on the right.

```ts
// In client-side JS (inside dangerouslySetInnerHTML script):
var closes = priceData.history.map(h => h.close).reverse();
html += '<span class="datatype-chart">' + sparklineExpr(normalize(closes)) + '</span>';
```

---

## Where to Apply

### 1. Signals view — price history sparkline
Each signal row gets a sparkline of the last 20 closes. Color matches signal type.

```
Signal   Ticker   Price   Trend      AI Conf
────────────────────────────────────────────────
Buy      AAPL     €188    {l:...}    0.80
Hold     MSFT     €415    {l:...}    0.62
```

### 2. Portfolio view — P&L sparkline
Each position row gets a sparkline of its price history (last 20 closes). Entry date and cost already in card — sparkline shows recent trend only.

### 3. Governance view — position weight bar chart
Each position shows a horizontal bar `{b:value}` where bar width = position weight as % of portfolio. Color encodes limit status.

### 4. Exits view — distance-to-stop bar
Each exit plan gets a `{b:distancePct}` bar showing how far current price is from stop loss. Color: green (>20%), yellow (10-20%), red (<10%).

### 5. Benchmark view — portfolio vs benchmark sparkline
Two sparklines: `{l:portfolio_returns}` vs `{l:benchmark_returns}`. Shows alpha over time.

---

## Implementation Steps

**Step 1:** Wire `DatatypeChart` into the signals view. Fetch price history from `/api/prices/:ticker`, reverse the array, render with `signalClass()` for coloring.

**Step 2:** Add P&L sparklines to the portfolio positions table. Same pattern — fetch price history, reverse, render.

**Step 3:** Add position weight bars to governance violations.

**Step 4:** Add benchmark sparklines once portfolio total value is wired into the benchmark route.

**Step 5:** Add exit distance bars in the exits view using `distanceToStopPct` from exit status.

---

## Technical Notes

- **Data source:** `GET /api/prices/:ticker` → `history[]`. Reverse before rendering — history is oldest-first, sparkline trends left-to-right with most recent on the right.
- The `{...}` syntax must appear in a span with `font-family: Datatype` and `font-feature-settings: 'calt' 1, 'liga' 1`.
- Values in `{l:}` and `{b:}` expressions are 0-100 integers. Use the `normalize()` helper in `datatype.tsx`.
- The `variant` prop handles all three types: `"sparkline"` | `"bar"` | `"pie"`.
- Signal coloring: use `signalClass(signal)` to get `"buy"` | `"sell"` | `"hold"` CSS class.

---

## Constraints

- Datatype font requires variable font support (GSUB table). Static fonts from CDN won't work — use `server/static/fonts/Datatype.woff2` only.
- Charts are monochrome by default. Color must come from the parent element's CSS class (e.g. `class="datatype-chart positive"` sets color on the parent).
- No tooltips or interaction — just static trend info.

---

## Success Criteria

- [ ] Signals view: price history sparkline on each row, color matches signal type
- [ ] Portfolio view: P&L sparkline on each position row
- [ ] Governance: position weight bars on violation rows
- [ ] All chart values computed from live `/api/prices/:ticker` data, not hardcoded
- [ ] CSS `font-feature-settings: 'calt' 1, 'liga' 1` applied to all chart spans
- [ ] `datatype.tsx` is the only chart-rendering code — no ad-hoc `{l:...}` strings outside the component