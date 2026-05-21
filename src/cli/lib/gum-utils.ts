/**
 * Gum CLI utilities — terminal styling via charmbracelet/gum.
 *
 * Wraps `gum` subprocess calls. Falls back gracefully to plain text
 * if gum is not installed or when stdout is not a TTY.
 *
 * Usage:
 *   import { gumStyle, gumTable, gumJoin, isGumAvailable } from "../lib/gum-utils"
 */

import { spawnSync } from "node:child_process"

// ── Detection ────────────────────────────────────────────────────────────────

let _checked = false
let _available = false

/**
 * Check if gum is installed and we're in a TTY.
 * Result is cached after first call.
 */
export function isGumAvailable(): boolean {
  if (_checked) return _available
  _checked = true
  try {
    const result = spawnSync("gum", ["--version"], { stdio: "pipe", timeout: 2000 })
    _available = result.status === 0 && process.stdout.isTTY
  } catch {
    _available = false
  }
  return _available
}

// ── Operations ───────────────────────────────────────────────────────────────

export interface GumStyleOptions {
  foreground?: string // hex color or gum color name (e.g. "#00ff00", "2", "green")
  background?: string
  bold?: boolean
  italic?: boolean
  border?: "none" | "normal" | "double" | "rounded" | "thick" | "hidden"
  padding?: string // e.g. "0 1" or "1 2"
  margin?: string
  width?: number
  height?: number
  align?: "left" | "center" | "right"
}

/**
 * Style text with gum. Falls back to plain text if gum unavailable.
 */
export function gumStyle(text: string, options: GumStyleOptions = {}): string {
  if (!isGumAvailable()) return text

  const args: string[] = []
  if (options.foreground) args.push("--foreground", options.foreground)
  if (options.background) args.push("--background", options.background)
  if (options.bold) args.push("--bold")
  if (options.italic) args.push("--italic")
  if (options.border && options.border !== "none") args.push("--border", options.border)
  if (options.padding) args.push("--padding", options.padding)
  if (options.margin) args.push("--margin", options.margin)
  if (options.width) args.push("--width", String(options.width))
  if (options.height) args.push("--height", String(options.height))
  if (options.align) args.push("--align", options.align)

  const result = spawnSync("gum", ["style", ...args], {
    input: text,
    stdio: ["pipe", "pipe", "pipe"],
    timeout: 5000,
  })

  if (result.status !== 0) return text
  return result.stdout.toString().trimEnd()
}

/**
 * Render a table with Unicode box-drawing characters.
 * Columns are left-padded to their max width. Works in any terminal (no TTY required).
 */
export function boxTable(columns: string[], rows: string[][]): string {
  // Calculate column widths (max of header and all cells)
  const colWidths = columns.map((col, i) => {
    const cellWidths = rows.map((r) => stripAnsi(r[i] ?? "").length)
    return Math.max(stripAnsi(col).length, ...cellWidths)
  })

  const pad = (text: string, width: number): string => {
    const stripped = stripAnsi(text)
    return text + " ".repeat(width - stripped.length)
  }

  const sep = (left: string, mid: string, right: string, fill: string): string => {
    return left + colWidths.map((w) => fill.repeat(w + 2)).join(mid) + right
  }

  const top = sep("┌", "┬", "┐", "─")
  const mid = sep("├", "┼", "┤", "─")
  const bot = sep("└", "┴", "┘", "─")

  const header = `│ ${columns.map((c, i) => pad(c, colWidths[i]!)).join(" │ ")} │`
  const body = rows.map(
    (row) => `│ ${row.map((cell, i) => pad(cell, colWidths[i]!)).join(" │ ")} │`,
  )

  return [top, header, mid, ...body, bot].join("\n")
}

/** Remove ANSI escape sequences to get visual length */
function stripAnsi(text: string): string {
  // biome-ignore lint/suspicious/noControlCharactersInRegex: ANSI escape sequence matcher
  return text.replace(/\[[0-9;]*m/g, "")
}

/**
 * Join lines vertically or horizontally.
 * Falls back to plain text join when gum is unavailable.
 */
export function gumJoin(
  items: string[],
  _direction: "vertical" | "horizontal" = "vertical",
): string {
  if (!isGumAvailable()) {
    return items.join("\n")
  }
  // gum join works via piping; for programmatic use, return items joined
  return items.join("\n")
}

/**
 * Print a gum-styled line directly to stdout.
 * Use this to avoid the intermediate string allocation for large output.
 */
export function gumPrint(text: string, options: GumStyleOptions = {}): void {
  if (!isGumAvailable()) {
    console.log(text)
    return
  }
  console.log(gumStyle(text, options))
}
