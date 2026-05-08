import { type Context, Hono } from "hono"
import { DatabaseFactory } from "../../lib/db.ts"
import { sanitizeForDb } from "../lib/sanitize.ts"
import { computePortfolioSummary } from "../lib/portfolio-data.ts"
import { PortfolioSummaryView } from "../views/portfolio-summary.tsx"

export const portfolioRouter = new Hono()

// ── Positions CRUD ────────────────────────────────────────────────────────────

/** GET /api/positions — list all open positions, optionally filter by platform */
portfolioRouter.get("/", (c) => {
  const db = DatabaseFactory.get()
  const platform = c.req.query("platform")
  if (platform) {
    const rows = db
      .query("SELECT * FROM positions WHERE status = 'open' AND platform = ? ORDER BY ticker")
      .all(platform)
    return c.json(rows)
  }
  const rows = db.query("SELECT * FROM positions WHERE status = 'open' ORDER BY ticker").all()
  return c.json(rows)
})

/** POST /api/positions — add a new position */
portfolioRouter.post("/", async (c) => {
  const db = DatabaseFactory.get()
  const body = await c.req.json()
  const { ticker, exchange, platform, quantity, avg_cost, entry_date, thesis, notes } = body
  if (!ticker || quantity == null || avg_cost == null) {
    return c.json({ error: "ticker, quantity, avg_cost required" }, 400)
  }
  const stmt = db.prepare(
    `INSERT INTO positions (ticker, exchange, platform, quantity, avg_cost, entry_date, thesis, notes)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  )
  stmt.run(
    ticker,
    exchange ?? "US",
    platform ?? "unknown",
    quantity,
    avg_cost,
    entry_date ?? new Date().toISOString().slice(0, 10),
    sanitizeForDb(thesis) ?? null,
    sanitizeForDb(notes) ?? null,
  )

  // Return updated portfolio HTML for HTMX
  const summary = await computePortfolioSummary()
  return c.html(<PortfolioSummaryView data={summary} />)
})

/** DELETE /api/positions/:id — close a position */
portfolioRouter.delete("/:id", async (c) => {
  const db = DatabaseFactory.get()
  const id = c.req.param("id")
  const stmt = db.prepare("UPDATE positions SET status = 'closed' WHERE id = ?")
  const result = stmt.run(id)
  if (result.changes === 0) {
    return c.html(<div class="error-card"><strong>Position not found</strong></div>, 404)
  }

  // Return updated portfolio HTML for HTMX
  const summary = await computePortfolioSummary()
  return c.html(<PortfolioSummaryView data={summary} />)
})

// ── Portfolio P&L summary ─────────────────────────────────────────────────────

/**
 * Standalone portfolio summary handler — mounted at GET /api/portfolio/summary in index.tsx.
 * Separated from portfolioRouter (which is mounted at /api/positions) to keep URLs clean.
 */
export async function handlePortfolioSummary(c: Context): Promise<Response> {
  const summary = await computePortfolioSummary()
  return c.json(summary)
}

/** GET /api/portfolio/summary/html — portfolio summary + positions table as HTML for HTMX */
export async function handlePortfolioSummaryHtml(c: Context): Promise<Response> {
  try {
    const summary = await computePortfolioSummary()
    return c.html(<PortfolioSummaryView data={summary} />)
  } catch (e: unknown) {
    return c.html(
      <div class="error-card">
        <strong>Portfolio error</strong>
        <br />
        {(e as Error).message}
      </div>,
      500,
    )
  }
}
