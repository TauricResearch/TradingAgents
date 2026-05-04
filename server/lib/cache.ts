/**
 * Shared caching utilities for the dashboard server.
 */

import { spawn } from "node:child_process"
import { dirname, join } from "node:path"

/**
 * Returns milliseconds until midnight UTC.
 * Price caches expire at end of trading day — next fetch is tomorrow.
 */
export function endOfToday(): number {
  const now = new Date()
  const tomorrow = new Date(now)
  tomorrow.setUTCDate(tomorrow.getUTCDate() + 1)
  tomorrow.setUTCHours(0, 0, 0, 0)
  return tomorrow.getTime()
}

/**
 * Shared price cache used by exits.ts and workflow.ts.
 * Key: ticker. Value: { price, expires }
 * Expires at midnight UTC — one fetch per ticker per calendar day.
 */
export const priceCache = new Map<string, { price: number | null; expires: number }>()

/**
 * Fetch a single ticker price, using cache if available.
 * Uses node:child_process spawn (works in Bun and Node).
 */
export function fetchPrice(
  ticker: string,
  getPriceScript: string,
  root: string,
): Promise<number | null> {
  return new Promise((resolve) => {
    const now = Date.now()
    const cached = priceCache.get(ticker)
    if (cached && cached.expires > now) {
      resolve(cached.price)
      return
    }

    const child = spawn("python3", [getPriceScript, ticker], {
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    })
    let resolved = false
    const finish = (price: number | null) => {
      if (resolved) return
      resolved = true
      child.kill()
      priceCache.set(ticker, { price, expires: endOfToday() })
      resolve(price)
    }
    let stdout = ""
    child.stdout.on("data", (d: Buffer) => { stdout += d.toString() })
    setTimeout(() => finish(null), 8_000)
    child.on("close", (code) => {
      if (code !== 0) { finish(null); return }
      try { const data = JSON.parse(stdout.trim()); finish(data.price ?? null) }
      catch { finish(null) }
    })
    child.on("error", () => finish(null))
  })
}