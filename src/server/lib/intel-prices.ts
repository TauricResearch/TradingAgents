/**
 * Live price fetching for portfolio tickers via Python script bridge.
 * Prices are cached in-process with a TTL; callers should await this for fresh data.
 */

import { spawn } from "node:child_process"
import { dirname, join } from "node:path"
import type { PriceResult } from "@lib/types"
import { endOfToday, priceCache } from "./cache.ts"
import { venvPython } from "./subprocess.ts"

async function fetchPriceForTicker(ticker: string): Promise<PriceResult> {
  const now = Date.now()
  const cached = priceCache.get(ticker)
  if (cached && cached.expires > now && cached.price !== null) {
    return { price: cached.price, currency: cached.currency ?? "USD" }
  }

  return new Promise((resolve) => {
    const python = venvPython()
    // venvPython() returns <project>/.venv/bin/python3
    // dirname 3x: .venv/bin/python3 → .venv/bin → .venv → project-root
    const projectRoot = dirname(dirname(dirname(python)))
    const script = join(projectRoot, "scripts", "py", "get_price.py")
    const child = spawn(python, [script, ticker], {
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
