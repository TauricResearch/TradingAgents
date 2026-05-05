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
import { fetchPrice } from "../lib/cache.ts"
import { DatabaseFactory } from "../lib/db.ts"
import { getHoldings } from "../lib/hledger.ts"
import { computeExitStatus, type ExitPlan, loadAllPlans } from "../lib/positions.ts"

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
      id: p.id,
      ticker: p.ticker,
      exchange: p.exchange,
      platform: p.platform,
      quantity: p.quantity,
      avgCost: parseFloat(String(p.avg_cost)),
      entryDate: p.entry_date,
      thesis: p.thesis,
    }))

  // HOLDINGS vs PENDING EXIT — split by urgency signal
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
      avgCost: parseFloat(String(p.avg_cost)),
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

  // Empty hledger → explain the clean state
  const note =
    openPositions.length === 0 && rawPositions.length > 0
      ? "Portfolio appears empty — hledger has no real holdings. " +
        "Add positions to hledger to see them in the workflow."
      : openPositions.length === 0
        ? "No holdings in hledger. Portfolio is empty."
        : undefined

  return c.json({ approved, holdings, pendingExit, hledgerPlatforms: [...hledgerPlatforms], note })
})

// ── HTML helpers ─────────────────────────────────────────────────────────────

function escWorkflow(s: string | null | undefined): string {
  if (s == null) return ""
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

function fmtWorkflowDate(d: string): string {
  if (!d) return "\u2014"
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ]
  const parts = d.split("-")
  if (parts.length !== 3) return d
  const [year, month, day] = parts as [string, string, string]
  return parseInt(day, 10) + (months[parseInt(month, 10) - 1] ?? "") + year.slice(2)
}

interface WorkflowData {
  approved: Array<{
    id: number
    ticker: string
    platform: string
    quantity: number
    avgCost: number
    entryDate: string
    thesis: string | null
  }>
  holdings: Array<{
    id: number
    ticker: string
    platform: string
    quantity: number
    avgCost: number
    entryDate: string
    thesis: string | null
    exitPlan: {
      entryPrice: number
      invalidationPrice: number
      invalidationThesis: string
      targets: unknown[]
      timeStop: string | null
      timeStopDaysLeft?: number
      targetsHit: number
      distanceToStopPct: number
    }
  }>
  pendingExit: Array<{
    id: number
    ticker: string
    platform: string
    quantity: number
    avgCost: number
    entryDate: string
    thesis: string | null
    exitPlan: {
      entryPrice: number
      invalidationPrice: number
      invalidationThesis: string
      targets: unknown[]
      timeStop: string | null
      timeStopDaysLeft?: number
      targetsHit: number
      distanceToStopPct: number
    }
  }>
  hledgerPlatforms: string[]
  note?: string
}

const STAGES_DEF = [
  { id: "approved", label: "Approved", color: "#3b82f6", icon: "\u25C7" },
  { id: "holdings", label: "Holdings", color: "#22c55e", icon: "\u25C6" },
  { id: "pendingExit", label: "Pending Exit", color: "#f59e0b", icon: "\u26A0" },
] as const

function buildWorkflowCardHtml(item: WorkflowData["approved"][0], stageId: string): string {
  const plat = item.platform && item.platform !== "unknown" ? item.platform : null
  let html = '<div class="workflow-card">'
  html += '<div class="card-header">'
  html += `<span class="card-ticker">${item.ticker}</span>`
  if (plat) html += `<span class="platform-tag">${plat}</span>`
  html += "</div>"

  if (stageId === "approved") {
    html += `<div class="card-meta">Entry \u00a3${item.avgCost.toFixed(2)} \u00b7 ${item.quantity} shares</div>`
    html += `<div class="card-meta muted">${fmtWorkflowDate(item.entryDate)}</div>`
    if (item.thesis) html += `<div class="card-thesis">${escWorkflow(item.thesis)}</div>`
    html += '<div class="entry-process">'
    html +=
      '<div class="process-row"><span class="process-dot" style="background:#6b7280">1</span><span>AI analysis &amp; signal</span></div>'
    html += `<div class="process-row"><span class="process-dot" style="background:#6b7280">2</span><span>Position size: ${item.quantity} shares</span></div>`
    html += `<div class="process-row"><span class="process-dot" style="background:#6b7280">3</span><span>Entry: \u20AC${item.avgCost.toFixed(2)}</span></div>`
    html +=
      '<div class="process-row"><span class="process-dot" style="background:#ef4444">4</span><span>Define exit plan before entry</span></div>'
    html += "</div>"
    html += '<div class="card-actions">'
    html += `<a href="/analyze?ticker=${item.ticker}" class="btn-sm">Analyze</a>`
    html += `<a href="/exits" class="btn-sm">+ Exit Plan</a>`
    html += "</div>"
  } else if (stageId === "holdings") {
    const ep = (item as WorkflowData["holdings"][0]).exitPlan
    const inv = ep.invalidationPrice
    const entry = ep.entryPrice
    html += `<div class="card-meta">Entry \u00a3${entry.toFixed(2)} \u00b7 Stop \u00a3${inv.toFixed(2)}</div>`
    if (ep.timeStopDaysLeft !== undefined)
      html += `<div class="card-meta muted">${ep.timeStopDaysLeft}d to time stop</div>`
    html += '<div class="card-actions">'
    html += `<a href="/analyze?ticker=${item.ticker}" class="btn-sm">Analyze</a>`
    html += `<button class="btn-sm" hx-delete="/api/workflow/close/${item.id}" hx-target="#workflow-wrapper" hx-swap="innerHTML" hx-confirm="Close this position?">Close</button>`
    html += "</div>"
  } else if (stageId === "pendingExit") {
    const ep = (item as WorkflowData["pendingExit"][0]).exitPlan
    const inv = ep.invalidationPrice
    const dist = ep.distanceToStopPct
    const hit = ep.targetsHit
    const total = ep.targets.length
    const days = ep.timeStopDaysLeft
    const targets = ep.targets as Array<{ label?: string }>

    html += '<div class="exit-strategy">'
    html += `<div class="process-row"><span class="process-dot" style="background:#ef4444">Stop</span><span>\u00a3${inv.toFixed(2)} (${dist.toFixed(0)}%)</span></div>`
    for (let ti = 0; ti < targets.length; ti++) {
      const tp = targets[ti]!
      const isHit = ti < hit
      const label = tp.label || `Target ${ti + 1}`
      html += `<div class="process-row"><span class="process-dot ${isHit ? "hit" : "pending"}">${isHit ? "\u2713" : ti + 1}</span><span>${escWorkflow(label)}</span></div>`
    }
    if (days !== undefined && days !== null) {
      html += `<div class="process-row"><span class="process-dot ${days < 30 ? "warning" : "pending"}">\u23F1</span><span>Time stop in ${days}d</span></div>`
    }
    html += "</div>"

    if (dist > 0 && dist < 10)
      html += '<span class="urgency-badge" style="background:#ef4444">\u26A0 Near stop</span>'
    else if (dist >= 10 && dist < 15)
      html += '<span class="urgency-badge" style="background:#f59e0b">\u26A0 Watch</span>'
    if (hit > 0)
      html += `<span class="urgency-badge" style="background:#22c55e">\u2713 ${hit}/${total} hit</span>`
    if (days !== undefined && days !== null && days < 30)
      html += `<span class="urgency-badge" style="background:#ef4444">\u23F1 ${days}d</span>`

    html += '<div class="card-actions">'
    html += `<a href="/analyze?ticker=${item.ticker}" class="btn-sm">Review</a>`
    html += `<button class="btn-sm" hx-delete="/api/workflow/close/${item.id}" hx-target="#workflow-wrapper" hx-swap="innerHTML" hx-confirm="Close this position?">Close</button>`
    html += "</div>"
  }

  html += "</div>"
  return html
}

function buildWorkflowHtml(data: WorkflowData): string {
  if (data.note) {
    return `<div class="muted" style="margin-bottom:1rem">${escWorkflow(data.note)}</div>`
  }

  let html = '<div class="workflow">'
  for (const stage of STAGES_DEF) {
    const items = (data as unknown as Record<string, unknown[]>)[stage.id] || []
    html += '<div class="workflow-col">'
    html += `<div class="workflow-header" style="border-top-color:${stage.color}">`
    html += `<span style="color:${stage.color}">${stage.icon}</span> ${stage.label}`
    html += ` <span class="badge" style="background:${stage.color}">${items.length}</span>`
    html += "</div>"
    html += '<div class="workflow-body">'
    if (items.length === 0) {
      html += '<div class="workflow-empty">\u2014</div>'
    } else {
      for (const item of items) {
        html += buildWorkflowCardHtml(item as WorkflowData["approved"][0], stage.id)
      }
    }
    html += "</div></div>"
  }
  html += "</div>"
  return html
}

/** GET /api/workflow/html — workflow kanban as HTML for HTMX */
workflowRouter.get("/html", async (c) => {
  try {
    const data = await workflowRouter.request("/", {}, c.env)
    const json = (await data.json()) as WorkflowData
    return c.html(buildWorkflowHtml(json))
  } catch (e: unknown) {
    return c.html(
      `<div class="error-card"><strong>Workflow error</strong><br>${(e as Error).message}</div>`,
      500,
    )
  }
})

/** POST /api/workflow/close/:id — close a position and return workflow HTML */
workflowRouter.post("/close/:id", async (c) => {
  const db = DatabaseFactory.get()
  const id = c.req.param("id")
  const result = db.prepare("UPDATE positions SET status = 'closed' WHERE id = ?").run(id)
  if (result.changes === 0) {
    return c.html('<div class="error-card"><strong>Position not found</strong></div>', 404)
  }

  // Re-fetch workflow data and return HTML
  const data = await workflowRouter.request("/", {}, c.env)
  const json = (await data.json()) as WorkflowData
  return c.html(buildWorkflowHtml(json))
})
