# Brief: DataType Font Integration for Dashboard Charts

**Date:** 2026-05-03
**Status:** Draft
**Author:** Agent

---

## Background

The dashboard has a `DatatypeChart` component (`server/views/datatype.tsx`) that wraps the DataType variable font. The font supports three chart types encoded as text:

- **{l:values}** — sparkline (line chart)
- **{b:values}** — bar chart
- **{p:value}** — pie chart

The font is already at `server/static/fonts/Datatype.woff2` with GSUB ligatures enabled. The CSS sets `font-feature-settings: 'calt' 1, 'liga' 1` and the `{...}` syntax activates the chart rendering.

**Current state:** `datatype.tsx` exists but is unused. All chart placeholders in views use emoji or CSS bars.

---

## Rationale

**Why this matters:**

- **No canvas/SVG needed** — charts are just text, rendered by the font. Zero JS, zero DOM overhead.
- **Consistent aesthetic** — all charts use the same monospace-adjacent font as the rest of the UI. No external charting library.
- **Dense data** — sparklines in a table cell give trend info without consuming layout space. Appropriate for a dashboard.
- **Already paid for** — the font is in the project, the CSS is written, the component exists. Low cost to wire it up.

---

## Where to Apply

### 1. Signals view — price history sparkline
Each signal row gets a sparkline of the last 20 closes (most recent → oldest, left to right). Shows price trend leading up to the signal date.

Data: `GET /api/prices/:ticker` → `history[]` (last 20 closes, chronological). Reverse before passing to `DatatypeChart` so line trends left-to-right with most recent on the right.

```
Signal   Ticker   Price   Trend      AI Conf
────────────────────────────────────────────────
Buy      AAPL     €188    {l:...}    0.80
Hold     MSFT     €415    {l:...}    0.62
```

The `signalClass()` helper maps signal type → CSS class (buy/sell/hold). Color the sparkline accordingly.

### 2. Portfolio view — P&L sparkline
Each position row gets a sparkline of its price history (last 20 closes, most recent first). Shows current trend. Entry date and cost are already in the card — sparkline shows the shape of recent price action only.

Data: `GET /api/prices/:ticker` → `history[]`. Reverse before use.

### 3. Governance view — position weight bar chart
Each position shows a horizontal bar `{b:value}` where the bar width = position weight as % of portfolio. The bar color encodes whether it's within or outside the limit.

### 4. Benchmark view — portfolio vs benchmark sparkline
Two sparklines overlaid: `{l:portfolio_returns}` vs `{l:benchmark_returns}`. Shows alpha over time.

### 5. Exits view — distance-to-stop bar
Each exit plan gets a `{b:distancePct}` bar showing how far current price is from stop loss. Color: green (>20%), yellow (10-20%), red (<10%).

---

## Implementation Steps

**Step 1:** Wire `DatatypeChart` into the signals view. Reverse `priceData.history` before rendering. Use `signalClass()` for coloring.

**Step 2:** Add P&L sparklines to the portfolio positions table. Fetch price history from `/api/prices/:ticker`, reverse, then render.

**Step 3:** Add position weight bars to governance violations. Normalize weights to 0-100 range for the bar expression.

**Step 4:** Add benchmark sparklines once portfolio total value is wired into the benchmark route.

**Step 5:** Add exit distance bars in the exits view using distanceToStopPct from the exit status computation.

---

## Technical Notes

- **Data source:** `GET /api/prices/:ticker` returns `history[]` — last 20 closes in chronological order (oldest first). **Reverse the array before passing to `DatatypeChart`** so the sparkline trends left-to-right with most recent on the right.
  ```ts
  // In client-side JS (inside the dangerouslySetInnerHTML script):
  var closes = priceData.history.map(function(h) { return h.close; });
  closes.reverse(); // now most recent first (left-to-right trend)
  html += '<span class="datatype-chart buy">' + sparklineExpr(normalize(closes)) + '</span>';
  ```
- The `{...}` syntax must appear in a span with `font-family: Datatype` and `font-feature-settings: 'calt' 1, 'liga' 1`.
- Values in `{l:}` and `{b:}` expressions are 0-100 integers. Use the `normalize()` helper in `datatype.tsx`.
- The `variant` prop handles all three types: `"sparkline"` | `"bar"` | `"pie"`.
- Signal coloring: use `signalClass(signal)` to get `"buy"` | `"sell"` | `"hold"` CSS class.

---

## Constraints

- Datatype font requires variable font support (GSUB table). Static fonts from CDN won't work — use `server/static/fonts/Datatype.woff2` only.
- Charts are monochrome by default. Color must come from the parent element's CSS class (e.g. `class="datatype-chart positive"` sets color on the parent).
- No tooltips or interaction — just static trend info. If interactivity is needed, use a real charting library instead.

---

## Success Criteria

- [ ] At least 3 views use `DatatypeChart` with real data
- [ ] All chart values are computed from live API data, not hardcoded
- [ ] CSS `font-feature-settings` applied to all chart spans
- [ ] `datatype.tsx` is the only chart-rendering code in the codebase (no ad-hoc `{l:...}` strings outside the component)