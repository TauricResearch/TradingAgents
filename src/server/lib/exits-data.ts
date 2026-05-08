/** Exit status data builder — extracted from route for reuse. */
import { join } from "node:path"
import { fetchPrice } from "./cache.ts"
import { computeExitStatus, type ExitPlan, type ExitStatus, loadAllPlans } from "./positions.ts"
import { findProjectRoot } from "./utils.ts"

// Response-level cache — full exit statuses valid for 30s
let responseCache: { statuses: ExitStatus[]; expires: number } | null = null

export async function buildExitStatuses(): Promise<ExitStatus[]> {
  const now = Date.now()

  // Serve from response cache if fresh
  if (responseCache && responseCache.expires > now) {
    return responseCache.statuses
  }

  const plans = loadAllPlans()
  const unique = [...new Set(plans.map((p: ExitPlan) => p.ticker))]
  const script = join(findProjectRoot(), "scripts", "py", "get_price.py")

  // Fetch in parallel batches (4 at a time)
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
  return statuses
}

export type { ExitPlan, ExitStatus, ExitTarget } from "./positions.ts"
