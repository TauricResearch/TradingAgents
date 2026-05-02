# Datatype Playbook — Inline Charts via Variable Font

## What It Is

[Datatype](https://franktisellano.github.io/datatype) is an OpenType variable font that turns text expressions into inline charts via **GSUB ligature substitution**. No JS, no canvas, no SVG — type the syntax and the font renders it.

## Font File

```
server/static/fonts/Datatype.woff2  (82 KB, variable font)
```

**Must be the variable font.** The static woff2 from Fontsource has no GSUB table and will not render charts.

Source: [GitHub repo](https://github.com/franktisellano/datatype) — `fonts/variable/Datatype[wdth,wght].woff2`
License: SIL Open Font License 1.1

## Three Chart Types

| Syntax | Renders | Max | Example |
|--------|---------|-----|---------|
| `{l:30,70,50,90}` | Sparkline (line) | 20 values | `{l:45,55,72,85}` |
| `{b:30,70,50,90}` | Bar chart | 20 values | `{b:45,55,72,85}` |
| `{p:65}` | Pie chart (filled %) | 1 value | `{p:85}` |

**All values: 0–100.** Normalize raw data before use.

## CSS Required

Every element that contains Datatype expressions **must** have:

```css
.chart {
  font-family: 'Datatype', sans-serif;
  font-feature-settings: 'calt' 1, 'liga' 1;
  -webkit-font-feature-settings: 'calt' 1, 'liga' 1;
  font-variation-settings: 'wdth' 100, 'wght' 400;
}
```

**The `calt` feature is mandatory.** Without it, you'll see raw text like `{l:30,70,50}` instead of a chart.

## Variable Font Axes

| Axis | Tag | Range | Default | Controls |
|------|-----|-------|---------|----------|
| Width | `wdth` | 50–150 | 100 | Chart density/spacing |
| Weight | `wght` | 100–900 | 400 | Stroke thickness |

```css
/* Thin, wide sparkline */
.sparkline-light {
  font-variation-settings: 'wdth' 125, 'wght' 200;
}

/* Bold, compact bar chart */
.bar-bold {
  font-variation-settings: 'wdth' 75, 'wght' 700;
}
```

## JSX Component

`server/views/datatype.tsx` provides a typed helper:

```tsx
import { DatatypeChart } from "./views/datatype.tsx";

// Sparkline (auto-normalized from raw values)
<DatatypeChart values={[8.45, 9.12, 10.09, 9.80]} variant="sparkline" />

// Bar chart
<DatatypeChart values={[30, 70, 50, 90]} variant="bar" />

// Pie chart (first value used as %)
<DatatypeChart values={[65]} variant="pie" />
```

## Normalize Helper

```tsx
// In datatype.tsx
function normalize(values: number[], min?: number, max?: number): number[] {
  const lo = min ?? Math.min(...values);
  const hi = max ?? Math.max(...values);
  const range = hi - lo || 1;
  return values.map(v => Math.round(((v - lo) / range) * 100));
}
```

For client-side JS:

```js
function normalize(values) {
  var lo = Math.min.apply(null, values);
  var hi = Math.max.apply(null, values);
  var range = hi - lo || 1;
  return values.map(function(v) { return Math.round(((v - lo) / range) * 100); });
}
```

## Signal Color Coding

```css
.sparkline.buy  { color: var(--green); }   /* overweight, buy */
.sparkline.sell { color: var(--red); }     /* underweight, sell */
.sparkline.hold { color: var(--yellow); }  /* hold, neutral */
```

```ts
export function signalClass(signal: string): "buy" | "sell" | "hold" {
  const s = signal.toLowerCase();
  if (s.includes("buy") || s.includes("overweight")) return "buy";
  if (s.includes("sell") || s.includes("underweight")) return "sell";
  return "hold";
}
```

## Current Usage

| View | Element | Type | Source |
|------|---------|------|--------|
| Signals timeline (top) | Confidence trend | sparkline `{l:...}` | Signals data |
| Signals timeline (row 2) | Confidence bars | bar chart `{b:...}` | Signals data |
| Signals timeline (per row) | Confidence level | pie chart `{p:...}` | Per-signal confidence |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Raw text `{l:30,70}` showing | Wrong font file (static, not variable) | Replace with `Datatype[wdth,wght].woff2` from repo |
| Raw text showing | `calt` feature not enabled | Add `font-feature-settings: 'calt' 1` |
| Raw text showing | Browser cached old font | Hard refresh (Cmd+Shift+R) |
| Pie not rendering | Confidence is string from SQLite | `parseFloat(s.confidence)` before `Math.round()` |
| Row not colored | Class on child spans, not parent div | Put class on parent, children use `color: inherit` |
| Chart too small | `font-size` too small | Increase to 1.5rem+ |
| Font not loading | Wrong MIME type | Server must return `font/woff2` |
| Font not loading | Wrong MIME type | Server must return `font/woff2` |

### Verify the font file

```bash
cd /Users/petersmith/Dev/GitHub/TradingAgents
.venv/bin/python3 -c "
from fontTools.ttLib import TTFont
f = TTFont('server/static/fonts/Datatype.woff2')
print('GSUB:', 'GSUB' in f)
print('calt:', 'calt' in [r.FeatureTag for r in f['GSUB'].table.FeatureList.FeatureRecord])
print('Glyphs:', f['maxp'].numGlyphs)  # Should be ~10,850
"
```

## Updating the Font

```bash
# Clone repo and copy variable font
cd /tmp && rm -rf datatype
git clone --depth 1 https://github.com/franktisellano/datatype.git
cp datatype/fonts/variable/Datatype\[wdth,wght\].woff2 \
  /path/to/TradingAgents/server/static/fonts/Datatype.woff2
```

## Limitations

- Values **must** be 0–100 (integer)
- Max **20 data points** per expression
- No per-value color control (color set via CSS on container)
- No axis labels, gridlines, or tooltips
- LLM-generated chart text could theoretically produce invalid syntax — no validation layer yet
