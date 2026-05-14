/**
 * Portfolio benchmarking — compare portfolio returns vs. passive index.
 *
 * Uses yfinance via Python subprocess to fetch benchmark prices.
 * Portfolio returns are computed from SQLite positions + live FX prices.
 *
 * NOTE: Portfolio values use cost basis (not current market value) until
 * live price integration is wired through. This means benchmark comparisons
 * will show inaccurate alpha until that's done.
 */

import { spawn } from "node:child_process"
import { dirname, join } from "node:path"
import { DatabaseFactory } from "@lib/db"
import type { PriceResult } from "@lib/types"
import { endOfToday, priceCache } from "./cache.ts"
import { getHoldings } from "./hledger.ts"
import { venvPython } from "./subprocess.ts"

const DEFAULT_BENCHMARK = process.env.BENCHMARK ?? "VWCE.DE"

// ── Benchmark types ───────────────────────────────────────────────────────────

export interface BenchmarkPrice {
  date: string
  price: number
}

export interface PeriodReturn {
  period: "3m" | "6m" | "1y"
  portfolioPct: number
  benchmarkPct: number
  alpha: number // portfolio - benchmark
}

export interface BenchmarkResult {
  ticker: string
  currentValue: number
  benchmarkPrices: BenchmarkPrice[]
  periodReturns: PeriodReturn[]
}

// ── Portfolio types (moved from benchmark-data.ts) ───────────────────────────

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

// ── Benchmark price fetch ─────────────────────────────────────────────────────

/**
 * Fetch benchmark price history via yfinance subprocess.
 * Returns daily closing prices for the last 12 months.
 */
export function fetchBenchmarkPrices(
  ticker: string = DEFAULT_BENCHMARK,
): Promise<BenchmarkPrice[]> {
  return new Promise((resolve, reject) => {
    const script = `
import yfinance as yf, json, sys
ticker = sys.argv[1]
t = yf.Ticker(ticker)
hist = t.history(period="1y")
if hist.empty:
    print(json.dumps([]))
    sys.exit(0)
prices = [{"date": d.strftime("%Y-%m-%d"), "price": round(r["Close"], 2)} for d, r in hist.iterrows()]
print(json.dumps(prices))
`
    const child = spawn(venvPython(), ["-c", script, ticker], {
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    })

    let stdout = ""
    let stderr = ""

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString()
    })

    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString()
    })

    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`yfinance exited with code ${code}: ${stderr.trim()}`))
        return
      }
      try {
        const prices = JSON.parse(stdout.trim()) as BenchmarkPrice[]
        resolve(prices)
      } catch {
        reject(new Error(`Failed to parse benchmark prices: ${stdout.slice(0, 200)}`))
      }
    })

    child.on("error", reject)
  })
}

// ── Batch price fetch ─────────────────────────────────────────────────────────

export async function batchFetchPrices(tickers: string[]): Promise<Map<string, PriceResult>> {
  const results = new Map<string, PriceResult>()
  if (tickers.length === 0) return results

  const python = venvPython()
  // venvPython() returns <project>/.venv/bin/python3
  // dirname 3x: .venv/bin/python3 → .venv/bin → .venv → project-root
  const projectRoot = dirname(dirname(dirname(python)))
  const script = join(projectRoot, "scripts", "py", "get_price.py")
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

            const python = venvPython()
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
  const rawRows = db
    .query("SELECT * FROM positions WHERE status = 'open' ORDER BY ticker")
    .all() as Array<
    Omit<PortfolioPosition, "quantity" | "avg_cost"> & {
      quantity: number | string
      avg_cost: number | string
    }
  >
  const rows: PortfolioPosition[] = rawRows.map((r) => ({
    id: r.id,
    ticker: r.ticker,
    exchange: r.exchange,
    platform: r.platform,
    quantity: parseFloat(String(r.quantity)),
    avg_cost: parseFloat(String(r.avg_cost)),
  }))

  if (rows.length === 0) return { total: 0, positions: [], fxRates: {} }

  const tickers = [...new Set(rows.map((r) => r.ticker))]
  const fxPairs = ["GBPEUR=X", "GBPUSD=X"]
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

/**
 * Compute portfolio vs. benchmark returns for 3m, 6m, 1y periods.
 * Uses computePeriodReturns (formerly in benchmark-data.ts) — the canonical
 * version since it correctly handles the currentPortfolioValue parameter.
 */
export function computeReturns(
  benchmarkPrices: BenchmarkPrice[],
  currentPortfolioValue: number,
  historicalPortfolioValues: Record<string, number> = {},
): PeriodReturn[] {
  if (benchmarkPrices.length < 60) {
    return [] // Need at least ~3 months of data
  }

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
    const startPrice = idxPrice?.price
    if (!startPrice) continue

    const benchmarkPct = ((latest.price - startPrice) / startPrice) * 100

    // Portfolio return — use historical values if available, otherwise estimate
    const startValue = idxPrice ? historicalPortfolioValues[idxPrice.date] : undefined
    const portfolioPct = startValue
      ? ((currentPortfolioValue - startValue) / startValue) * 100
      : benchmarkPct // Fallback: assume portfolio tracks benchmark

    results.push({
      period,
      portfolioPct: Math.round(portfolioPct * 100) / 100,
      benchmarkPct: Math.round(benchmarkPct * 100) / 100,
      alpha: Math.round((portfolioPct - benchmarkPct) * 100) / 100,
    })
  }

  return results
}

/**
 * Alias for computeReturns — retained for backwards compatibility with callers
 * that import from benchmark-data.ts (now merged into benchmark.ts).
 */
export const computePeriodReturns = computeReturns

/**
 * Full benchmark check: fetch prices + compute returns.
 */
export async function getBenchmark(ticker: string = DEFAULT_BENCHMARK): Promise<BenchmarkResult> {
  const prices = await fetchBenchmarkPrices(ticker)
  const { holdings, cash } = await getHoldings()

  const currentPortfolioValue =
    holdings.reduce((s, h) => s + h.costBasis, 0) + cash.reduce((s, c) => s + c.amount, 0)

  const periodReturns = computeReturns(prices, currentPortfolioValue)

  return {
    ticker,
    currentValue: currentPortfolioValue,
    benchmarkPrices: prices,
    periodReturns,
  }
}
