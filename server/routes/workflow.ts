/**
 * GET /api/workflow — unified position lifecycle data for Kanban pipeline.
 *
 * Returns three stages:
 *   approved     — open DB positions with no exit plan yet
 *   holdings     — open positions with exit plan, no urgency signal
 *   pendingExit  — open positions with exit plan AND urgency signal
 */
import { spawn } from "node:child_process"
import { dirname, join } from "node:path"
import { Hono } from "hono"
import { DatabaseFactory } from "../lib/db.ts"
import { computeExitStatus, type ExitPlan, loadAllPlans } from "../lib/positions.ts"

export const workflowRouter = new Hono()

// ── Price cache (shared with exits.ts) ───────────────────────────────────────

const priceCache = new Map<string, { price: number | null; expires: number }>()

function fetchPrice(ticker: string): Promise<number | null> {
  return new Promise((resolve) => {
    const now = Date.now()
    const cached = priceCache.get(ticker)
    if (cached && cached.expires > now) {
      resolve(cached.price)
      return
    }

    const root = (() => {
      if (process.env.TA_ROOT) return process.env.TA_ROOT
      const p = dirname(dirname(import.meta.dir))
      return p.includes("TradingAgents") ? p : p
    })()
    const child = spawn("python3", [join(root, "scripts", "get_price.py"), ticker], {
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    })
    let resolved = false
    const finish = (price: number | null) => {
      if (resolved) return
      resolved = true
      child.kill()
      priceCache.set(ticker, { price, expires: now + 60_000 })
      resolve(price)
    }
    let stdout = ""
    child.stdout.on("data", (d: Buffer) => {
      stdout += d.toString()
    })
    setTimeout(() => finish(null), 8_000)
    child.on("close", (code) => {
      if (code !== 0) {
        finish(null)
        return
      }
      try {
        const data = JSON.parse(stdout.trim())
        finish(data.price ?? null)
      } catch {
        finish(null)
      }
    })
    child.on("error", () => finish(null))
  })
}

workflowRouter.get("/", async (c) => {
  const db = DatabaseFactory.get()

  const openPositions = db
    .query(
      "SELECT id, ticker, exchange, platform, quantity, avg_cost, entry_date, thesis FROM positions WHERE status = 'open' ORDER BY ticker",
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
  }>

  const plans = loadAllPlans()
  const planSet = new Set(plans.map((p: ExitPlan) => `${p.ticker}::${p.platform || "unknown"}`))

  // Fetch live prices for all unique tickers (batched, 4 at a time)
  const uniqueTickers = [...new Set(plans.map((p: ExitPlan) => p.ticker))]
  const priceMap = new Map<string, number | null>()
  for (let i = 0; i < uniqueTickers.length; i += 4) {
    const batch = uniqueTickers.slice(i, i + 4)
    const results = await Promise.all(batch.map((t) => fetchPrice(t)))
    batch.forEach((t, idx) => void priceMap.set(t, results[idx] ?? null))
  }

  // Build exit statuses with live prices
  const exitStatuses = new Map<string, ReturnType<typeof computeExitStatus>>()
  for (const plan of plans) {
    const key = `${plan.ticker}::${plan.platform || "unknown"}`
    const currentPrice = priceMap.get(plan.ticker) ?? undefined
    exitStatuses.set(key, computeExitStatus(plan, currentPrice))
  }

  // APPROVED
  const approved = openPositions
    .filter((p) => !planSet.has(`${p.ticker}::${p.platform}`))
    .map((p) => ({
      id: p.id,
      ticker: p.ticker,
      exchange: p.exchange,
      platform: p.platform,
      quantity: p.quantity,
      avgCost: p.avg_cost,
      entryDate: p.entry_date,
      thesis: p.thesis,
    }))

  // HOLDINGS vs PENDING EXIT (split by urgency signal)
  type ExitPlanData = {
    entryPrice: number
    invalidationPrice: number
    invalidationThesis: string
    targets: unknown[]
    timeStop: string | null
    timeStopDaysLeft?: number
    targetsHit: number
    distanceToStopPct: number
  }
  type PositionItem = {
    id: number
    ticker: string
    platform: string
    quantity: number
    avgCost: number
    entryDate: string
    thesis: string
    exitPlan: ExitPlanData
  }
  const holdings: PositionItem[] = []
  const pendingExit: PositionItem[] = []

  for (const p of openPositions) {
    if (!planSet.has(`${p.ticker}::${p.platform}`)) continue
    const key = `${p.ticker}::${p.platform}`
    const status = exitStatuses.get(key)
    const isUrgent =
      !!status &&
      (status.distanceToStopPct < 15 ||
        (status.targetsHit ?? 0) > 0 ||
        (status.timeStopDaysLeft ?? 999) < 30)
    const item: PositionItem = {
      id: p.id,
      ticker: p.ticker,
      platform: p.platform,
      quantity: p.quantity,
      avgCost: p.avg_cost,
      entryDate: p.entry_date,
      thesis: p.thesis,
      exitPlan: {
        entryPrice: status?.plan.entry_price ?? p.avg_cost,
        invalidationPrice: status?.plan.invalidation?.price ?? 0,
        invalidationThesis: status?.plan.invalidation?.thesis ?? "",
        targets: status?.plan.targets ?? [],
        timeStop: status?.plan.time_stop ?? null,
        timeStopDaysLeft: status?.timeStopDaysLeft,
        targetsHit: status?.targetsHit ?? 0,
        distanceToStopPct: status?.distanceToStopPct ?? 0,
      },
    }
    if (isUrgent) pendingExit.push(item)
    else holdings.push(item)
  }

  return c.json({ approved, holdings, pendingExit })
})
