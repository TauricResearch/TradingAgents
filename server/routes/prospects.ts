import { Hono } from "hono"
import { DatabaseFactory } from "../lib/db.ts"
import { sanitizeForDb } from "../lib/sanitize.ts"

export const prospectsRouter = new Hono()

const STAGES = ["researching", "analyzed", "candidate", "approved", "acquired"] as const

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

/** POST /api/prospects — add ticker to watchlist */
prospectsRouter.post("/", async (c) => {
  const db = DatabaseFactory.get()
  const body = await c.req.json()
  const { ticker, exchange, platform, thesis, priority } = body

  if (!ticker) {
    return c.json({ error: "ticker is required" }, 400)
  }

  try {
    const stmt = db.prepare(
      "INSERT INTO watchlist (ticker, exchange, platform, thesis, priority, added_date) VALUES (?, ?, ?, ?, ?, ?)",
    )
    const result = stmt.run(
      ticker,
      exchange ?? "US",
      platform ?? "unknown",
      sanitizeForDb(thesis) ?? null,
      priority ?? "medium",
      new Date().toISOString().slice(0, 10),
    )
    return c.json(
      {
        id: result.lastInsertRowid,
        ticker,
        platform: platform ?? "unknown",
        stage: "researching",
      },
      201,
    )
  } catch (e: unknown) {
    if ((e as Error).message.includes("UNIQUE")) {
      return c.json({ error: `${ticker} already on watchlist` }, 409)
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
    return c.json({ error: `Invalid stage. Must be: ${STAGES.join(", ")}` }, 400)
  }

  const result = db.prepare("UPDATE watchlist SET stage = ? WHERE id = ?").run(stage, id)
  if (result.changes === 0) {
    return c.json({ error: "Prospect not found" }, 404)
  }

  return c.json({ id, stage })
})

/** DELETE /api/prospects/:id — remove from watchlist */
prospectsRouter.delete("/:id", (c) => {
  const db = DatabaseFactory.get()
  const id = c.req.param("id")
  const result = db.prepare("DELETE FROM watchlist WHERE id = ?").run(id)
  if (result.changes === 0) {
    return c.json({ error: "Prospect not found" }, 404)
  }
  return c.json({ id, deleted: true })
})
