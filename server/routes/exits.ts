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
import { fetchPrice } from "../lib/cache.ts"
import {
  computeExitStatus,
  type ExitPlan,
  type ExitStatus,
  loadAllPlans,
} from "../lib/positions.ts"

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

function buildExitsHtml(statuses: ExitStatus[]): string {
  if (!statuses || statuses.length === 0) {
    return '<div class="muted">No exit plans. Create YAML files in ~/.tradingagents/positions/</div>'
  }

  let html = ""
  for (const s of statuses) {
    const p = s.plan
    const isWarn = s.distanceToStopPct < 10
    const warnStyle = isWarn ? ' style="background:#fff3cd;color:#1a1a2e"' : ""
    const pnlColor = isWarn ? "#1a1a2e" : s.pnlPct >= 0 ? "var(--green)" : "var(--red)"

    html += `<div class="exit-card"${warnStyle}>`
    html += '<div class="exit-header">'
    html += `<span class="ticker">${p.ticker}</span>`
    if (p.platform && p.platform !== "unknown") {
      html += `<span class="platform-tag">${p.platform}</span>`
    }
    html += `<span class="pnl" style="color:${pnlColor}">${s.pnlPct >= 0 ? "+" : ""}${s.pnlPct.toFixed(1)}%</span>`
    html += "</div>"

    html += '<div class="exit-details">'
    html += `<div><strong>Thesis:</strong> ${(p.thesis || "\u2014").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>`
    html += `<div><strong>Entry:</strong> ${p.quantity} @ \u00a3${p.entry_price.toFixed(2)} <span class="muted">(GBP)</span></div>`

    const stopPrice = p.invalidation?.price ?? p.invalidation_price ?? 0
    html += `<div><strong>Stop:</strong> \u00a3${stopPrice.toFixed(2)} <span class="muted">(GBP)</span>`
    if (s.distanceToStopPct !== undefined) {
      html += ` (${s.distanceToStopPct.toFixed(1)}% away)`
    }
    html += "</div>"

    if (p.targets && p.targets.length > 0) {
      html += `<div><strong>Targets:</strong> ${s.targetsHit}/${p.targets.length} hit`
      if (s.nextTarget) {
        html += ` \u2192 next \u00a3${s.nextTarget.price.toFixed(2)} <span class="muted">(GBP)</span>`
        if (s.distanceToTargetPct !== undefined) {
          html += ` (${s.distanceToTargetPct.toFixed(1)}% away)`
        }
      }
      html += "</div>"
    }

    if (s.timeStopDaysLeft !== undefined) {
      const urgency = s.timeStopDaysLeft < 30 ? " \u26a0\ufe0f" : ""
      html += `<div><strong>Time stop:</strong> ${s.timeStopDaysLeft} days left${urgency}</div>`
    }

    const invThesis = p.invalidation?.thesis ?? p.invalidation_thesis ?? "\u2014"
    html += `<div><strong>Invalidation:</strong> ${invThesis.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>`

    if (p.notes) {
      html += `<div class="notes">${p.notes.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>`
    }

    html += "</div></div>"
  }
  return html
}

/** GET /api/positions/exits/html — exit plans as HTML for HTMX */
exitsRouter.get("/html", async (c) => {
  const now = Date.now()

  // Serve from response cache if fresh
  if (responseCache && responseCache.expires > now) {
    return c.html(buildExitsHtml(responseCache.statuses as ExitStatus[]))
  }

  const plans = loadAllPlans()
  const unique = [...new Set(plans.map((p: ExitPlan) => p.ticker))]
  const script = join(findProjectRoot(), "scripts", "get_price.py")

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

  responseCache = { statuses, expires: now + 30_000 }
  return c.html(buildExitsHtml(statuses))
})
