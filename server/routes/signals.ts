import { Hono } from "hono"
import { DatabaseFactory } from "../lib/db.ts"

export const signalsRouter = new Hono()

/** GET /api/signals — list all signals, optionally filter by ticker */
signalsRouter.get("/", (c) => {
  const db = DatabaseFactory.get()
  const ticker = c.req.query("ticker")

  let query = "SELECT * FROM signals ORDER BY date DESC, id DESC"
  const params: string[] = []

  if (ticker) {
    query = "SELECT * FROM signals WHERE ticker = ? ORDER BY date DESC, id DESC"
    params.push(ticker)
  }

  const rows = db.query(query).all(...params)
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
  const { ticker, date, signal, reasoning, confidence } = body

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
    `INSERT INTO signals (ticker, date, signal, reasoning, confidence)
     VALUES (?, ?, ?, ?, ?)`,
  )
  const result = stmt.run(
    ticker,
    date ?? new Date().toISOString().slice(0, 10),
    normalised,
    reasoning ?? null,
    confidence != null ? Number(confidence) : null,
  )

  // Return only server-generated fields, not user input
  return c.json(
    {
      id: result.lastInsertRowid,
      ticker,
      date: date ?? new Date().toISOString().slice(0, 10),
      signal: normalised,
    },
    201,
  )
})
