import { Hono, Context } from "hono"
import { DatabaseFactory } from "../lib/db.ts"
import { sanitizeForDb } from "../lib/sanitize.ts"
import { priceCache, endOfToday } from "../lib/cache.ts"
import { join, dirname } from "node:path"
import { spawn } from "node:child_process"

export const portfolioRouter = new Hono()

function findProjectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT
  const projectRoot = dirname(dirname(import.meta.dir))
  if (projectRoot.includes("TradingAgents")) return projectRoot
  return projectRoot
}

// ── Positions CRUD ────────────────────────────────────────────────────────────

/** GET /api/positions — list all open positions, optionally filter by platform */
portfolioRouter.get("/", (c) => {
  const db = DatabaseFactory.get()
  const platform = c.req.query("platform")
  if (platform) {
    const rows = db
      .query("SELECT * FROM positions WHERE status = 'open' AND platform = ? ORDER BY ticker")
      .all(platform)
    return c.json(rows)
  }
  const rows = db.query("SELECT * FROM positions WHERE status = 'open' ORDER BY ticker").all()
  return c.json(rows)
})

/** POST /api/positions — add a new position */
portfolioRouter.post("/", async (c) => {
  const db = DatabaseFactory.get()
  const body = await c.req.json()
  const { ticker, exchange, platform, quantity, avg_cost, entry_date, thesis, notes } = body
  if (!ticker || quantity == null || avg_cost == null) {
    return c.json({ error: "ticker, quantity, avg_cost required" }, 400)
  }
  const stmt = db.prepare(
    `INSERT INTO positions (ticker, exchange, platform, quantity, avg_cost, entry_date, thesis, notes)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  )
  const result = stmt.run(
    ticker,
    exchange ?? "US",
    platform ?? "unknown",
    quantity,
    avg_cost,
    entry_date ?? new Date().toISOString().slice(0, 10),
    sanitizeForDb(thesis) ?? null,
    sanitizeForDb(notes) ?? null,
  )
  return c.json(
    {
      id: result.lastInsertRowid,
      ticker,
      exchange: exchange ?? "US",
      platform: platform ?? "unknown",
      quantity,
      avg_cost,
    },
    201,
  )
})

/** DELETE /api/positions/:id — close a position */
portfolioRouter.delete("/:id", (c) => {
  const db = DatabaseFactory.get()
  const id = c.req.param("id")
  const stmt = db.prepare("UPDATE positions SET status = 'closed' WHERE id = ?")
  const result = stmt.run(id)
  if (result.changes === 0) {
    return c.json({ error: "position not found" }, 404)
  }
  return c.json({ status: "closed", id })
})

// ── Portfolio P&L summary ─────────────────────────────────────────────────────

interface PriceData {
  price: number | null
  currency: string
}

interface PositionEnriched {
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
}

interface PortfolioSummary {
  positions: PositionEnriched[]
  totals: {
    portfolio_value_gbp: number | null
    total_cost_gbp: number | null
    total_pnl_gbp: number | null
    total_pnl_pct: number | null
    positions_count: number
  }
  fx_rates: Record<string, number> // e.g. { GBPEUR: 1.18, GBPUSD: 1.27 }
}

/**
 * Standalone portfolio summary handler — mounted at GET /api/portfolio/summary in index.tsx.
 * Separated from portfolioRouter (which is mounted at /api/positions) to keep URLs clean.
 */
export async function handlePortfolioSummary(c: Context): Promise<Response> {
  const db = DatabaseFactory.get()
  const rows = db.query("SELECT * FROM positions WHERE status = 'open' ORDER BY ticker").all() as Array<{
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
    return c.json({ positions: [], totals: { portfolio_value_gbp: 0, total_cost_gbp: 0, total_pnl_gbp: 0, total_pnl_pct: null, positions_count: 0 }, fx_rates: {} })
  }

  // Unique tickers + FX pairs needed
  const tickers = [...new Set(rows.map((r) => r.ticker))]
  const fxPairs = ["GBPEUR=X", "GBPUSD=X", "GBPEUR", "GBPUSD"]
  const allTickers = [...tickers, ...fxPairs]

  // Batch fetch using prices batch endpoint logic (inline to avoid circular deps)
  const priceResults = await batchFetchPrices(allTickers)

  // Build FX rate map
  const fxRates: Record<string, number> = {}
  for (const fx of fxPairs) {
    const data = priceResults.get(fx)
    if (data?.price != null) {
      // yfinance FX pairs: e.g. GBPEUR=X gives EUR per GBP
      // 1 GBP = data.price EUR  → GBPEUR rate = data.price
      const key = fx.replace("=X", "").replace("=", "")
      fxRates[key] = data.price
    }
  }

  // Default rates if FX lookups failed (rough estimates)
  if (!fxRates["GBPEUR"]) fxRates["GBPEUR"] = 1.18
  if (!fxRates["GBPUSD"]) fxRates["GBPUSD"] = 1.27

  const gbpPerEur = 1 / fxRates["GBPEUR"] // 1 EUR = X GBP
  const gbpPerUsd = 1 / fxRates["GBPUSD"] // 1 USD = X GBP

  // Enrich each position
  let totalValue = 0
  let totalCost = 0

  const enriched: PositionEnriched[] = rows.map((p) => {
    const priceData = priceResults.get(p.ticker)
    let currentPriceGbp: number | null = null

    if (priceData?.price != null) {
      const rawPrice = priceData.price
      if (priceData.currency === "EUR") {
        currentPriceGbp = rawPrice * gbpPerEur
      } else if (priceData.currency === "USD") {
        currentPriceGbp = rawPrice * gbpPerUsd
      } else {
        // Treat as GBP
        currentPriceGbp = rawPrice
      }
    }

    // All costs stored in GBP (base currency).
    // If cost was entered in EUR or USD, it should already be converted to GBP at entry time.
    // For seed data that stored native currency: apply same FX conversion as current price.
    // Default: treat as GBP (no conversion).
    const quantity = p.quantity
    let costValueGbp = p.avg_cost * quantity
    if (p.exchange === "US" && fxRates["GBPUSD"]) {
      // USD cost basis — convert to GBP
      costValueGbp = (p.avg_cost * quantity) / fxRates["GBPUSD"]
    } else if ((p.exchange === "XETRA" || p.exchange === "EUR") && fxRates["GBPEUR"]) {
      // EUR cost basis — convert to GBP
      costValueGbp = (p.avg_cost * quantity) / fxRates["GBPEUR"]
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
    }
  })

  // Sort by P&L ascending (worst first, nulls at end)
  enriched.sort((a, b) => {
    if (a.pnl_gbp == null && b.pnl_gbp == null) return 0
    if (a.pnl_gbp == null) return 1
    if (b.pnl_gbp == null) return -1
    return a.pnl_gbp - b.pnl_gbp
  })

  const totalPnlGbp = totalValue - totalCost
  const totalPnlPct = totalCost > 0 ? (totalPnlGbp / totalCost) * 100 : null

  const summary: PortfolioSummary = {
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

  return c.json(summary)
}

// ── Batch price helper (inline to avoid circular imports) ─────────────────────

async function batchFetchPrices(
  tickers: string[],
): Promise<Map<string, PriceData>> {
  const results = new Map<string, PriceData>()
  const root = findProjectRoot()
  const script = join(root, "scripts", "get_price.py")

  // Fetch in parallel, one at a time (yfinance is the bottleneck)
  const fetches = tickers.map(
    (ticker) =>
      new Promise<[string, PriceData]>((resolve) => {
        // Check cache first
        const cached = priceCache.get(ticker)
        const now = Date.now()
        if (cached && cached.expires > now) {
          resolve([ticker, { price: cached.price, currency: "USD" }])
          return
        }

        const child = spawn("python3", [script, ticker], {
          env: { ...process.env, PYTHONUNBUFFERED: "1" },
          timeout: 12_000,
        })

        let stdout = ""
        child.stdout.on("data", (d: Buffer) => { stdout += d.toString() })
        child.on("close", (_code) => {
          try {
            const data = JSON.parse(stdout.trim())
            const price = data.price ?? null
            const currency = data.currency ?? "USD"
            if (price != null) {
              priceCache.set(ticker, { price, expires: endOfToday() })
            }
            resolve([ticker, { price, currency }])
          } catch {
            resolve([ticker, { price: null, currency: "USD" }])
          }
        })
        child.on("error", () => resolve([ticker, { price: null, currency: "USD" }]))
      }),
  )

  const settled = await Promise.all(fetches)
  for (const [ticker, data] of settled) {
    results.set(ticker, data)
  }
  return results
}