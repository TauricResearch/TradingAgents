/** Portfolio data layer — extracted from route for reuse. */
import { spawn } from "node:child_process"
import { join } from "node:path"
import { DatabaseFactory } from "../../lib/db.ts"
import { endOfToday, priceCache } from "./cache.ts"
import { findProjectRoot } from "./utils.ts"

// ── Types ─────────────────────────────────────────────────────────────────────

export interface PriceData {
  price: number | null
  currency: string
  history: { date: string; close: number }[]
}

export interface PositionEnriched {
  id: number
  ticker: string
  exchange: string
  platform: string
  quantity: number
  avg_cost: number
  entry_date: string
  thesis: string | null
  // enriched fields
  current_price_gbp: number | null
  current_value_gbp: number | null
  cost_value_gbp: number | null
  pnl_gbp: number | null
  pnl_pct: number | null
  currency: string
  price_history: { date: string; close: number }[] | null
}

export interface PortfolioSummary {
  positions: PositionEnriched[]
  totals: {
    portfolio_value_gbp: number | null
    total_cost_gbp: number | null
    total_pnl_gbp: number | null
    total_pnl_pct: number | null
    positions_count: number
  }
  fx_rates: Record<string, number>
}

// ── Batch price fetching ─────────────────────────────────────────────────────

async function batchFetchPrices(tickers: string[]): Promise<Map<string, PriceData>> {
  const results = new Map<string, PriceData>()
  const root = findProjectRoot()
  const script = join(root, "scripts", "py", "get_price.py")

  const fetches = tickers.map(
    (ticker) =>
      new Promise<[string, PriceData]>((resolve) => {
        const cached = priceCache.get(ticker)
        const now = Date.now()
        if (cached && cached.expires > now) {
          resolve([ticker, { price: cached.price, currency: "USD", history: [] }])
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
            const price = data.price ?? null
            const currency = data.currency ?? "USD"
            if (price != null) {
              priceCache.set(ticker, { price, expires: endOfToday() })
            }
            const history: { date: string; close: number }[] = (data.history ?? []).slice(-20)
            resolve([ticker, { price, currency, history }])
          } catch {
            resolve([ticker, { price: null, currency: "USD", history: [] }])
          }
        })
        child.on("error", () => resolve([ticker, { price: null, currency: "USD", history: [] }]))
      }),
  )

  const settled = await Promise.all(fetches)
  for (const [ticker, data] of settled) {
    results.set(ticker, data)
  }
  return results
}

// ── Main computation ─────────────────────────────────────────────────────────

export async function computePortfolioSummary(): Promise<PortfolioSummary> {
  const db = DatabaseFactory.get()
  const rows = db
    .query("SELECT * FROM positions WHERE status = 'open' ORDER BY ticker")
    .all() as Array<{
    id: number
    ticker: string
    exchange: string
    platform: string
    quantity: number
    avg_cost: number
    entry_date: string
    thesis: string | null
  }>

  if (rows.length === 0) {
    return {
      positions: [],
      totals: {
        portfolio_value_gbp: 0,
        total_cost_gbp: 0,
        total_pnl_gbp: 0,
        total_pnl_pct: null,
        positions_count: 0,
      },
      fx_rates: {},
    }
  }

  const tickers = [...new Set(rows.map((r) => r.ticker))]
  const fxPairs = ["GBPEUR=X", "GBPUSD=X", "GBPEUR", "GBPUSD"]
  const allTickers = [...tickers, ...fxPairs]
  const priceResults = await batchFetchPrices(allTickers)

  const fxRates: Record<string, number> = {}
  for (const fx of fxPairs) {
    const data = priceResults.get(fx)
    if (data?.price != null) {
      const key = fx.replace("=X", "").replace("=", "")
      fxRates[key] = data.price
    }
  }

  if (!fxRates.GBPEUR) fxRates.GBPEUR = 1.18
  if (!fxRates.GBPUSD) fxRates.GBPUSD = 1.27

  const gbpPerEur = 1 / fxRates.GBPEUR
  const gbpPerUsd = 1 / fxRates.GBPUSD

  let totalValue = 0
  let totalCost = 0

  const enriched: PositionEnriched[] = rows.map((p) => {
    const priceData = priceResults.get(p.ticker) ?? null
    let currentPriceGbp: number | null = null

    if (priceData?.price != null) {
      const rawPrice = priceData.price
      if (priceData.currency === "EUR") {
        currentPriceGbp = rawPrice * gbpPerEur
      } else if (priceData.currency === "USD") {
        currentPriceGbp = rawPrice * gbpPerUsd
      } else {
        currentPriceGbp = rawPrice
      }
    }

    const quantity = p.quantity
    let costValueGbp = p.avg_cost * quantity
    if (p.exchange === "US" && fxRates.GBPUSD) {
      costValueGbp = (p.avg_cost * quantity) / fxRates.GBPUSD
    } else if ((p.exchange === "XETRA" || p.exchange === "EUR") && fxRates.GBPEUR) {
      costValueGbp = (p.avg_cost * quantity) / fxRates.GBPEUR
    }

    const currentValueGbp = currentPriceGbp != null ? currentPriceGbp * quantity : null
    const pnlGbp = currentValueGbp != null ? currentValueGbp - costValueGbp : null
    const pnlPct = costValueGbp > 0 && pnlGbp != null ? (pnlGbp / costValueGbp) * 100 : null

    if (currentValueGbp != null) totalValue += currentValueGbp
    totalCost += costValueGbp

    return {
      ...p,
      current_price_gbp: currentPriceGbp != null ? Math.round(currentPriceGbp * 100) / 100 : null,
      current_value_gbp: currentValueGbp != null ? Math.round(currentValueGbp * 100) / 100 : null,
      cost_value_gbp: Math.round(costValueGbp * 100) / 100,
      pnl_gbp: pnlGbp != null ? Math.round(pnlGbp * 100) / 100 : null,
      pnl_pct: pnlPct != null ? Math.round(pnlPct * 100) / 100 : null,
      currency: priceData?.currency ?? "GBP",
      price_history: priceData?.history ?? null,
    }
  })

  enriched.sort((a, b) => {
    if (a.pnl_gbp == null && b.pnl_gbp == null) return 0
    if (a.pnl_gbp == null) return 1
    if (b.pnl_gbp == null) return -1
    return a.pnl_gbp - b.pnl_gbp
  })

  const totalPnlGbp = totalValue - totalCost
  const totalPnlPct = totalCost > 0 ? (totalPnlGbp / totalCost) * 100 : null

  return {
    positions: enriched,
    totals: {
      portfolio_value_gbp: Math.round(totalValue * 100) / 100,
      total_cost_gbp: Math.round(totalCost * 100) / 100,
      total_pnl_gbp: Math.round(totalPnlGbp * 100) / 100,
      total_pnl_pct: totalPnlPct != null ? Math.round(totalPnlPct * 100) / 100 : null,
      positions_count: rows.length,
    },
    fx_rates: fxRates,
  }
}
