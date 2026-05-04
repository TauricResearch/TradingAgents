import { Hono } from "hono"
import { DatabaseFactory } from "../lib/db.ts"
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
        id: number; ticker: string; exchange: string; platform: string;
        quantity: number; avg_cost: number; entry_date: string; thesis: string; status: string;
      }>

    // Batch-load exit plans
    const exitPlans = new Map<string, {
      price: number; thesis: string; time_stop: string;
      targets: Array<{ price: number }>;
    }>()
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
      // Latest price
      const latestRow = db
        .query(`SELECT close, date FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1`)
        .get(p.ticker) as { close: number; date: string } | undefined

      const currentPrice = latestRow?.close ?? null
      const lastPriceDate = latestRow?.date ?? null

      // Sparkline: sample up to 20 points evenly across available bars
      const allBars = db
        .query(`SELECT date, close FROM prices WHERE ticker = ? ORDER BY date ASC`)
        .all(p.ticker) as Array<{ date: string; close: number }>

      const SPARK_POINTS = 20
      let sparkline: number[] = []
      if (allBars.length > 0) {
        const step = Math.max(1, Math.floor(allBars.length / SPARK_POINTS))
        for (let i = 0; i < Math.min(SPARK_POINTS, allBars.length); i++) {
          sparkline.push(allBars[Math.min(i * step, allBars.length - 1)]!.close)
        }
      }

      // P&L
      const costBasis = p.avg_cost * p.quantity
      const currentValue = currentPrice !== null ? currentPrice * p.quantity : null
      const pnl = currentValue !== null ? currentValue - costBasis : null
      const pnlPct = costBasis > 0 && currentValue !== null
        ? ((currentValue - costBasis) / costBasis) * 100
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
        quantity: p.quantity,
        avgCost: p.avg_cost,
        costBasis,
        entryDate: p.entry_date,
        currentPrice,
        currentValue,
        pnl,
        pnlPct,
        sparkline: sparkline.length > 0 ? sparkline : null,
        invalidationPrice,
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