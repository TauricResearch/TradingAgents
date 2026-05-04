/**
 * GET /api/portfolio/intelligence — unified portfolio view
 *
 * Fuses:
 *   - hledger cash balances (authoritative per-platform cash)
 *   - SQLite positions with live market prices + P&L
 *   - Governance rules (violations + rebalance suggestions)
 *
 * Returns:
 *   - total portfolio value (live prices)
 *   - cash by platform
 *   - positions by platform with live P&L
 *   - allocation breakdown (by platform, by asset class)
 *   - governance violations
 *   - cash % of portfolio
 */
import { Hono } from "hono"
import { getHoldings } from "../lib/hledger.ts"
import { DatabaseFactory } from "../lib/db.ts"
import { checkRules, suggestRebalance, loadRules } from "../lib/governance.ts"
import { priceCache, endOfToday } from "../lib/cache.ts"
import { spawn } from "node:child_process"
import { dirname, join } from "node:path"

export const intelligenceRouter = new Hono()

function findProjectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT
  const projectRoot = dirname(dirname(import.meta.dir))
  if (projectRoot.includes("TradingAgents")) return projectRoot
  return projectRoot
}

interface DbPosition {
  id: number
  ticker: string
  exchange: string
  platform: string
  quantity: number
  avg_cost: number
  entry_date: string
  thesis: string | null
}

interface PositionWithValue {
  id: number
  ticker: string
  exchange: string
  platform: string
  quantity: number
  avg_cost: number
  entry_date: string
  thesis: string | null
  current_price_gbp: number | null
  current_value_gbp: number | null
  cost_value_gbp: number
  pnl_gbp: number | null
  pnl_pct: number | null
  currency: string
}

interface CashBalance {
  platform: string
  currency: string
  amount: number
  amount_gbp: number
}

interface PriceResult { price: number | null; currency: string }

async function fetchPriceForTicker(ticker: string): Promise<PriceResult> {
  const now = Date.now()
  const cached = priceCache.get(ticker)
  if (cached && cached.expires > now && cached.price !== null) {
    return { price: cached.price, currency: "USD" }
  }

  return new Promise((resolve) => {
    const script = join(findProjectRoot(), "scripts", "get_price.py")
    const child = spawn("python3", [script, ticker], {
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      timeout: 12_000,
    })
    let stdout = ""
    child.stdout.on("data", (d: Buffer) => { stdout += d.toString() })
    child.on("close", () => {
      try {
        const data = JSON.parse(stdout.trim())
        if (data.price != null) {
          priceCache.set(ticker, { price: data.price, expires: endOfToday() })
        }
        resolve({ price: data.price ?? null, currency: data.currency ?? "USD" })
      } catch {
        resolve({ price: null, currency: "USD" })
      }
    })
    child.on("error", () => resolve({ price: null, currency: "USD" }))
  })
}

async function fetchPrices(tickers: string[]): Promise<Map<string, PriceResult>> {
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

// ── Asset classification helpers ─────────────────────────────────────────────

function classifyTicker(ticker: string, exchange: string): string {
  const t = ticker.toUpperCase()
  // ETFs
  if (t === "VWCE.DE" || t === "IWDA.L" || t === "CSPX.L" || t === "TERA.SW") return "etf"
  // Crypto
  if (exchange === "CRYPTO" || ["BTC", "ETH", "SOL", "XRP"].includes(t)) return "crypto"
  // Default: equity
  return "equity"
}

// ── Main endpoint ────────────────────────────────────────────────────────────

intelligenceRouter.get("/", async (c) => {
  try {
    // 1. Fetch hledger cash (authoritative per-platform cash balances)
    const { holdings: hlHoldings, cash: hlCash } = await getHoldings()

    // 2. Fetch SQLite positions
    const db = DatabaseFactory.get()
    const dbPositions = db.query(
      "SELECT id, ticker, exchange, platform, quantity, avg_cost, entry_date, thesis FROM positions WHERE status = 'open'",
    ).all() as DbPosition[]

    // 3. Compute live prices for all tickers + FX pairs
    const tickers = [...new Set(dbPositions.map((p) => p.ticker))]
    const fxPairs = ["GBPEUR=X", "GBPUSD=X"]
    const allNeeded = [...tickers, ...fxPairs]
    const prices = await fetchPrices(allNeeded)

    const gbpeur = prices.get("GBPEUR=X")?.price ?? 1.18
    const gbpUSD = prices.get("GBPUSD=X")?.price ?? 1.27
    const gbpPerEur = 1 / gbpeur
    const gbpPerUsd = 1 / gbpUSD

    // 4. Build cash balances (from hledger) with GBP conversion
    const cashByPlatform: Map<string, CashBalance[]> = new Map()
    for (const c of hlCash) {
      const list = cashByPlatform.get(c.platform) ?? []
      let amountGbp = c.amount
      if (c.currency === "EUR") amountGbp = c.amount * gbpPerEur
      else if (c.currency === "USD") amountGbp = c.amount * gbpPerUsd
      // GBP stays as-is
      list.push({ platform: c.platform, currency: c.currency, amount: c.amount, amount_gbp: amountGbp })
      cashByPlatform.set(c.platform, list)
    }

    const totalCashGbp = [...cashByPlatform.values()].flat().reduce((s, c) => s + c.amount_gbp, 0)

    // 5. Build positions with live values
    const positionsWithValue: PositionWithValue[] = dbPositions.map((p) => {
      const pd = prices.get(p.ticker)
      let currentPriceGbp: number | null = null
      if (pd?.price != null) {
        if (pd.currency === "EUR") currentPriceGbp = pd.price * gbpPerEur
        else if (pd.currency === "USD") currentPriceGbp = pd.price * gbpPerUsd
        else currentPriceGbp = pd.price
      }

      // Cost basis in GBP
      let costValueGbp = p.avg_cost * p.quantity
      if (p.exchange === "US") costValueGbp = (p.avg_cost * p.quantity) / gbpUSD
      else if (p.exchange === "XETRA" || p.exchange === "EUR") costValueGbp = (p.avg_cost * p.quantity) / gbpeur

      const currentValueGbp = currentPriceGbp != null ? currentPriceGbp * p.quantity : null
      const pnlGbp = currentValueGbp != null ? currentValueGbp - costValueGbp : null
      const pnlPct = costValueGbp > 0 && pnlGbp != null ? (pnlGbp / costValueGbp) * 100 : null

      return {
        ...p,
        current_price_gbp: currentPriceGbp != null ? Math.round(currentPriceGbp * 100) / 100 : null,
        current_value_gbp: currentValueGbp != null ? Math.round(currentValueGbp * 100) / 100 : null,
        cost_value_gbp: Math.round(costValueGbp * 100) / 100,
        pnl_gbp: pnlGbp != null ? Math.round(pnlGbp * 100) / 100 : null,
        pnl_pct: pnlPct != null ? Math.round(pnlPct * 100) / 100 : null,
        currency: pd?.currency ?? "GBP",
      }
    })

    // 6. Total portfolio value (positions at live price + cash in GBP)
    const totalPositionsValueGbp = positionsWithValue.reduce(
      (s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp),
      0,
    )
    const totalPortfolioGbp = totalPositionsValueGbp + totalCashGbp

    // Cash is negative when hledger shows more sells than buys (or data gaps).
    // For % calculations: use |totalPortfolioGbp| so weights are meaningful.
    const cashPctRaw = totalPortfolioGbp !== 0 ? (totalCashGbp / totalPortfolioGbp) * 100 : 0
    const cashPct = cashPctRaw // may be negative — view handles it
    const absPortfolioGbp = Math.abs(totalPortfolioGbp) // for % calculation safety

    // 8. Allocation by platform (current market value)
    const positionsByPlatform = new Map<string, PositionWithValue[]>()
    for (const p of positionsWithValue) {
      const list = positionsByPlatform.get(p.platform) ?? []
      list.push(p)
      positionsByPlatform.set(p.platform, list)
    }

    const cashByPlatformGbp = new Map<string, number>()
    for (const [platform, balances] of cashByPlatform) {
      cashByPlatformGbp.set(platform, balances.reduce((s, c) => s + c.amount_gbp, 0))
    }

    // Group by platform
    const allPlatforms = [
      ...new Set([...positionsByPlatform.keys(), ...cashByPlatformGbp.keys()]),
    ]

    const platformAllocations = allPlatforms.map((platform) => {
      const pos = positionsByPlatform.get(platform) ?? []
      const cashGbp = cashByPlatformGbp.get(platform) ?? 0
      const posValueGbp = pos.reduce((s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp), 0)
      const totalGbp = posValueGbp + cashGbp

      return {
        platform,
        positions: pos,
        cash_gbp: Math.round(cashGbp * 100) / 100,
        position_value_gbp: Math.round(posValueGbp * 100) / 100,
        total_value_gbp: Math.round(totalGbp * 100) / 100,
        weight_pct: absPortfolioGbp > 0 ? Math.round((totalGbp / absPortfolioGbp) * 10000) / 100 : 0,
        cash_pct: totalGbp > 0 ? Math.round((cashGbp / totalGbp) * 10000) / 100 : 0,
      }
    })

    // 9. Allocation by asset class
    const etfValueGbp = positionsWithValue
      .filter((p) => classifyTicker(p.ticker, p.exchange) === "etf")
      .reduce((s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp), 0)
    const equityValueGbp = positionsWithValue
      .filter((p) => classifyTicker(p.ticker, p.exchange) === "equity")
      .reduce((s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp), 0)
    const cryptoValueGbp = positionsWithValue
      .filter((p) => classifyTicker(p.ticker, p.exchange) === "crypto")
      .reduce((s, p) => s + (p.current_value_gbp ?? p.cost_value_gbp), 0)

    const assetClassAllocation = [
      { assetClass: "cash", value_gbp: Math.round(Math.abs(totalCashGbp) * 100) / 100, weight_pct: Math.abs(cashPct) },
      { assetClass: "equity", value_gbp: Math.round(equityValueGbp * 100) / 100, weight_pct: absPortfolioGbp > 0 ? Math.round((equityValueGbp / absPortfolioGbp) * 10000) / 100 : 0 },
      { assetClass: "etf", value_gbp: Math.round(etfValueGbp * 100) / 100, weight_pct: absPortfolioGbp > 0 ? Math.round((etfValueGbp / absPortfolioGbp) * 10000) / 100 : 0 },
      { assetClass: "crypto", value_gbp: Math.round(cryptoValueGbp * 100) / 100, weight_pct: absPortfolioGbp > 0 ? Math.round((cryptoValueGbp / absPortfolioGbp) * 10000) / 100 : 0 },
    ].filter((a) => a.value_gbp > 0)

    // 10. Governance check (per-platform)
    const rules = loadRules()
    const governanceByPlatform: Record<string, unknown> = {}

    for (const pa of platformAllocations) {
      const total = pa.total_value_gbp
      const allocations = pa.positions.map((p) => ({
        ticker: p.ticker,
        value: p.current_value_gbp ?? p.cost_value_gbp,
        weight: total > 0 ? ((p.current_value_gbp ?? p.cost_value_gbp) / total) * 100 : 0,
      }))
      const platformCashPct = pa.cash_pct
      const violations = checkRules(allocations, platformCashPct, total, total, rules)
      const suggestions = suggestRebalance(allocations, platformCashPct, rules)
      governanceByPlatform[pa.platform] = { violations, suggestions }
    }

    // 11. Overall governance (all platforms combined)
    const overallAllocations = positionsWithValue.map((p) => ({
      ticker: p.ticker,
      value: p.current_value_gbp ?? p.cost_value_gbp,
      weight: absPortfolioGbp > 0 ? ((p.current_value_gbp ?? p.cost_value_gbp) / absPortfolioGbp) * 100 : 0,
    }))
    const overallViolations = checkRules(overallAllocations, cashPct, totalPortfolioGbp, totalPortfolioGbp, rules)
    const overallSuggestions = suggestRebalance(overallAllocations, cashPct, rules)

    return c.json({
      portfolio: {
        total_value_gbp: Math.round(totalPortfolioGbp * 100) / 100,
        cash_gbp: Math.round(totalCashGbp * 100) / 100,
        cash_pct: Math.round(cashPct * 100) / 100,
        cash_pct_raw: Math.round(cashPctRaw * 100) / 100,
        cash_negative: totalCashGbp < 0,
        position_value_gbp: Math.round(totalPositionsValueGbp * 100) / 100,
        positions_count: positionsWithValue.length,
      },
      fx_rates: {
        GBPEUR: Math.round(gbpeur * 10000) / 10000,
        GBPUSD: Math.round(gbpUSD * 10000) / 10000,
      },
      platforms: platformAllocations.sort((a, b) => b.total_value_gbp - a.total_value_gbp),
      asset_classes: assetClassAllocation,
      governance: {
        violations: overallViolations,
        suggestions: overallSuggestions,
      },
      governance_by_platform: governanceByPlatform,
    })
  } catch (e: unknown) {
    return c.json(
      { error: "Portfolio intelligence failed", detail: (e as Error).message },
      500,
    )
  }
})