/** Benchmark data layer — extracted from route for reuse. */
import { spawn } from "node:child_process"
import { join } from "node:path"
import type { BenchmarkPrice, PeriodReturn } from "./benchmark.ts"
import { findProjectRoot } from "./utils.ts"

export { type BenchmarkPrice, fetchBenchmarkPrices, type PeriodReturn } from "./benchmark.ts"

import { DatabaseFactory } from "../../lib/db.ts"
import { endOfToday, priceCache } from "./cache.ts"
import type { PriceResult } from "./types.ts"

// ── Types ─────────────────────────────────────────────────────────────────────

export interface PortfolioPosition {
  id: number
  ticker: string
  exchange: string
  platform: string
  quantity: number
  avg_cost: number
}

export interface PositionWithPrice extends PortfolioPosition {
  currentPriceGbp: number | null
  currentValueGbp: number | null
  costValueGbp: number
}

// ── Batch price fetch ─────────────────────────────────────────────────────────

export async function batchFetchPrices(tickers: string[]): Promise<Map<string, PriceResult>> {
  const results = new Map<string, PriceResult>()
  if (tickers.length === 0) return results

  const script = join(findProjectRoot(), "scripts", "py", "get_price.py")
  const BATCH_SIZE = 4

  for (let i = 0; i < tickers.length; i += BATCH_SIZE) {
    const batch = tickers.slice(i, i + BATCH_SIZE)
    const settled = await Promise.all(
      batch.map(
        (ticker) =>
          new Promise<[string, PriceResult]>((resolve) => {
            const cached = priceCache.get(ticker)
            const now = Date.now()
            if (cached && cached.expires > now && cached.price !== null) {
              resolve([ticker, { price: cached.price, currency: "USD" }])
              return
            }

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
                  priceCache.set(ticker, { price: data.price, expires: endOfToday() })
                }
                resolve([ticker, { price: data.price ?? null, currency: data.currency ?? "USD" }])
              } catch {
                resolve([ticker, { price: null, currency: "USD" }])
              }
            })
            child.on("error", () => resolve([ticker, { price: null, currency: "USD" }]))
          }),
      ),
    )
    for (const [ticker, data] of settled) results.set(ticker, data)
  }

  return results
}

// ── Live portfolio value ──────────────────────────────────────────────────────

export async function getLivePortfolioValue(): Promise<{
  total: number
  positions: PositionWithPrice[]
  fxRates: Record<string, number>
}> {
  const db = DatabaseFactory.get()
  const rows = db
    .query("SELECT * FROM positions WHERE status = 'open' ORDER BY ticker")
    .all() as PortfolioPosition[]

  if (rows.length === 0) return { total: 0, positions: [], fxRates: {} }

  const tickers = [...new Set(rows.map((r) => r.ticker))]
  const fxPairs = ["GBPEUR=X", "GBPUSD=X", "GBPEUR", "GBPUSD"]
  const allTickers = [...tickers, ...fxPairs]

  const priceResults = await batchFetchPrices(allTickers)

  const fxRates: Record<string, number> = {}
  for (const fx of ["GBPEUR=X", "GBPUSD=X"]) {
    const data = priceResults.get(fx)
    if (data?.price != null) {
      const key = fx.replace("=X", "")
      fxRates[key] = data.price
    }
  }
  if (!fxRates.GBPEUR) fxRates.GBPEUR = 1.18
  if (!fxRates.GBPUSD) fxRates.GBPUSD = 1.27

  const gbpPerEur = 1 / fxRates.GBPEUR
  const gbpPerUsd = 1 / fxRates.GBPUSD

  let total = 0
  const positions: PositionWithPrice[] = rows.map((p) => {
    const priceData = priceResults.get(p.ticker)
    let currentPriceGbp: number | null = null

    if (priceData?.price != null) {
      const raw = priceData.price
      if (priceData.currency === "EUR") {
        currentPriceGbp = raw * gbpPerEur
      } else if (priceData.currency === "USD") {
        currentPriceGbp = raw * gbpPerUsd
      } else {
        currentPriceGbp = raw
      }
    }

    let costValueGbp = p.avg_cost * p.quantity
    if (p.exchange === "US" && fxRates.GBPUSD) {
      costValueGbp = (p.avg_cost * p.quantity) / fxRates.GBPUSD
    } else if ((p.exchange === "XETRA" || p.exchange === "EUR") && fxRates.GBPEUR) {
      costValueGbp = (p.avg_cost * p.quantity) / fxRates.GBPEUR
    }

    const currentValueGbp = currentPriceGbp != null ? currentPriceGbp * p.quantity : null
    if (currentValueGbp != null) total += currentValueGbp

    return {
      ...p,
      currentPriceGbp,
      currentValueGbp,
      costValueGbp,
    }
  })

  return { total: Math.round(total * 100) / 100, positions, fxRates }
}

// ── Period returns ────────────────────────────────────────────────────────────

export function computePeriodReturns(
  benchmarkPrices: BenchmarkPrice[],
  _currentPortfolioValue: number,
): PeriodReturn[] {
  if (benchmarkPrices.length < 60) return []

  const latest = benchmarkPrices[benchmarkPrices.length - 1]
  if (!latest) return []

  const periods: Array<{ period: "3m" | "6m" | "1y"; days: number }> = [
    { period: "3m", days: 63 },
    { period: "6m", days: 126 },
    { period: "1y", days: 252 },
  ]

  const results: PeriodReturn[] = []
  for (const { period, days } of periods) {
    const idx = Math.max(0, benchmarkPrices.length - days)
    const idxPrice = benchmarkPrices[idx]
    if (!idxPrice) continue

    const startPrice = idxPrice.price
    const benchmarkPct = ((latest.price - startPrice) / startPrice) * 100
    const portfolioPct = benchmarkPct // fallback: assume portfolio tracks benchmark

    results.push({
      period,
      portfolioPct: Math.round(portfolioPct * 100) / 100,
      benchmarkPct: Math.round(benchmarkPct * 100) / 100,
      alpha: Math.round((portfolioPct - benchmarkPct) * 100) / 100,
    })
  }

  return results
}
