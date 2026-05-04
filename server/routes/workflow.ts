/**
 * GET /api/workflow — unified position lifecycle data for Kanban pipeline.
 *
 * Returns three stages:
 *   approved     — open DB positions with no exit plan yet
 *   holdings     — open positions with exit plan, no urgency signal
 *   pendingExit  — open positions with exit plan AND urgency signal
 *
 * hledger is the authoritative source for real holdings.
 * Only positions for platforms with actual hledger holdings are shown.
 * Empty hledger → empty workflow (clean, no phantom positions).
 *
 * Price cache: daily (expires at midnight UTC) — shared with exits.ts via ../lib/cache.ts.
 */
import { dirname, join } from "node:path"
import { Hono } from "hono"
import { DatabaseFactory } from "../lib/db.ts"
import { computeExitStatus, type ExitPlan, loadAllPlans } from "../lib/positions.ts"
import { priceCache, fetchPrice } from "../lib/cache.ts"
import { getHoldings } from "../lib/hledger.ts"

export const workflowRouter = new Hono()

function findProjectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT
  const projectRoot = dirname(dirname(import.meta.dir))
  if (projectRoot.includes("TradingAgents")) return projectRoot
  return projectRoot
}

workflowRouter.get("/", async (c) => {
  const db = DatabaseFactory.get()

  // hledger is the authoritative source for real holdings.
  // Only show positions for platforms that have actual hledger holdings.
  const { holdings: hlHoldings } = await getHoldings()
  const hledgerPlatforms = new Set<string>(["test"]) // always allow test platform (for dev)
  for (const h of hlHoldings) {
    hledgerPlatforms.add(h.platform)
  }

  const rawPositions = db
    .query(
      "SELECT id, ticker, exchange, platform, quantity, avg_cost, entry_date, thesis FROM positions WHERE status = 'open' ORDER BY ticker",
    )
    .all() as Array<{
    id: number; ticker: string; exchange: string; platform: string;
    quantity: number; avg_cost: number; entry_date: string; thesis: string;
  }>

  const openPositions = rawPositions.filter((p) => hledgerPlatforms.has(p.platform))

  // Load exit plans
  const plans = loadAllPlans()
  const planSet = new Set(plans.map((p: ExitPlan) => `${p.ticker}::${p.platform || "unknown"}`))

  // Fetch live prices for plan tickers (batched, 4 at a time)
  const uniqueTickers = [...new Set(plans.map((p: ExitPlan) => p.ticker))]
  const script = join(findProjectRoot(), "scripts", "get_price.py")
  const priceMap = new Map<string, number | null>()
  for (let i = 0; i < uniqueTickers.length; i += 4) {
    const batch = uniqueTickers.slice(i, i + 4)
    const results = await Promise.all(batch.map((t) => fetchPrice(t, script, findProjectRoot())))
    batch.forEach((t, idx) => void priceMap.set(t, results[idx] ?? null))
  }

  // Build exit statuses
  const exitStatuses = new Map<string, ReturnType<typeof computeExitStatus>>()
  for (const plan of plans) {
    const key = `${plan.ticker}::${plan.platform || "unknown"}`
    const currentPrice = priceMap.get(plan.ticker) ?? undefined
    exitStatuses.set(key, computeExitStatus(plan, currentPrice))
  }

  // APPROVED — open positions with no exit plan
  const approved = openPositions
    .filter((p) => !planSet.has(`${p.ticker}::${p.platform}`))
    .map((p) => ({
      id: p.id, ticker: p.ticker, exchange: p.exchange,
      platform: p.platform, quantity: p.quantity, avgCost: p.avg_cost,
      entryDate: p.entry_date, thesis: p.thesis,
    }))

  // HOLDINGS vs PENDING EXIT — split by urgency signal
  type ExitPlanData = {
    entryPrice: number; invalidationPrice: number; invalidationThesis: string;
    targets: unknown[]; timeStop: string | null;
    timeStopDaysLeft?: number; targetsHit: number; distanceToStopPct: number;
  }
  type PositionItem = {
    id: number; ticker: string; platform: string; quantity: number;
    avgCost: number; entryDate: string; thesis: string;
    exitPlan: ExitPlanData;
  }
  const holdings: PositionItem[] = []
  const pendingExit: PositionItem[] = []

  for (const p of openPositions) {
    if (!planSet.has(`${p.ticker}::${p.platform}`)) continue
    const key = `${p.ticker}::${p.platform}`
    const status = exitStatuses.get(key)
    const isUrgent = !!status && (
      status.distanceToStopPct < 15 ||
      (status.targetsHit ?? 0) > 0 ||
      (status.timeStopDaysLeft ?? 999) < 30
    )
    const item: PositionItem = {
      id: p.id, ticker: p.ticker, platform: p.platform,
      quantity: p.quantity, avgCost: p.avg_cost,
      entryDate: p.entry_date, thesis: p.thesis,
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

  // Empty hledger → explain the clean state
  const note =
    openPositions.length === 0 && rawPositions.length > 0
      ? "Portfolio appears empty — hledger has no real holdings. " +
        "Add positions to hledger to see them in the workflow."
      : openPositions.length === 0
      ? "No holdings in hledger. Portfolio is empty."
      : undefined

  return c.json({
    approved,
    holdings,
    pendingExit,
    hledgerPlatforms: [...hledgerPlatforms],
    note,
  })
})