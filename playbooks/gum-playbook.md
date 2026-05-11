# Gum Playbook

## What

[Gum](https://github.com/charmbracelet/gum) is a CLI tool from Charm that provides
styled terminal output — borders, colours, alignment, padding — without writing
terminal escape codes by hand.

## Why

ASCII box-drawing characters (`╔═╗`, `┌─┐`, etc.) are fragile. They depend on:
- Terminal font (monospace? CJK width?)
- Character width calculations
- Manual padding math

Gum uses terminal escape codes. Works everywhere, looks consistent, no math.

## Installation

Already in `flox.toml` (required):

```toml
[install]
gum.pkg-path = "gum"
```

Also available via Homebrew: `brew install gum`

## Project Helper

Use `scripts/lib/gum.ts` — thin wrapper around `gum style` via `Bun.spawn`:

```typescript
import { gum } from "./lib/gum.ts"

// Single-line styled text
console.log(await gum("Hello", ["--bold", "--foreground", "212"]))

// Multi-line bordered box
const box = await gum(text, ["--border", "rounded", "--padding", "1 2", "--width", "56"])
console.log(box)
```

**Never use `child_process.execSync`.** Use `Bun.spawn` with `stdin: "pipe"`.
The helper already does this.

## Common Patterns

### Header

```typescript
await gum("TradingAgents", [
  "--bold", "--foreground", "212",
  "--width", "56", "--align", "center",
])
```

### Bordered Table

```typescript
const rows = [
  "Service            Status     PID",
  "───────────────────────────────",
  "Dashboard Server   ● running  49039",
].join("\n")

await gum(rows, [
  "--border", "rounded",
  "--padding", "1 2",
  "--width", "56",
])
```

### Status Line

```typescript
// Green = OK
await gum("✓ Dashboard responding", ["--foreground", "2"])

// Yellow = Warning
await gum("! Port 3000 not responding", ["--foreground", "3"])

// Red = Error
await gum("✗ Server not running", ["--foreground", "1"])
```

## Colour Reference

Gum uses ANSI colour numbers:

| Number | Colour | Use |
|--------|--------|-----|
| 1 | Red | Error, stopped, breach |
| 2 | Green | OK, running, passing |
| 3 | Yellow | Warning, unknown |
| 4 | Blue | Info, neutral |
| 7 | White | Headers, labels |
| 212 | Pink | Brand accent |

## Flags Reference

| Flag | Values | Purpose |
|------|--------|---------|
| `--border` | `none`, `normal`, `rounded`, `thick`, `double` | Box style |
| `--padding` | `"1 2"` (vertical horizontal) | Inner spacing |
| `--width` | `56` | Force width (prevents terminal auto-width) |
| `--align` | `left`, `center`, `right` | Text alignment |
| `--foreground` | `1`–`255` | Text colour (ANSI) |
| `--background` | `1`–`255` | Background colour (ANSI) |
| `--bold` | — | Bold text |
| `--italic` | — | Italic text |

## Multi-line Text

Pass `\n` in the text string. The helper pipes via `stdin.write()`, so embedded
newlines work correctly:

```typescript
const multi = "Line 1\nLine 2"
await gum(multi, ["--border", "rounded"])
```

**Do NOT** pass multi-line text as a command-line argument. Gum interprets
lines after the first as extra positional arguments, producing garbage output.

## Validated Pattern: Service Status Table

**Source of truth:** `scripts/server-lifecycle.ts` `status()` (post-2026-05-08).

Problem: Display multiple services with state, detail, and associated `just` verb.
Constraints: Must not wrap, must be readable at any terminal width, must support
future services without layout changes.

### The Winning Pattern (Template E)

```typescript
const dotColour: Record<"running" | "stopped" | "error" | "unknown", string> = {
  running: "\x1b[32m", stopped: "\x1b[90m",
  error: "\x1b[31m", unknown: "\x1b[33m",
}

// Build plain-text rows with ANSI inline dots
const lines = [
  `${"Service".padEnd(maxName + 2)}${"Status".padEnd(10)}${"Detail".padEnd(maxDetail + 2)}Verb`,
  "─".repeat(maxName + maxDetail + 24),
  ...rows.map(r => {
    const dot = `${dotColour[r.state]}●\x1b[0m`
    return `${dot} ${r.name.padEnd(maxName + 1)} ${r.state.padEnd(9)} ${r.detail.padEnd(maxDetail + 2)}${r.verb}`
  }),
]

// One border. Dynamic width. No --width flag.
const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])

// Title and hint OUTSIDE the box — never wrap
const title = await gum("TradingAgents", ["--bold", "--foreground", "212"])
console.log(`  ${title}`)
console.log(box)
console.log(`  \x1b[90mhint: just <verb> → ...\x1b[0m`)
```

### Why This Wins

| Approach | Why It Fails |
|----------|-------------|
| Fixed `--width` + variable content | Wraps inside box, breaks layout |
| Nested borders (cards) | Visual noise, brittle side-by-side splicing |
| Title inside the box | Title text wraps if too long |
| `gum` per-row colour | `--foreground` applies to whole block, not per row |
| Pure ANSI no border | Lacks visual presence, hard to scan |

**Rule:** One border around the data. Title and hint outside. Inline ANSI dots
for per-row colour. Dynamic width via `padEnd()` math, not `--width`.

## Validated Pattern: Multi-Column Financial Table

**Source of truth:** `src/cli/commands/portfolio.ts`, `src/cli/commands/alerts.ts`
(post-2026-05-08).

For tables with many columns (Ticker, Platform, Qty, Price, Cost, Value, P&L, %):

```typescript
const maxTicker = Math.max(6, ...rows.map((r) => r.ticker.length))

const lines = [
  `${"Ticker".padEnd(maxTicker + 2)}${"Qty".padStart(6)} ${"Price".padStart(10)} ${"P&L".padStart(14)}`,
  "─".repeat(maxTicker + 36),
  ...rows.map((r) => {
    const pnlColour = r.pnl >= 0 ? "\x1b[32m" : "\x1b[31m"
    const reset = "\x1b[0m"
    return `${r.ticker.padEnd(maxTicker + 2)}${String(r.qty).padStart(6)} ${r.price.toFixed(2).padStart(10)} ${pnlColour}${fmtGBP(r.pnl).padStart(14)}${reset}`
  }),
]

const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
```

**Key difference from service status tables:** Financial tables need inline
ANSI for per-row P&L colour. The dot pattern (●) from Template E works, but
for dense data, embed the colour directly in the value cell.

## The One Border Rule (General Principle)

**Every Gum display should have at most one border.**

Multiple nested borders create visual noise and brittle layout code
(side-by-side card splicing, width calculations). One border around the
data, titles and hints outside. This applies to:
- Service status tables
- Financial tables
- Alert displays
- Any multi-line output

The only exception: when showing genuinely separate datasets (e.g. two
unrelated tables) where a gap between single-border boxes is clearer than
one massive box.

## When NOT to Use Gum

- Inside the Bun/Hono server (serves HTML, not terminal)
- In browser-facing output (HTMX expects HTML, not ANSI codes)
- For log files (escape codes make logs unreadable)

Gum is for CLI scripts only.
