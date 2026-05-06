/** Shared HTML-escape and number-formatting helpers for JSX views. */

/** Escape HTML special characters. Returns "" for null/undefined. */
export function esc(s: string | null | undefined): string {
  if (s == null) return ""
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

/** Format a number with fixed decimals. Returns "—" for null/NaN. */
export function fmt(n: number | null | undefined, dec = 2): string {
  if (n == null || Number.isNaN(n)) return "\u2014"
  return n.toFixed(dec)
}

/** Format a GBP currency value. Returns "—" for null/NaN. */
export function fmtGBP(n: number | null | undefined, dec = 2): string {
  if (n == null || Number.isNaN(n)) return "\u2014"
  return `\u00a3${n.toFixed(dec)}`
}
