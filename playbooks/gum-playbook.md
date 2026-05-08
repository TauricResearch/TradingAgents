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

## When NOT to Use Gum

- Inside the Bun/Hono server (serves HTML, not terminal)
- In browser-facing output (HTMX expects HTML, not ANSI codes)
- For log files (escape codes make logs unreadable)

Gum is for CLI scripts only.
