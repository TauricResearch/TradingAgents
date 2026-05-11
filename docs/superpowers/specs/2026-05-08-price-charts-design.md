# Price Charts — Design Spec

**Date:** 2026-05-08
**Status:** Approved

---

## Overview

Add a 30-day close price + volume chart to each ticker card in the dashboard. Charts load lazily — data is only fetched when a card is first rendered, not on page load. A signal overlay marks the most recent BUY/SELL/HOLD decision.

---

## Backend

### New endpoint

`GET /api/tickers/{ticker}/chart`

Calls `yf.Ticker(ticker).history(period="30d")` and returns:

```json
{
  "dates": ["2026-04-08", "2026-04-09", ...],
  "close": [112.4, 113.1, ...],
  "volume": [48200000, 51000000, ...]
}
```

- Returns `404 {"error": "No data"}` if yfinance returns an empty DataFrame.
- No server-side cache — yfinance caches per process; 30-day history fetches in ~100 ms.

---

## Frontend

### Dependencies

Chart.js loaded once via CDN `<script>` in `<head>`:

```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
```

### State

Two new module-level objects alongside the existing `state = {}`:

```js
const chartInstances = {};   // ticker → Chart instance
const chartsLoaded = new Set();  // tickers whose chart data has been fetched
```

### Card markup

`renderCard(ticker)` adds a fixed-height canvas inside the card:

```html
<div class="chart-container">
  <canvas id="chart-{ticker}" style="height:120px"></canvas>
</div>
```

The container div gets a small top margin to visually separate it from the agent pills.

### Lazy load trigger

After inserting the card into the DOM, call `loadChart(ticker)` once. Guard with `chartsLoaded` to prevent duplicate fetches on reconnect or re-render:

```js
if (!chartsLoaded.has(ticker)) {
    chartsLoaded.add(ticker);
    loadChart(ticker);
}
```

### loadChart(ticker)

1. Fetches `GET /api/tickers/{ticker}/chart`.
2. On `404` or network error: shows a small "No chart data" label inside the container, returns.
3. On success, creates a Chart.js instance on `#chart-{ticker}`:
   - **Dataset 1 — close price** (type: `line`, y-axis: `y`): white line, `pointRadius: 0`, `tension: 0.3`.
   - **Dataset 2 — volume** (type: `bar`, y-axis: `y2`): semi-transparent grey (`rgba(255,255,255,0.15)`), no border.
   - **Dataset 3 — signal point** (type: `scatter`, y-axis: `y`): single point; only added if the card already has a result.

### Signal point rules

- x-value: always `chartData.dates[chartData.dates.length - 1]` — guarantees alignment with the time axis.
- BUY → green triangle-up (`pointStyle: 'triangle'`, `rotation: 0`, `backgroundColor: '#00e676'`).
- SELL → red triangle-down (`pointStyle: 'triangle'`, `rotation: 180`, `backgroundColor: '#ff1744'`).
- HOLD → grey circle (`pointStyle: 'circle'`, `backgroundColor: '#888'`).
- Signal point is also added/updated when `applyResult()` fires for a ticker whose chart is already loaded.

### Chart style

- Dark background matching the card (`#0d0d0d` or transparent).
- No gridlines, no axis labels, no legend.
- `x` axis: `type: 'category'`, ticks hidden.
- `y` (price) axis: hidden, `display: false`.
- `y2` (volume) axis: hidden, `display: false`, `position: 'right'`.
- Canvas explicit height: `canvas.style.height = '120px'`.

### Cleanup on card removal

`removeTicker(ticker)` calls before DOM removal:

```js
if (chartInstances[ticker]) {
    chartInstances[ticker].destroy();
    delete chartInstances[ticker];
}
chartsLoaded.delete(ticker);
```

---

## Files Changed

| File | Change |
|---|---|
| `backend.py` | Add `GET /api/tickers/{ticker}/chart` endpoint |
| `dashboard.html` | Add Chart.js CDN, `chartInstances`, `chartsLoaded`, `loadChart()`, canvas in `renderCard()`, cleanup in `removeTicker()`, signal update in `applyResult()` |
