/** DB-based analysis routes: /list and /:id (numeric DB id). */
import { Hono } from "hono"
import { DatabaseFactory } from "../lib/db.ts"
import { renderMarkdown } from "../lib/markdown.ts"
import { escapeHtml, signalClass } from "./analyses-common.ts"

export const analysesDbRouter = new Hono()

interface DbAnalysis {
  id: number
  ticker: string
  date: string
  decision: string | null
  platform: string
  raw_state: string | null
  created_at: string
}

/**
 * GET /api/analyses/list — analyses from the dashboard DB.
 * Returns analyses ordered by date descending, with has_raw_state flag.
 */
analysesDbRouter.get("/list", (c) => {
  const db = DatabaseFactory.get()
  const rows = db
    .query(
      "SELECT id, ticker, date, decision, platform, raw_state, created_at FROM analyses ORDER BY date DESC, id DESC",
    )
    .all() as DbAnalysis[]

  const result = rows.map((r) => ({
    id: r.id,
    ticker: r.ticker,
    date: r.date,
    decision: r.decision ?? null,
    platform: r.platform,
    has_raw_state: r.raw_state != null && r.raw_state !== "[]" && r.raw_state !== "",
    created_at: r.created_at,
  }))

  return c.json(result)
})

/**
 * GET /api/analyses/:id — rendered full report from DB raw_state.
 * The :id param is the numeric DB id (not ticker/date).
 */
analysesDbRouter.get("/:id", (c) => {
  const id = c.req.param("id")
  const db = DatabaseFactory.get()
  const row = db
    .query(
      "SELECT id, ticker, date, decision, platform, raw_state, created_at FROM analyses WHERE id = ?",
    )
    .get(parseInt(id, 10)) as DbAnalysis | undefined

  if (!row) {
    return c.json({ error: "Analysis not found" }, 404)
  }

  let html = `<div class="report-header">
    <h2>${escapeHtml(row.ticker)}</h2>
    <span class="report-date">${escapeHtml(row.date)}</span>
    <span class="report-platform">${escapeHtml(row.platform)}</span>
  </div>`

  if (row.decision) {
    const signal = extractSignal(row.decision)
    const cls = signalClass(signal)
    html += `<div class="report-decision ${cls}">
      <strong>Decision:</strong> ${renderMarkdown(row.decision)}
    </div>`
  }

  if (row.raw_state && row.raw_state !== "[]" && row.raw_state !== "") {
    try {
      const events = JSON.parse(row.raw_state) as Array<{
        type: string
        data: Record<string, unknown>
      }>
      for (const event of events) {
        html += renderEventSection(event)
      }
    } catch {
      // Malformed JSON — skip
    }
  }

  return c.html(`<div class="panel report-panel"><div class="report-body">${html}</div></div>`)
})

function fmtDate(d: string): string {
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

function buildAnalysisReportHtml(row: DbAnalysis): string {
  let html = `<div class="report-header">
    <h2>${escapeHtml(row.ticker)}</h2>
    <span class="report-date">${escapeHtml(row.date)}</span>
    <span class="report-platform">${escapeHtml(row.platform)}</span>
  </div>`

  if (row.decision) {
    const signal = extractSignal(row.decision)
    const cls = signalClass(signal)
    html += `<div class="report-decision ${cls}">
      <strong>Decision:</strong> ${renderMarkdown(row.decision)}
    </div>`
  }

  if (row.raw_state && row.raw_state !== "[]" && row.raw_state !== "") {
    try {
      const events = JSON.parse(row.raw_state) as Array<{
        type: string
        data: Record<string, unknown>
      }>
      for (const event of events) {
        html += renderEventSection(event)
      }
    } catch {
      // Malformed JSON — skip
    }
  }

  return `<div class="panel report-panel"><div class="report-body">${html}</div></div>`
}

/** GET /api/analyses/list/html — analyses table as HTML for HTMX */
analysesDbRouter.get("/list/html", (c) => {
  const db = DatabaseFactory.get()
  const rows = db
    .query(
      "SELECT id, ticker, date, decision, platform, raw_state, created_at FROM analyses ORDER BY date DESC, id DESC",
    )
    .all() as DbAnalysis[]

  if (rows.length === 0) {
    return c.html(
      '<tr><td colspan="5" class="muted">No analyses yet. Run one from the Analysis tab.</td></tr>',
    )
  }

  let html = ""
  for (const r of rows) {
    const hasRaw = r.raw_state != null && r.raw_state !== "[]" && r.raw_state !== ""
    const decisionShort = r.decision ? r.decision.substring(0, 60) : "\u2014"
    const rowClass = hasRaw ? "has-raw" : "dec-only"
    html += `<tr class="${rowClass}">`
    html += `<td class="date-col">${fmtDate(r.date)}</td>`
    html += `<td class="ticker">${escapeHtml(r.ticker)}</td>`
    html += `<td class="muted" style="font-size:0.8em;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(r.decision ?? "")}">${escapeHtml(decisionShort)}</td>`
    html += `<td><span class="platform-tag">${escapeHtml(r.platform)}</span></td>`
    html += `<td><button class="btn-sm" hx-get="/api/analyses/${r.id}/card" hx-target="#history-content" hx-swap="innerHTML">View</button></td>`
    html += "</tr>"
  }

  return c.html(html)
})

/** GET /api/analyses/:id/card — analysis card with back button for HTMX */
analysesDbRouter.get("/:id/card", (c) => {
  const id = c.req.param("id")
  const db = DatabaseFactory.get()
  const row = db
    .query(
      "SELECT id, ticker, date, decision, platform, raw_state, created_at FROM analyses WHERE id = ?",
    )
    .get(parseInt(id, 10)) as DbAnalysis | undefined

  if (!row) {
    return c.html('<div class="error-card"><strong>Analysis not found</strong></div>', 404)
  }

  const report = buildAnalysisReportHtml(row)

  let html = `<div class="analysis-card">`
  html += `<button class="btn-sm" hx-get="/api/analyses/list/html" hx-target="#history-content" hx-swap="innerHTML">\u2190 Back to list</button>`
  html += `<div class="analysis-report-container">${report}</div>`
  html += `</div>`

  return c.html(html)
})

function extractSignal(text: string): string {
  const lower = text.toLowerCase()
  if (lower.includes("overweight") || lower.includes("buy")) return "Overweight"
  if (lower.includes("underweight") || lower.includes("sell")) return "Underweight"
  return "Hold"
}

function renderEventSection(event: { type: string; data: Record<string, unknown> }): string {
  const t = event.type
  const d = event.data

  if (t === "start") {
    return `<div class="event-section event-start">
      <h4>Analysis started</h4>
      <p class="muted">${escapeHtml(String(d.date ?? d.timestamp ?? ""))}</p>
    </div>`
  }

  if (t === "agent_report") {
    const agent = String(d.agent ?? "Unknown")
    const report = String(d.report ?? "")
    const sectionClass = agent.toLowerCase().replace(/\s+/g, "-")
    return `<div class="event-section agent-report ${sectionClass}">
      <h4>${escapeHtml(agent)} Report</h4>
      ${renderMarkdown(report)}
    </div>`
  }

  if (t === "debate_round") {
    const round = Number(d.round ?? 0)
    const stance = String(d.stance ?? "")
    const discussion = String(d.discussion ?? "")
    const verdict = String(d.verdict ?? "")
    const cls = signalClass(verdict)
    return `<div class="event-section debate-round">
      <h4>Debate Round ${round} <span class="${cls}">(${escapeHtml(stance)})</span></h4>
      ${renderMarkdown(discussion)}
      ${verdict ? `<div class="verdict ${cls}"><strong>Verdict:</strong> ${renderMarkdown(verdict)}</div>` : ""}
    </div>`
  }

  if (t === "risk_assessment") {
    const severity = String(d.severity ?? "info")
    const content = String(d.content ?? d.assessment ?? "")
    return `<div class="event-section risk-assessment risk-${severity}">
      <h4>Risk Assessment <span class="risk-badge">${escapeHtml(severity)}</span></h4>
      ${renderMarkdown(content)}
    </div>`
  }

  if (t === "decision") {
    const signal = String(d.signal ?? "")
    const confidence = d.confidence != null ? Number(d.confidence) : null
    const rationale = String(d.rationale ?? d.text ?? "")
    const cls = signalClass(signal)
    const confStr = confidence != null ? ` (${Math.round(confidence * 100)}% confidence)` : ""
    return `<div class="event-section final-decision ${cls}">
      <h4>Final Decision <span class="${cls}">${escapeHtml(signal)}${confStr}</span></h4>
      ${renderMarkdown(rationale)}
    </div>`
  }

  if (t === "complete") {
    return `<div class="event-section event-complete">
      <p class="muted">Analysis complete</p>
    </div>`
  }

  if (t === "error") {
    const msg = String(d.message ?? "Unknown error")
    return `<div class="event-section event-error">
      <h4>Error</h4>
      <p style="color:var(--red)">${escapeHtml(msg)}</p>
    </div>`
  }

  return `<div class="event-section unknown">
    <h4>${escapeHtml(t)}</h4>
    <pre>${escapeHtml(JSON.stringify(event.data, null, 2))}</pre>
  </div>`
}
