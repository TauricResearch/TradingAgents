import { Hono } from "hono"
import { DatabaseFactory } from "../lib/db.ts"
import { sanitizeForDb } from "../lib/sanitize.ts"

export const prospectsRouter = new Hono()

const STAGES = ["researching", "analyzed", "candidate", "approved", "acquired"] as const

// ── HTML helpers ───────────────────────────────────────────────────────────────

function escProspects(s: string | null | undefined): string {
  if (s == null) return ""
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

interface Prospect {
  id: number
  ticker: string
  platform: string
  stage: string
  priority: string
  thesis: string | null
  last_signal: string | null
}

function buildProspectsHtml(items: Prospect[], selectedPlatform: string): string {
  let html =
    '<div class="form-row" style="margin-bottom:0.75rem" hx-get="/api/prospects/html" hx-target="#pipeline-wrapper" hx-trigger="change" hx-include="this">'
  html += '<h3 style="margin:0">Prospects Pipeline</h3>'
  html += `<select name="platform" style="margin-left:auto">`
  html += '<option value="">All platforms</option>'
  const platforms = ["degiero", "ibkr", "pension:nn", "test", "unknown"]
  for (const p of platforms) {
    html += `<option value="${p}"${p === selectedPlatform ? " selected" : ""}>${p === "unknown" ? "Other/Unknown" : p}</option>`
  }
  html += "</select></div>"

  const filtered = selectedPlatform
    ? items.filter((item) => item.platform === selectedPlatform)
    : items

  if (filtered.length === 0) {
    html += `<div class="muted">No prospects${selectedPlatform ? ` for ${escProspects(selectedPlatform)}` : ""}. Add tickers above.</div>`
    return html
  }

  const groups: Record<string, Prospect[]> = {}
  for (const s of STAGES) groups[s] = []
  for (const item of filtered) {
    const g = groups[item.stage]
    if (g) g.push(item)
  }

  html += '<div class="pipeline">'
  for (const stage of STAGES) {
    const stageItems = groups[stage] || []
    if (stageItems.length === 0) continue
    html += '<div class="pipeline-column">'
    html += `<div class="pipeline-header">${stage.charAt(0).toUpperCase() + stage.slice(1)} <span class="badge">${stageItems.length}</span></div>`
    html += '<div class="pipeline-body">'
    for (const item of stageItems) {
      html += `<div class="pipeline-card" data-id="${item.id}">`
      html += `<div class="card-title">${item.ticker}</div>`
      html += '<div class="card-meta">'
      if (item.platform && item.platform !== "unknown") {
        html += `<span class="platform-tag">${escProspects(item.platform)}</span>`
      }
      html += `<span class="priority-${item.priority || "medium"}">${item.priority || "medium"}</span>`
      html += `<span class="signal">${item.last_signal || "\u2014"}</span>`
      html += "</div>"
      if (item.thesis) {
        html += `<div class="card-thesis">${escProspects(item.thesis)}</div>`
      }
      html += '<div class="card-actions">'
      const idx = STAGES.indexOf(stage as (typeof STAGES)[number])
      if (idx >= 0 && idx < STAGES.length - 1) {
        const next = STAGES[idx + 1]
        html += `<button class="btn-sm" hx-post="/api/prospects/${item.id}/stage" hx-target="#pipeline-wrapper" hx-swap="innerHTML" hx-vals='{"stage":"${next}"}'>\u2192</button>`
      }
      html += `<button class="btn-sm danger" hx-delete="/api/prospects/${item.id}" hx-target="#pipeline-wrapper" hx-swap="innerHTML" hx-confirm="Remove ${item.ticker}?">\u2715</button>`
      html += "</div></div>"
    }
    html += "</div></div>"
  }
  html += "</div>"

  return html
}

async function fetchProspects(platform?: string): Promise<Prospect[]> {
  const db = DatabaseFactory.get()
  let rows: unknown[]
  if (platform) {
    rows = db
      .query(
        "SELECT * FROM watchlist WHERE platform = ? AND stage != 'acquired' ORDER BY priority DESC, added_date DESC",
      )
      .all(platform)
  } else {
    rows = db
      .query(
        "SELECT * FROM watchlist WHERE stage != 'acquired' ORDER BY priority DESC, added_date DESC",
      )
      .all()
  }
  return rows as Prospect[]
}

/** GET /api/prospects — list all watchlist items, optionally filter by platform */
prospectsRouter.get("/", (c) => {
  const db = DatabaseFactory.get()
  const stage = c.req.query("stage")
  const platform = c.req.query("platform")

  if (stage && platform) {
    const rows = db
      .query(
        "SELECT * FROM watchlist WHERE stage = ? AND platform = ? ORDER BY priority DESC, added_date DESC",
      )
      .all(stage, platform)
    return c.json(rows)
  }
  if (platform) {
    const rows = db
      .query(
        "SELECT * FROM watchlist WHERE platform = ? AND stage != 'acquired' ORDER BY priority DESC, added_date DESC",
      )
      .all(platform)
    return c.json(rows)
  }
  if (stage) {
    const rows = db
      .query("SELECT * FROM watchlist WHERE stage = ? ORDER BY priority DESC, added_date DESC")
      .all(stage)
    return c.json(rows)
  }

  const rows = db
    .query(
      "SELECT * FROM watchlist WHERE stage != 'acquired' ORDER BY priority DESC, added_date DESC",
    )
    .all()
  return c.json(rows)
})

/** GET /api/prospects/html — prospects pipeline as HTML for HTMX */
prospectsRouter.get("/html", async (c) => {
  try {
    const platform = c.req.query("platform") || ""
    const items = await fetchProspects(platform || undefined)
    return c.html(buildProspectsHtml(items, platform))
  } catch (e: unknown) {
    return c.html(
      `<div class="error-card"><strong>Prospects error</strong><br>${(e as Error).message}</div>`,
      500,
    )
  }
})

/** POST /api/prospects — add ticker to watchlist */
prospectsRouter.post("/", async (c) => {
  const db = DatabaseFactory.get()
  const body = await c.req.json()
  const { ticker, exchange, platform, thesis, priority } = body

  if (!ticker) {
    return c.html(`<div id="prospect-error" class="error-card">ticker is required</div>`, 400)
  }

  try {
    const stmt = db.prepare(
      "INSERT INTO watchlist (ticker, exchange, platform, thesis, priority, added_date) VALUES (?, ?, ?, ?, ?, ?)",
    )
    stmt.run(
      ticker,
      exchange ?? "US",
      platform ?? "unknown",
      sanitizeForDb(thesis) ?? null,
      priority ?? "medium",
      new Date().toISOString().slice(0, 10),
    )
    const items = await fetchProspects()
    return c.html(buildProspectsHtml(items, ""))
  } catch (e: unknown) {
    if ((e as Error).message.includes("UNIQUE")) {
      return c.html(
        `<div id="prospect-error" class="error-card">${ticker} already on watchlist</div>`,
        409,
      )
    }
    throw e
  }
})

/** POST /api/prospects/:id/stage — advance stage */
prospectsRouter.post("/:id/stage", async (c) => {
  const db = DatabaseFactory.get()
  const id = c.req.param("id")
  const body = await c.req.json()
  const { stage } = body

  if (!STAGES.includes(stage as (typeof STAGES)[number])) {
    return c.html(`<div class="error-card">Invalid stage. Must be: ${STAGES.join(", ")}</div>`, 400)
  }

  const result = db.prepare("UPDATE watchlist SET stage = ? WHERE id = ?").run(stage, id)
  if (result.changes === 0) {
    return c.html('<div class="error-card">Prospect not found</div>', 404)
  }

  const items = await fetchProspects()
  return c.html(buildProspectsHtml(items, ""))
})

/** DELETE /api/prospects/:id — remove from watchlist */
prospectsRouter.delete("/:id", async (c) => {
  const db = DatabaseFactory.get()
  const id = c.req.param("id")
  const result = db.prepare("DELETE FROM watchlist WHERE id = ?").run(id)
  if (result.changes === 0) {
    return c.html('<div class="error-card">Prospect not found</div>', 404)
  }

  const items = await fetchProspects()
  return c.html(buildProspectsHtml(items, ""))
})
