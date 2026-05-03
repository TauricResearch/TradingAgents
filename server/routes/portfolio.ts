import { Hono } from "hono"
import { DatabaseFactory } from "../lib/db.ts"
import { sanitizeForDb } from "../lib/sanitize.ts"

export const portfolioRouter = new Hono()

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
  const result = stmt.run(
    ticker,
    exchange ?? "US",
    platform ?? "unknown",
    quantity,
    avg_cost,
    entry_date ?? new Date().toISOString().slice(0, 10),
    sanitizeForDb(thesis) ?? null,
    sanitizeForDb(notes) ?? null,
  )
  return c.json(
    {
      id: result.lastInsertRowid,
      ticker,
      exchange: exchange ?? "US",
      platform: platform ?? "unknown",
      quantity,
      avg_cost,
    },
    201,
  )
})

/** DELETE /api/positions/:id — close a position */
portfolioRouter.delete("/:id", (c) => {
  const db = DatabaseFactory.get()
  const id = c.req.param("id")
  const stmt = db.prepare("UPDATE positions SET status = 'closed' WHERE id = ?")
  const result = stmt.run(id)
  if (result.changes === 0) {
    return c.json({ error: "position not found" }, 404)
  }
  return c.json({ status: "closed", id })
})
