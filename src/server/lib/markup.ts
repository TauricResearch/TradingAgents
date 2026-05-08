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

/** Format a number with comma separators and fixed decimals. Returns "—" for null/NaN. */
export function fmtCommas(n: number | null | undefined, dec = 2): string {
  if (n == null || Number.isNaN(n)) return "\u2014"
  const fixed = n.toFixed(dec)
  const [intPart, fracPart] = fixed.split(".") as [string, string | undefined]
  const formatted = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",")
  return fracPart !== undefined ? `${formatted}.${fracPart}` : formatted
}

/** Format a GBP currency value. Returns "—" for null/NaN. */
export function fmtGBP(n: number | null | undefined, dec = 2): string {
  if (n == null || Number.isNaN(n)) return "\u2014"
  // Place the sign before the currency symbol: "-£1,234.56", not "£-1,234.56".
  const sign = n < 0 ? "-" : ""
  return `${sign}£${fmtCommas(Math.abs(n), dec)}`
}
