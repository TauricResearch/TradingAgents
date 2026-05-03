import { Hono } from "hono"
import { DatabaseFactory } from "../lib/db.ts"
import { sanitizeForDb } from "../lib/sanitize.ts"

export const signalsRouter = new Hono()

/** GET /api/signals — list all signals, optionally filter by ticker or platform */
signalsRouter.get("/", (c) => {
  const db = DatabaseFactory.get()
  const ticker = c.req.query("ticker")
  const platform = c.req.query("platform")

  if (ticker && platform) {
    const rows = db
      .query("SELECT * FROM signals WHERE ticker = ? AND platform = ? ORDER BY date DESC, id DESC")
      .all(ticker, platform)
    return c.json(rows)
  }
  if (ticker) {
    const rows = db
      .query("SELECT * FROM signals WHERE ticker = ? ORDER BY date DESC, id DESC")
      .all(ticker)
    return c.json(rows)
  }
  if (platform) {
    const rows = db
      .query("SELECT * FROM signals WHERE platform = ? ORDER BY date DESC, id DESC")
      .all(platform)
    return c.json(rows)
  }

  const rows = db.query("SELECT * FROM signals ORDER BY date DESC, id DESC").all()
  return c.json(rows)
})

/** GET /api/signals/:ticker — signal timeline for a specific ticker */
signalsRouter.get("/:ticker", (c) => {
  const db = DatabaseFactory.get()
  const ticker = c.req.param("ticker")
  const rows = db
    .query("SELECT * FROM signals WHERE ticker = ? ORDER BY date DESC, id DESC")
    .all(ticker)
  return c.json(rows)
})

/** POST /api/signals — record a new signal */
signalsRouter.post("/", async (c) => {
  const db = DatabaseFactory.get()
  const body = await c.req.json()
  const { ticker, date, signal, reasoning, confidence, platform } = body

  if (!ticker || !signal) {
    return c.json({ error: "ticker and signal are required" }, 400)
  }

  // Validate signal against schema constraint
  const VALID_SIGNALS = ["buy", "overweight", "hold", "underweight", "sell"]
  const normalised = String(signal).toLowerCase()
  if (!VALID_SIGNALS.includes(normalised)) {
    return c.json({ error: `signal must be one of: ${VALID_SIGNALS.join(", ")}` }, 400)
  }

  const stmt = db.prepare(
    `INSERT INTO signals (ticker, platform, date, signal, reasoning, confidence)
     VALUES (?, ?, ?, ?, ?, ?)`,
  )
  const result = stmt.run(
    ticker,
    platform ?? "unknown",
    date ?? new Date().toISOString().slice(0, 10),
    normalised,
    sanitizeForDb(reasoning) ?? null,
    confidence != null ? Number(confidence) : null,
  )

  return c.json(
    {
      id: result.lastInsertRowid,
      ticker,
      platform: platform ?? "unknown",
      date: date ?? new Date().toISOString().slice(0, 10),
      signal: normalised,
    },
    201,
  )
})
