/** DB-based analysis routes: /list and /:id (numeric DB id). */
import { Hono } from "hono"
import { DatabaseFactory } from "../../lib/db.ts"
import type { DbAnalysis } from "../lib/analysis-data.ts"
import {
  AnalysesListView,
  AnalysisCardView,
  AnalysisReportView,
} from "../views/analysis-report.tsx"

export const analysesDbRouter = new Hono()

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

/** GET /api/analyses/list/html — analyses table as HTML for HTMX */
analysesDbRouter.get("/list/html", (c) => {
  const db = DatabaseFactory.get()
  const rows = db
    .query(
      "SELECT id, ticker, date, decision, platform, raw_state, created_at FROM analyses ORDER BY date DESC, id DESC",
    )
    .all() as DbAnalysis[]

  return c.html(<AnalysesListView rows={rows} />)
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

  return c.html(<AnalysisReportView row={row} />)
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
    return c.html(
      <div class="error-card">
        <strong>Analysis not found</strong>
      </div>,
      404,
    )
  }

  return c.html(<AnalysisCardView row={row} />)
})
