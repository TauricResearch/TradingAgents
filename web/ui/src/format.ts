// Number and time formatting. All times render in UTC, the ledger's and the
// trade date's convention; the full form adds the Beijing clock, where the
// dashboard is read.

export const DASH = '—'

const cache = new Map<string, Intl.NumberFormat>()

function nf(digits: number, signed: boolean): Intl.NumberFormat {
  const key = `${digits}:${signed ? 's' : 'u'}`
  let f = cache.get(key)
  if (!f) {
    f = new Intl.NumberFormat('en-US', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
      signDisplay: signed ? 'exceptZero' : 'auto',
    })
    cache.set(key, f)
  }
  return f
}

const isNum = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x)

/** USDT amount: 2 decimals, thousands separators, no sign. */
export function fmtUsdt(x: number | null | undefined, digits = 2): string {
  return isNum(x) ? nf(digits, false).format(x) : DASH
}

/** Signed amount (PnL): +1,234.56 / -1,234.56. */
export function fmtSigned(x: number | null | undefined, digits = 2): string {
  return isNum(x) ? nf(digits, true).format(x) : DASH
}

/** LLM spend in USD: $0.42. */
export function fmtUsd(x: number | null | undefined): string {
  return isNum(x) ? `$${nf(2, false).format(x)}` : DASH
}

/** Fraction as signed percentage: 0.0015 -> +0.15%. */
export function fmtPct(x: number | null | undefined, digits = 2): string {
  return isNum(x) ? `${nf(digits, true).format(x * 100)}%` : DASH
}

/** Drawdown fraction (>= 0 below peak) shown as a loss: 0.032 -> -3.20%. */
export function fmtDrawdown(x: number | null | undefined): string {
  if (!isNum(x)) return DASH
  const pct = Math.abs(x) * 100
  return pct === 0 ? '0.00%' : `-${nf(2, false).format(pct)}%`
}

/** Plain ratio such as Sharpe or Calmar. */
export function fmtNum(x: number | null | undefined, digits = 2): string {
  return isNum(x) ? nf(digits, false).format(x) : DASH
}

/** Integer with thousands separators (token counts). */
export function fmtInt(x: number | null | undefined): string {
  return isNum(x) ? nf(0, false).format(x) : DASH
}

/** Contract quantity: signed, trailing zeros dropped (-0.0085, -4.44, +12). */
export function fmtQty(x: number | null | undefined): string {
  if (!isNum(x)) return DASH
  const body = Math.abs(x)
    .toFixed(8)
    .replace(/\.?0+$/, '')
  if (body === '0') return '0'
  return (x < 0 ? '-' : '+') + body
}

/** Unsigned quantity for sentences like "买入 0.0085 @ 101,234.50". */
export function fmtAbsQty(x: number): string {
  return fmtQty(Math.abs(x)).replace(/^\+/, '')
}

const pad2 = (n: number): string => String(n).padStart(2, '0')

/** ISO time -> "11-07 00:15 UTC". */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return DASH
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())} UTC`
}

const BEIJING_OFFSET_MS = 8 * 3_600_000

const stamp = (d: Date): string =>
  `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}`

/** ISO time -> "2026-11-07 00:15:30 UTC · 北京 2026-11-07 08:15:30", for tooltips. */
export function fmtTimeFull(iso: string | null | undefined): string {
  if (!iso) return DASH
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${stamp(d)} UTC · 北京 ${stamp(new Date(d.getTime() + BEIJING_OFFSET_MS))}`
}

/** ISO time -> "2026-11-07" (UTC date). */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return DASH
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`
}

/** ISO time -> "11-07" for chart axes. */
export function fmtDay(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`
}

/** Sign of a number as a tone for colouring. */
export function tone(x: number | null | undefined): 'up' | 'down' | 'flat' {
  if (!isNum(x) || x === 0) return 'flat'
  return x > 0 ? 'up' : 'down'
}

/** Shorten long error text for a card or a cell. */
export function truncate(s: string, max = 80): string {
  const t = s.trim().replace(/\s+/g, ' ')
  return t.length > max ? `${t.slice(0, max - 1)}…` : t
}

/** The coin of a research ticker where space is short: "BTC-USD" → "BTC". */
export function coinLabel(coin: string | null | undefined): string {
  return coin ? coin.split('-')[0] : DASH
}

/**
 * The holding window the settlement scored over, as tradingagents.backtest words it:
 * "5 trading days" → "5 个交易日"; its placeholder before any rating settled → null.
 */
export function fmtHolding(holding: string): string | null {
  const m = /^(\d+) trading days?$/.exec(holding.trim())
  return m ? `${m[1]} 个交易日` : null
}
