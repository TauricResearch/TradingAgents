# Datatype Playbook — Inline Charts via Variable Font

## What It Is

[Datatype](https://github.com/franktisellano/datatype) is an OpenType variable font that turns text expressions into inline charts via ligature substitution. No JS, no canvas, no SVG — just type and the font renders it.

## Font File

```
server/static/fonts/Datatype.woff2  (51 KB)
```

Source: [Fontsource CDN](https://fontsource.org/fonts/datatype)  
License: SIL Open Font License 1.1

## CSS Setup

Already configured in `server/static/style.css`:

```css
@font-face {
  font-family: 'Datatype';
  src: url('/static/fonts/Datatype.woff2') format('woff2');
  font-display: swap;
  font-weight: 100 900;
  font-stretch: 50% 150%;
}

.sparkline {
  font-family: 'Datatype', sans-serif;
  font-size: 1.25rem;
}
```

## Syntax

| Type | Syntax | Values | Max |
|------|--------|--------|-----|
| Sparkline | `{l:10,40,25,70,50}` | 0–100 | 20 points |
| Bar chart | `{b:30,70,20,90}` | 0–100 | 20 bars |
| Pie chart | `{p:65}` | 0–100 | single value |

**All values must be 0–100.** Use the `normalize()` helper for raw data.

## JSX Component

```tsx
import { DatatypeChart } from "./views/datatype.tsx";

// Sparkline (auto-normalized)
<DatatypeChart values={[8.45, 9.12, 10.09, 9.80, 10.50]} variant="sparkline" />

// Bar chart
<DatatypeChart values={[30, 70, 50, 90]} variant="bar" />

// Pie chart (first value used)
<DatatypeChart values={[65]} variant="pie" />
```

## Raw HTML

```html
<span class="sparkline">{l:30,70,50,90,20}</span>
<span class="bar-chart">{b:60,40,80}</span>
<span class="sparkline">{p:73}</span>
```

## Normalize Helper

The `DatatypeChart` component auto-normalizes values to 0–100:

```tsx
// These raw prices → normalized to {l:0,44,100,87,100}
<DatatypeChart values={[8.45, 9.12, 10.09, 9.80, 10.50]} />
```

For manual normalization in JS (client-side):

```js
function normalize(values) {
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const range = hi - lo || 1;
  return values.map(v => Math.round(((v - lo) / range) * 100));
}
```

## Signal Coloring

```css
.sparkline.buy  { color: var(--green); }   /* overweight, buy */
.sparkline.sell { color: var(--red); }     /* underweight, sell */
.sparkline.hold { color: var(--yellow); }  /* hold, neutral */
```

Use `signalClass(signal)` from `datatype.tsx` to get the class name.

## Current Usage

| View | Element | Type |
|------|---------|------|
| Signals timeline | confidence trend | sparkline |
| (future) Portfolio table | price history per row | sparkline |
| (future) Analysis output | debate round scores | bar chart |

## Limitations

- Values capped at 0–100 — must normalize raw data
- Max 20 data points per expression
- No per-value color control (color is set via CSS on the container)
- No axis labels or gridlines
- Static font (400 weight) from Fontsource; variable font (width/weight axes) not yet available via CDN

## Updating the Font

To replace with a newer version:

```bash
curl -L -o server/static/fonts/Datatype.woff2 \
  "https://cdn.jsdelivr.net/fontsource/fonts/datatype@latest/latin-400-normal.woff2"
```

Or download the variable font from [GitHub releases](https://github.com/franktisellano/datatype/releases) if a woff2 is available:

```bash
# Replace with actual release asset URL
curl -L -o server/static/fonts/Datatype.woff2 \
  "https://github.com/franktisellano/datatype/releases/download/vX.X.X/Datatype%5Bwdth%2Cwght%5D.woff2"
```
