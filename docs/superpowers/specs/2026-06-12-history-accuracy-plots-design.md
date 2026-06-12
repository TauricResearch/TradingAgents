# History Accuracy Plots (replacing text stats)

## Overview

Replace the current text-based `HistoryStats` block in the Historical Analysis
drawer with three interactive plots that show prediction performance **across
all delta time horizons**, not just a single delta.

## Current State

- `HistoryStats.tsx` renders one line of text: "N runs · X right · Y wrong · Z
  pending · P% right" plus a per-action breakdown (BUY/SELL/HOLD).
- `computeStats()` computes a single `Stats` object for one `deltaMs`.
- The delta slider selects which delta to evaluate — the user can only see one
  delta's stats at a time.

## Goal

1. **Accuracy vs Δ line chart** — y-axis = percent accuracy
   (right/(right+wrong)), x-axis = delta time values (log scale).
2. **Successes & Failures vs Δ line chart** — two lines (success count, failure
   count) sharing the same x-axis.
3. Keep the OHLC candlestick chart + volume bars as-is.
4. Move the delta slider next to the OHLC chart (grouped with Candle and Refresh
   controls).
5. Remove the `HistoryStats` text block.

## Data Flow

### Client-side computation (verdicts.ts additions)

All curve computation happens in the frontend using already-fetched data (bars +
runs from `getTickerHistory`). No server changes needed.

**Nearest-price lookup:**
```
function findNearestBar(bars: Bar[], targetTimeMs: number): Bar | null
```
Finds the bar whose timestamp is closest to `targetTimeMs` (before or after).
This handles gaps in ticker data (nights, weekends) by using the nearest actual
price.

**Accuracy-curve verdict (nearest-price variant):**
```
function computeVerdictNearestPrice(
  run: RunLike, bars: Bar[], deltaMs: number,
  holdThresholdPct: number, nowIso: string,
): Verdict
```
Same semantics as `computeVerdict` but passes only the single nearest bar to
T+Δ as the window. Implemented as a thin wrapper:
1. Compute `targetTimeMs = isoToMs(run.startedAt) + deltaMs`.
2. Call `findNearestBar(bars, targetTimeMs)` to get the closest bar.
3. Pass `[nearestBar]` (or `[]` if null) as `windowBars` to `computeVerdict`.
This reuses ALL existing verdict logic (target hit/miss, direction, HOLD
threshold, tie detection).

**Curve computation:**
```
function computeAccuracyCurve(
  runs: RunLike[], bars: Bar[], deltas: number[],
  holdThresholdPct: number, nowIso: string,
): AccuracyPoint[]
```
Where `AccuracyPoint = { delta: number; total: number; right: number;
wrong: number; unknown: number; rightPct: number | null }`.

### Discrete delta set

Fixed set of delta values (milliseconds):

```
5m, 15m, 30m, 1h, 2h, 4h, 8h, 1d, 3d, 1w, 2w, 1mo, 3mo, 6mo, 1y
```

Deltas where `right + wrong === 0` (no scored runs) are filtered out from the
plot. Remaining points are connected by the line chart.

## Layout (revised per user feedback)

```
┌─────────────────────────────────────┐
│ Header (ticker, range selector, X)  │
├─────────────────────────────────────┤
│ [Candle ▼] [Refresh ▼]  [Δ slider] │  ← controls grouped, slider near chart
│                                     │
│  OHLC Chart (candles + volume)      │  ← unchanged
│                                     │
├─────────────────────────────────────┤
│                                     │
│  Accuracy vs Delta (line chart)     │  ← NEW: y=% right, x=delta (log)
│                                     │
├─────────────────────────────────────┤
│                                     │
│  Successes & Failures vs Δ (lines)  │  ← NEW: 2 lines, same x-axis
│                                     │
├─────────────────────────────────────┤
│  Run list (scrollable)              │  ← unchanged
└─────────────────────────────────────┘
```

### Components

1. **`AccuracyPlot.tsx`** — Recharts `LineChart` showing one line
   (`rightPct`). Y-axis domain `[0, 1]` formatted as `0%–100%`. X-axis uses
   log-scale positions, tick labels formatted with `fmtDelta`. Tooltip shows
   delta + accuracy + counts (right/wrong/total).

2. **`SuccessFailurePlot.tsx`** — Recharts `LineChart` with two lines:
   "successes" (right count) and "failures" (wrong count). Same x-axis as
   accuracy plot. Y-axis is integer count. One legend.

 3. **`HistoricalAnalysisDrawer.tsx`** changes:
   - Import and render `AccuracyPlot` + `SuccessFailurePlot` instead of
     `HistoryStats`.
   - Compute `accuracyCurve` via `useMemo(computeAccuracyCurve, [runs, bars,
     holdThresholdPct, tick.nowIso])`.
   - Move `HistoryControls` from below stats to above the OHLC chart, in the
     toolbar row alongside Candle and Refresh selectors. Reduce its visual
     weight (compact, inline). Both the Δ slider and the HOLD% slider move
     together.
   - Keep `deltaMs` state and pass it to `HistoryChart` for reference markers.
     **The delta slider ONLY affects OHLC chart markers** (run bands, target
     lines, start dots). The accuracy and S+F plots always show all deltas
     regardless of the slider position.
   - Keep the per-run `verdicts` Map computation (line 146-159) as-is — it
     still uses the slider-selected `deltaMs` for OHLC chart coloring.

### Chart styling

- Match the existing chart aesthetic: `#e2e8f0` grid, `#64748b` axis labels,
  white background, 10px font.
- Accuracy line: `#2563eb` (blue-600).
- Success line: `#16a34a` (green-600).
- Failure line: `#dc2626` (red-600).
- Y-axis domain `[0, 1]` for accuracy; `[0, auto]` for success/failure counts.
- X-axis tick formatting reuses `fmtDelta` from `format.ts`.

## Files Changed

| File | Change |
|------|--------|
| `src/verdicts.ts` | Add `findNearestBar`, `computeVerdictNearestPrice`, `computeAccuracyCurve`, `AccuracyPoint` type |
| `src/components/AccuracyPlot.tsx` | **New** — accuracy vs Δ line chart |
| `src/components/SuccessFailurePlot.tsx` | **New** — successes & failures vs Δ line chart |
| `src/components/HistoricalAnalysisDrawer.tsx` | Wire new plots, move slider to toolbar, remove HistoryStats |
| `src/components/HistoryStats.tsx` | **Remove** |

## Edge Cases

- **No price data in range:** Show a centered "No data" message in each plot
  area (same style as the drawer's existing "No price data" handling).
- **Only 1–2 runs:** Deltas may have 0 scored runs. Filter those points out;
  the line only connects points with scored data.
- **All runs pending:** `rightPct` is `null` for all deltas. Plot shows empty
  axes with a note.
- **Single bar in range:** `findNearestBar` trivially returns that bar.
- **Very large run count (10k+):** Computation still O(runs × deltas). With 15
  deltas × 10k runs = 150k iterations, each is a simple lookup. `useMemo`
  caches result; recomputes only when runs/bars change.
