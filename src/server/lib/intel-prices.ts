import { spawn } from "node:child_process"
import { join } from "node:path"
import { endOfToday, priceCache } from "./cache.ts"
import type { PriceResult } from "./types.ts"
import { findProjectRoot } from "./utils.ts"

async function fetchPriceForTicker(ticker: string): Promise<PriceResult> {
  const now = Date.now()
  const cached = priceCache.get(ticker)
  if (cached && cached.expires > now && cached.price !== null) {
    return { price: cached.price, currency: cached.currency ?? "USD" }
  }

  return new Promise((resolve) => {
    const script = join(findProjectRoot(), "scripts", "py", "get_price.py")
    const child = spawn("python3", [script, ticker], {
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      timeout: 12_000,
    })
    let stdout = ""
    child.stdout.on("data", (d: Buffer) => {
      stdout += d.toString()
    })
    child.on("close", () => {
      try {
        const data = JSON.parse(stdout.trim())
        if (data.price != null) {
          priceCache.set(ticker, {
            price: data.price,
            currency: data.currency,
            expires: endOfToday(),
          })
        }
        resolve({ price: data.price ?? null, currency: data.currency ?? "USD" })
      } catch {
        resolve({ price: null, currency: "USD" })
      }
    })
    child.on("error", () => resolve({ price: null, currency: "USD" }))
  })
}

export async function fetchPrices(tickers: string[]): Promise<Map<string, PriceResult>> {
  const results = new Map<string, PriceResult>()
  if (tickers.length === 0) return results

  const settled = await Promise.all(
    tickers.map(
      (t) =>
        new Promise<[string, PriceResult]>((resolve) => {
          fetchPriceForTicker(t).then((r) => resolve([t, r]))
        }),
    ),
  )
  for (const [ticker, data] of settled) results.set(ticker, data)
  return results
}
