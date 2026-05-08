/** @jsxImportSource hono/jsx */

import { Hono } from "hono"
import { PositionsTable } from "../views/holdings.tsx"
import { DatabaseFactory } from "../../lib/db.ts"
import { getAllocation, getHoldings, getPrices } from "../lib/hledger.ts"
import { loadPlan } from "../lib/positions.ts"

export const holdingsRouter = new Hono()

/** GET /api/holdings — current holdings from hLedger */
holdingsRouter.get("/", async (c) => {
  try {
    const result = await getHoldings()
    return c.json(result)
  } catch (e: unknown) {
    return c.json(
      {
        error: "hLedger error",
        detail: (e as Error).message,
        hint: "Check HLEDGER_FILE env var and journal file syntax",
      },
      500,
    )
  }
})

/** GET /api/holdings/prices — price history from hLedger */
holdingsRouter.get("/prices", async (c) => {
  try {
    const prices = await getPrices()
    return c.json(prices)
  } catch (e: unknown) {
    return c.json(
      {
        error: "hLedger error",
        detail: (e as Error).message,
      },
      500,
    )
  }
})

/** GET /api/holdings/allocation — allocation tree (human-readable) */
holdingsRouter.get("/allocation", async (c) => {
  try {
    const text = await getAllocation()
    return c.text(text)
  } catch (e: unknown) {
    return c.json(
      {
        error: "hLedger error",
        detail: (e as Error).message,
      },
      500,
    )
  }
})

/** GET /api/holdings/positions — positions with prices, sparklines, stop monitoring
 *
 * Reads open positions from the prices table (SQLite) and enriches with:
 * - Current price (latest close from prices table)
 * - Sparkline: 20 points spread evenly across all available bars
 * - Exit plan data (invalidation_price, targets, time_stop)
 * - Stop status indicator (safe/watch/danger)
 * - P&L vs cost basis
 * - Freshness badge (last price date)
 *
 * Sorted by urgency: danger first, then watch, then safe.
 */
holdingsRouter.get("/positions", async (c) => {
  try {
    const db = DatabaseFactory.get()

    // Load all open positions (from SQLite — seeded by seed_database.ts)
    const positions = db
      .query(
        `SELECT id, ticker, exchange, platform, quantity, avg_cost, entry_date, thesis, status
         FROM positions
         WHERE status = 'open'
         ORDER BY platform, ticker`,
      )
      .all() as Array<{
      id: number
      ticker: string
      exchange: string
      platform: string
      quantity: number
      avg_cost: number
      entry_date: string
      thesis: string
      status: string
    }>

    // Batch-load exit plans
    const exitPlans = new Map<
      string,
      {
        price: number
        thesis: string
        time_stop: string
        targets: Array<{ price: number }>
      }
    >()
    for (const p of positions) {
      const plan = loadPlan(p.ticker, p.platform)
      if (plan) {
        const inv = plan.invalidation
        const flat = plan as unknown as { [key: string]: unknown }
        exitPlans.set(`${p.ticker}:${p.platform}`, {
          price: inv?.price ?? (flat.invalidation_price as number | undefined) ?? 0,
          thesis: inv?.thesis ?? (flat.invalidation_thesis as string | undefined) ?? "",
          time_stop: plan.time_stop ?? "",
          targets: plan.targets ?? [],
        })
      }
    }

    type StopLevel = "danger" | "watch" | "safe" | "no-price"
    const STOP_ORDER: Record<StopLevel, number> = { danger: 0, watch: 1, safe: 2, "no-price": 3 }

    const enriched = positions.map((p) => {
      // Latest price + currency + gbp_rate (stored at sync time)
      const latestRow = db
        .query(
          `SELECT close, date, currency, gbp_rate FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1`,
        )
        .get(p.ticker) as
        | { close: number; date: string; currency: string; gbp_rate: number | null }
        | undefined

      const currentPrice = latestRow?.close ?? null
      const currency = latestRow?.currency ?? "USD"
      const gbpRate = latestRow?.gbp_rate ?? 1 // default to 1 (no conversion)
      const lastPriceDate = latestRow?.date ?? null

      // Sparkline: sample up to 20 points evenly across available bars
      const allBars = db
        .query(`SELECT date, close FROM prices WHERE ticker = ? ORDER BY date ASC`)
        .all(p.ticker) as Array<{ date: string; close: number }>

      const SPARK_POINTS = 20
      const sparkline: number[] = []
      if (allBars.length > 0) {
        const step = Math.max(1, Math.floor(allBars.length / SPARK_POINTS))
        for (let i = 0; i < SPARK_POINTS && i * step < allBars.length; i++) {
          sparkline.push(allBars[i * step]?.close ?? 0)
        }
      }

      // All financial values pre-converted to GBP using stored gbp_rate
      const avgCostNum = parseFloat(String(p.avg_cost))
      const quantityNum = parseFloat(String(p.quantity))
      const costBasisGbp = avgCostNum * quantityNum * gbpRate
      const currentPriceGbp = currentPrice !== null ? currentPrice * gbpRate : null
      const currentValueGbp = currentPriceGbp !== null ? currentPriceGbp * quantityNum : null
      const pnlGbp = currentValueGbp !== null ? currentValueGbp - costBasisGbp : null
      const pnlPctGbp =
        costBasisGbp > 0 && currentValueGbp !== null
          ? ((currentValueGbp - costBasisGbp) / costBasisGbp) * 100
          : null

      // Stop status
      const exitPlan = exitPlans.get(`${p.ticker}:${p.platform}`)
      const invalidationPrice = exitPlan?.price ?? null

      let stopLevel: StopLevel = "no-price"
      if (currentPrice !== null && invalidationPrice !== null && invalidationPrice > 0) {
        const pctAbove = ((currentPrice - invalidationPrice) / currentPrice) * 100
        if (pctAbove < 5) stopLevel = "danger"
        else if (pctAbove < 20) stopLevel = "watch"
        else stopLevel = "safe"
      }

      return {
        id: p.id,
        ticker: p.ticker,
        exchange: p.exchange,
        platform: p.platform,
        quantity: quantityNum,
        avgCost: avgCostNum,
        avgCostGbp: Math.round(costBasisGbp * 100) / 100,
        costBasisGbp: Math.round(costBasisGbp * 100) / 100,
        entryDate: p.entry_date,
        currentPrice: currentPriceGbp, // GBP
        currency,
        gbpRate, // conversion factor (for reference)
        currentValue: currentValueGbp !== null ? Math.round(currentValueGbp * 100) / 100 : null, // GBP
        pnlGbp: pnlGbp !== null ? Math.round(pnlGbp * 100) / 100 : null, // GBP
        pnlPct: pnlPctGbp, // percentage in GBP terms
        sparkline: sparkline.length > 0 ? sparkline : null,
        invalidationPrice: Math.round((invalidationPrice ?? 0) * gbpRate * 100) / 100 || null, // GBP
        stopLevel,
        lastPriceDate,
        timeStop: exitPlan?.time_stop ?? null,
        targets: (exitPlan?.targets ?? []) as Array<{ price: number }>,
      }
    })

    // Sort: danger → watch → safe → no-price; secondary sort by worst P&L
    enriched.sort((a, b) => {
      const orderDiff = STOP_ORDER[a.stopLevel] - STOP_ORDER[b.stopLevel]
      if (orderDiff !== 0) return orderDiff
      return (a.pnlPct ?? 0) - (b.pnlPct ?? 0)
    })

    return c.json({ positions: enriched })
  } catch (e: unknown) {
    return c.json(
      {
        error: "Failed to load positions",
        detail: (e as Error).message,
        hint: "Check PORTFOLIO_DB or TEST_MODE=1",
      },
      500,
    )
  }
})

// ── HTML partial for HTMX refresh ──────────────────────────────────────────────

/** GET /api/holdings/positions/html — positions table as HTML for HTMX swap */
holdingsRouter.get("/positions/html", async (c) => {
  try {
    const db = DatabaseFactory.get()

    const positions = db
      .query(
        `SELECT id, ticker, exchange, platform, quantity, avg_cost, entry_date, thesis, status
         FROM positions WHERE status = 'open' ORDER BY platform, ticker`,
      )
      .all() as Array<{
        id: number; ticker: string; exchange: string; platform: string;
        quantity: number; avg_cost: number; entry_date: string; thesis: string; status: string
      }>

    const exitPlans = new Map<string, { price: number; thesis: string; time_stop: string; targets: Array<{ price: number }> }>()
    for (const p of positions) {
      const plan = loadPlan(p.ticker, p.platform)
      if (plan) {
        const inv = plan.invalidation
        const flat = plan as unknown as Record<string, unknown>
        exitPlans.set(`${p.ticker}:${p.platform}`, {
          price: inv?.price ?? (flat.invalidation_price as number | undefined) ?? 0,
          thesis: inv?.thesis ?? (flat.invalidation_thesis as string | undefined) ?? "",
          time_stop: plan.time_stop ?? "",
          targets: plan.targets ?? [],
        })
      }
    }

    type StopLevel = "danger" | "watch" | "safe" | "no-price"
    const STOP_ORDER: Record<StopLevel, number> = { danger: 0, watch: 1, safe: 2, "no-price": 3 }

    const enriched = positions.map((p) => {
      const latestRow = db
        .query(`SELECT close, date, currency, gbp_rate FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1`)
        .get(p.ticker) as { close: number; date: string; currency: string; gbp_rate: number | null } | undefined

      const currentPrice = latestRow?.close ?? null
      const gbpRate = latestRow?.gbp_rate ?? 1
      const lastPriceDate = latestRow?.date ?? null

      const allBars = db
        .query(`SELECT date, close FROM prices WHERE ticker = ? ORDER BY date ASC`)
        .all(p.ticker) as Array<{ date: string; close: number }>

      const SPARK_POINTS = 20
      const sparkline: number[] = []
      if (allBars.length > 0) {
        const step = Math.max(1, Math.floor(allBars.length / SPARK_POINTS))
        for (let i = 0; i < SPARK_POINTS && i * step < allBars.length; i++) {
          sparkline.push(allBars[i * step]?.close ?? 0)
        }
      }

      const avgCostNum = parseFloat(String(p.avg_cost))
      const quantityNum = parseFloat(String(p.quantity))
      const costBasisGbp = avgCostNum * quantityNum * gbpRate
      const currentPriceGbp = currentPrice !== null ? currentPrice * gbpRate : null
      const currentValueGbp = currentPriceGbp !== null ? currentPriceGbp * quantityNum : null
      const pnlGbp = currentValueGbp !== null ? currentValueGbp - costBasisGbp : null
      const pnlPctGbp = costBasisGbp > 0 && currentValueGbp !== null ? ((currentValueGbp - costBasisGbp) / costBasisGbp) * 100 : null

      const exitPlan = exitPlans.get(`${p.ticker}:${p.platform}`)
      const invalidationPrice = exitPlan?.price ?? null

      let stopLevel: StopLevel = "no-price"
      if (currentPrice !== null && invalidationPrice !== null && invalidationPrice > 0) {
        const pctAbove = ((currentPrice - invalidationPrice) / currentPrice) * 100
        if (pctAbove < 5) stopLevel = "danger"
        else if (pctAbove < 20) stopLevel = "watch"
        else stopLevel = "safe"
      }

      return {
        ticker: p.ticker,
        platform: p.platform,
        quantity: quantityNum,
        avgCost: avgCostNum,
        currentPrice: currentPriceGbp !== null ? Math.round(currentPriceGbp * 100) / 100 : null,
        currentValue: currentValueGbp !== null ? Math.round(currentValueGbp * 100) / 100 : null,
        pnlPct: pnlPctGbp,
        sparkline: sparkline.length > 0 ? sparkline : null,
        stopLevel,
        lastPriceDate,
        invalidationPrice: invalidationPrice !== null ? Math.round(invalidationPrice * gbpRate * 100) / 100 : null,
      }
    })

    enriched.sort((a, b) => {
      const orderDiff = STOP_ORDER[a.stopLevel] - STOP_ORDER[b.stopLevel]
      if (orderDiff !== 0) return orderDiff
      return (a.pnlPct ?? 0) - (b.pnlPct ?? 0)
    })

    return c.html(<PositionsTable positions={enriched} />)
  } catch (e: unknown) {
    return c.html(
      <div class="error-card">
        <strong>Positions error</strong>
        <br />{(e as Error).message}
      </div>,
      500,
    )
  }
})
