# Color Tools

Small TypeScript utilities for working with CSS color values in the dashboard project.

## `convert-hex-to-oklch.ts`

Converts hex color declarations inside a CSS `:root` block to `oklch()`, preserving the original hex in trailing comments.

### Why oklch?

oklch provides uniform perceptual lightness. Changing the `l` (lightness) channel of an oklch color by 10% produces a visibly consistent change regardless of hue. This makes it ideal for:

- **Generating hover/active states** by lightening/darkening a base color predictably.
- **Theme variants** (e.g. a light mode palette derived from the same hue/chroma values).
- **Accessible contrast tuning** — small lightness adjustments reliably hit WCAG targets.

### Usage

```bash
# Convert default stylesheet (server/static/style.css) in-place
bun scripts/color-tools/convert-hex-to-oklch.ts

# Convert a specific file, writing to a different output
bun scripts/color-tools/convert-hex-to-oklch.ts src/colors.css src/colors-oklch.css
```

### Just verb

```bash
just convert-hex-oklch
```

### Before / after

```css
/* Before */
:root {
  --bg: #0f1117;
  --surface: #1a1d27;
}

/* After */
:root {
  --bg: oklch(17.833% 0.01281 270.6); /* #0f1117 */
  --surface: oklch(23.974% 0.01717 270.6); /* #1a1d27 */
}
```

### Dependencies

- [`colorizr`](https://github.com/gilbarbara/colorizr) — zero-dependency TypeScript color library focused on oklch/oklab.
