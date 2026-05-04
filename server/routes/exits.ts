/**
 * GET /api/positions/exits — exit status for all planned positions
 *
 * Fetches live prices for each ticker, then computes exit status
 * (P&L, distance to stop, distance to targets).
 *
 * Price cache: daily (expires at midnight UTC) — one fetch per ticker per calendar day.
 * Response cache: 30s — avoids recomputing when multiple routes hit simultaneously.
 */
import { dirname, join } from "node:path"
import { Hono } from "hono"
import { computeExitStatus, type ExitPlan, loadAllPlans } from "../lib/positions.ts"
import { priceCache, fetchPrice, endOfToday } from "../lib/cache.ts"

export const exitsRouter = new Hono()

function findProjectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT
  const projectRoot = dirname(dirname(import.meta.dir))
  if (projectRoot.includes("TradingAgents")) return projectRoot
  return projectRoot
}

// Response-level cache — full exit statuses valid for 30s
let responseCache: { statuses: unknown[]; expires: number } | null = null

exitsRouter.get("/", async (c) => {
  const now = Date.now()

  // Serve from response cache if fresh
  if (responseCache && responseCache.expires > now) {
    return c.json(responseCache.statuses)
  }

  const plans = loadAllPlans()
  const unique = [...new Set(plans.map((p: ExitPlan) => p.ticker))]
  const script = join(findProjectRoot(), "scripts", "get_price.py")

  // Fetch in parallel batches (4 at a time) — keeps total time under ~40s on first load
  const BATCH_SIZE = 4
  const priceMap = new Map<string, number | null>()
  for (let i = 0; i < unique.length; i += BATCH_SIZE) {
    const batch = unique.slice(i, i + BATCH_SIZE)
    const results = await Promise.all(batch.map((t) => fetchPrice(t, script, findProjectRoot())))
    batch.forEach((ticker, idx) => void priceMap.set(ticker, results[idx] ?? null))
  }

  const statuses = plans.map((plan: ExitPlan) => {
    const currentPrice = priceMap.get(plan.ticker) ?? undefined
    return computeExitStatus(plan, currentPrice)
  })

  // Cache for 30s
  responseCache = { statuses, expires: now + 30_000 }
  return c.json(statuses)
})