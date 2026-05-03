/**
 * GET /api/positions/exits — exit status for all planned positions
 *
 * Fetches live prices for each ticker, then computes exit status
 * (P&L, distance to stop, distance to targets).
 */
import { spawn } from "node:child_process"
import { dirname, join } from "node:path"
import { Hono } from "hono"
import { computeExitStatus, type ExitPlan, loadAllPlans } from "../lib/positions.ts"

export const exitsRouter = new Hono()

function findProjectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT
  const projectRoot = dirname(dirname(import.meta.dir))
  if (projectRoot.includes("TradingAgents")) return projectRoot
  return projectRoot
}

// Simple in-memory cache — prices valid for 60s
const priceCache = new Map<string, { price: number | null; expires: number }>()

// Response-level cache — full exit statuses valid for 30s
let responseCache: { statuses: unknown[]; expires: number } | null = null

function fetchPrice(ticker: string): Promise<number | null> {
  return new Promise((resolve) => {
    const now = Date.now()
    const cached = priceCache.get(ticker)
    if (cached && cached.expires > now) {
      resolve(cached.price)
      return
    }

    const root = findProjectRoot()
    const script = join(root, "scripts", "get_price.py")
    const child = spawn("python3", [script, ticker], {
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    })
    let resolved = false
    const finish = (price: number | null) => {
      if (resolved) return
      resolved = true
      child.kill()
      // Cache success OR failure (don't hammer on outages)
      priceCache.set(ticker, { price, expires: now + 60_000 })
      resolve(price)
    }
    let stdout = ""
    child.stdout.on("data", (d: Buffer) => {
      stdout += d.toString()
    })
    // Hard timeout — per ticker budget
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

exitsRouter.get("/", async (c) => {
  const now = Date.now()

  // Serve from response cache if fresh
  if (responseCache && responseCache.expires > now) {
    return c.json(responseCache.statuses)
  }

  const plans = loadAllPlans()
  const unique = [...new Set(plans.map((p: ExitPlan) => p.ticker))]

  // Fetch in parallel batches (4 at a time) — keeps total time under ~40s
  const BATCH_SIZE = 4
  const priceMap = new Map<string, number | null>()
  for (let i = 0; i < unique.length; i += BATCH_SIZE) {
    const batch = unique.slice(i, i + BATCH_SIZE)
    const results = await Promise.all(batch.map((t) => fetchPrice(t)))
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
