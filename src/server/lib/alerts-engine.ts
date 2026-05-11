/**
 * Alert matching engine — pure function that evaluates alert rules against
 * current price data. No side effects, no I/O.
 *
 * Takes alert rules and a map of ticker → latest price data, returns the
 * subset of alerts that are currently triggered.
 */

import type { AlertCondition, AlertRule, TriggeredAlert } from "./types.ts"

// ── Price Data ────────────────────────────────────────────────────────────────

export interface PriceData {
  close: number
  closePrev?: number // previous day's close (for % change)
}

// ── Internal ──────────────────────────────────────────────────────────────────

interface MatchContext {
  price: number
  pctChange?: number
}

function evaluateCondition(condition: AlertCondition, ctx: MatchContext): boolean {
  const { type, threshold } = condition

  switch (type) {
    case "price_below":
      return ctx.price <= (threshold ?? 0)

    case "price_above":
      return ctx.price >= (threshold ?? Infinity)

    case "pct_change_day":
      if (ctx.pctChange == null || threshold == null) return false
      return Math.abs(ctx.pctChange) >= threshold

    case "pct_change_week": {
      // Weekly change is approximated as 5× daily change from prev close
      if (ctx.pctChange == null || threshold == null) return false
      return ctx.pctChange >= threshold
    }

    case "signal_change":
      // signal_change is handled externally (requires signal history)
      // Here we just return false; caller should check signals table separately
      return false

    case "price_cross":
      // price_cross requires prev price, skip in engine
      return false

    default:
      return false
  }
}

function buildMessage(alert: AlertRule, ctx: MatchContext): string {
  if (alert.message) return alert.message

  const { type, threshold } = alert.condition
  const price = `£${ctx.price.toFixed(2)}`

  switch (type) {
    case "price_below":
      return `🔴 ${alert.name}: ${price} ≤ £${(threshold ?? 0).toFixed(2)}`
    case "price_above":
      return `🟢 ${alert.name}: ${price} ≥ £${(threshold ?? 0).toFixed(2)}`
    case "pct_change_day":
      return `⚡ ${alert.name}: ${ctx.pctChange?.toFixed(1)}% day change (≥ ${threshold}%)`
    case "pct_change_week":
      return `📅 ${alert.name}: ${ctx.pctChange?.toFixed(1)}% week change (≥ ${threshold}%)`
    case "signal_change":
      return `📡 ${alert.name}: signal changed`
    case "price_cross":
      return `↕ ${alert.name}: price crossed £${(threshold ?? 0).toFixed(2)}`
    default:
      return `⚠️ ${alert.name}: condition met`
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

/**

 * Evaluates all enabled alert rules against the given price data.
 *
 * @param alerts       — all alert rules to evaluate
 * @param prices       — map of ticker → PriceData (only tickers with alerts)
 * @param signalsMap   — optional map of ticker → last signal (for signal_change alerts)
 */
export function matchAlerts(
  alerts: AlertRule[],
  prices: Record<string, PriceData>,
  _signalsMap?: Record<string, string>,
): TriggeredAlert[] {
  const enabled = alerts.filter((a) => a.enabled)

  return enabled
    .map((alert) => {
      // Skip cross-ticker or portfolio-level alerts (handled by caller)
      if (!alert.ticker) return null

      const priceData = prices[alert.ticker]
      if (!priceData) return null

      const pctChange = priceData.closePrev
        ? (() => {
            const c = parseFloat(String(priceData.close))
            const p = parseFloat(String(priceData.closePrev))
            if (!Number.isFinite(c) || !Number.isFinite(p) || p === 0) return undefined
            return ((c - p) / p) * 100
          })()
        : undefined

      const ctx: MatchContext = {
        price: priceData.close,
        pctChange,
      }

      const triggered = evaluateCondition(alert.condition, ctx)
      if (!triggered) return null

      return {
        alert,
        currentPrice: priceData.close,
        pctChange,
        message: buildMessage(alert, ctx),
      } satisfies Omit<TriggeredAlert, "currentPrice"> & { currentPrice: number }
    })
    .filter(Boolean) as TriggeredAlert[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Returns the set of tickers referenced by enabled alerts.
 */
export function tickersFromAlerts(alerts: AlertRule[]): string[] {
  return [...new Set(alerts.filter((a) => a.enabled && a.ticker).map((a) => a.ticker as string))]
}

/**
 * Loads latest prices for the given tickers from the SQLite prices table.
 * Returns a map of ticker → PriceData.
 */
export function loadPriceMap(
  tickers: string[],
  db: import("bun:sqlite").Database,
): Record<string, PriceData> {
  if (tickers.length === 0) return {}

  const placeholders = tickers.map(() => "?").join(",")
  const rows = db
    .query(
      `SELECT
         p.ticker,
         p.close,
         p_prev.close AS close_prev
       FROM prices p
       LEFT JOIN prices p_prev ON p_prev.ticker = p.ticker
       AND p_prev.date = (
         SELECT MAX(date) FROM prices WHERE ticker = p.ticker AND date < p.date
       )
       WHERE p.ticker IN (${placeholders})
         AND p.date = (SELECT MAX(date) FROM prices WHERE ticker = p.ticker)`,
    )
    .all(...tickers) as { ticker: string; close: number; close_prev: number | null }[]

  const map: Record<string, PriceData> = {}
  for (const row of rows) {
    map[row.ticker] = {
      close: row.close,
      closePrev: row.close_prev ?? undefined,
    }
  }
  return map
}
