/** Data builder for workflow kanban — extracted from route for reuse. */
import { join } from "node:path"
import { DatabaseFactory } from "../../lib/db.ts"
import { fetchPrice } from "./cache.ts"
import { getHoldings } from "./hledger.ts"
import { computeExitStatus, type ExitPlan, loadAllPlans } from "./positions.ts"
import { findProjectRoot } from "./utils.ts"

export interface ExitPlanData {
  entryPrice: number
  invalidationPrice: number
  invalidationThesis: string
  targets: unknown[]
  timeStop: string | null
  timeStopDaysLeft?: number
  targetsHit: number
  distanceToStopPct: number
}

interface WorkflowBaseItem {
  id: number
  ticker: string
  platform: string
  quantity: number
  avgCost: number
  entryDate: string
  thesis: string | null
}

export interface WorkflowApprovedItem extends WorkflowBaseItem {}

export interface WorkflowHoldingItem extends WorkflowBaseItem {
  exitPlan: ExitPlanData
}

export interface WorkflowPendingExitItem extends WorkflowBaseItem {
  exitPlan: ExitPlanData
}

export interface WorkflowData {
  approved: WorkflowApprovedItem[]
  holdings: WorkflowHoldingItem[]
  pendingExit: WorkflowPendingExitItem[]
  hledgerPlatforms: string[]
  note?: string
}

export async function buildWorkflowData(): Promise<WorkflowData> {
  const db = DatabaseFactory.get()

  // hledger is the authoritative source for real holdings.
  const { holdings: hlHoldings } = await getHoldings()
  const hledgerPlatforms = new Set<string>(["test"])
  for (const h of hlHoldings) {
    hledgerPlatforms.add(h.platform)
  }

  const rawPositions = db
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

  const openPositions = rawPositions.filter((p) => hledgerPlatforms.has(p.platform))

  // Load exit plans
  const plans = loadAllPlans()
  const planSet = new Set(plans.map((p: ExitPlan) => `${p.ticker}::${p.platform || "unknown"}`))

  // Fetch live prices for plan tickers (batched, 4 at a time)
  const uniqueTickers = [...new Set(plans.map((p: ExitPlan) => p.ticker))]
  const script = join(findProjectRoot(), "scripts", "py", "get_price.py")
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
  const approved: WorkflowApprovedItem[] = openPositions
    .filter((p) => !planSet.has(`${p.ticker}::${p.platform}`))
    .map((p) => ({
      id: p.id,
      ticker: p.ticker,
      platform: p.platform,
      quantity: p.quantity,
      avgCost: parseFloat(String(p.avg_cost)),
      entryDate: p.entry_date,
      thesis: p.thesis,
    }))

  // HOLDINGS vs PENDING EXIT — split by urgency signal
  const holdings: WorkflowHoldingItem[] = []
  const pendingExit: WorkflowPendingExitItem[] = []

  for (const p of openPositions) {
    if (!planSet.has(`${p.ticker}::${p.platform}`)) continue
    const key = `${p.ticker}::${p.platform}`
    const status = exitStatuses.get(key)
    const isUrgent =
      !!status &&
      (status.distanceToStopPct < 15 ||
        (status.targetsHit ?? 0) > 0 ||
        (status.timeStopDaysLeft ?? 999) < 30)

    const exitPlan: ExitPlanData = {
      entryPrice: status?.plan.entry_price ?? p.avg_cost,
      invalidationPrice: status?.plan.invalidation?.price ?? 0,
      invalidationThesis: status?.plan.invalidation?.thesis ?? "",
      targets: status?.plan.targets ?? [],
      timeStop: status?.plan.time_stop ?? null,
      timeStopDaysLeft: status?.timeStopDaysLeft,
      targetsHit: status?.targetsHit ?? 0,
      distanceToStopPct: status?.distanceToStopPct ?? 0,
    }

    const item = {
      id: p.id,
      ticker: p.ticker,
      platform: p.platform,
      quantity: p.quantity,
      avgCost: parseFloat(String(p.avg_cost)),
      entryDate: p.entry_date,
      thesis: p.thesis,
      exitPlan,
    }

    if (isUrgent) pendingExit.push(item)
    else holdings.push(item)
  }

  const note =
    openPositions.length === 0 && rawPositions.length > 0
      ? "Portfolio appears empty — hledger has no real holdings. Add positions to hledger to see them in the workflow."
      : openPositions.length === 0
        ? "No holdings in hledger. Portfolio is empty."
        : undefined

  return {
    approved,
    holdings,
    pendingExit,
    hledgerPlatforms: [...hledgerPlatforms],
    note,
  }
}
