import { Hono, Context } from "hono"

interface Signal {
  id?: number
  ticker: string
  platform: string
  date: string
  signal: string
  reasoning: string | null
  confidence: number | null
  [key: string]: unknown
}
import { DatabaseFactory } from "../lib/db.ts"
import { sanitizeForDb } from "../lib/sanitize.ts"
import { priceCache, endOfToday } from "../lib/cache.ts"
import { dirname, join } from "node:path"
import { spawn } from "node:child_process"

export const signalsRouter = new Hono()

// ── Signals CRUD ──────────────────────────────────────────────────────────────

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

/** GET /api/signals/table — signals with price history for sparklines */
signalsRouter.get("/table", async (c) => {
  const db = DatabaseFactory.get()
  const ticker = c.req.query("ticker")
  const platform = c.req.query("platform")

  let rows
  if (ticker && platform) {
    rows = db
      .query("SELECT * FROM signals WHERE ticker = ? AND platform = ? ORDER BY date DESC, id DESC")
      .all(ticker, platform)
  } else if (ticker) {
    rows = db
      .query("SELECT * FROM signals WHERE ticker = ? ORDER BY date DESC, id DESC")
      .all(ticker)
  } else if (platform) {
    rows = db
      .query("SELECT * FROM signals WHERE platform = ? ORDER BY date DESC, id DESC")
      .all(platform)
  } else {
    rows = db.query("SELECT * FROM signals ORDER BY date DESC, id DESC").all()
  }

  // Collect unique tickers for price history fetch
  const signals = rows as Signal[]
  const tickers = [...new Set(signals.map((r) => r.ticker))]

  // Batch-fetch price histories
  const priceData = await batchFetchPricesWithHistory(tickers)

  // Merge price history into signals
  const enriched = signals.map((s) => ({
    ...s,
    price_history: priceData.get(s.ticker) ?? null,
  }))

  return c.json(enriched)
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
    { id: result.lastInsertRowid, ticker, platform: platform ?? "unknown", date: date ?? new Date().toISOString().slice(0, 10), signal: normalised },
    201,
  )
})

// ── Batch price fetch with history (for sparklines) ───────────────────────────

interface PriceWithHistory {
  price: number | null
  currency: string
  history: { date: string; close: number }[]
}

function findProjectRoot(): string {
  if (process.env.TA_ROOT) return process.env.TA_ROOT
  const projectRoot = dirname(dirname(import.meta.dir))
  if (projectRoot.includes("TradingAgents")) return projectRoot
  return projectRoot
}

async function batchFetchPricesWithHistory(tickers: string[]): Promise<Map<string, PriceWithHistory>> {
  const results = new Map<string, PriceWithHistory>()
  if (tickers.length === 0) return results

  const root = findProjectRoot()
  const script = join(root, "scripts", "get_price.py")

  // Fetch in parallel batches of 4 (yfinance is the bottleneck)
  const BATCH_SIZE = 4
  for (let i = 0; i < tickers.length; i += BATCH_SIZE) {
    const batch = tickers.slice(i, i + BATCH_SIZE)
    const batchResults = await Promise.all(
      batch.map(
        (ticker) =>
          new Promise<[string, PriceWithHistory]>((resolve) => {
            const cached = priceCache.get(ticker)
            const now = Date.now()
            // Check if we have cached full price data
            if (cached && cached.expires > now && cached.price !== null) {
              // We only cached price, not history — need to fetch anyway for history
              // But use cache to avoid duplicate spawns within same request
            }

            const child = spawn("python3", [script, ticker], {
              env: { ...process.env, PYTHONUNBUFFERED: "1" },
              timeout: 12_000,
            })
            let stdout = ""
            child.stdout.on("data", (d: Buffer) => { stdout += d.toString() })
            child.on("close", (code) => {
              if (code !== 0) {
                resolve([ticker, { price: null, currency: "USD", history: [] }])
                return
              }
              try {
                const data = JSON.parse(stdout.trim())
                const history: { date: string; close: number }[] = (data.history ?? []).slice(-20)
                resolve([
                  ticker,
                  {
                    price: data.price ?? null,
                    currency: data.currency ?? "USD",
                    history,
                  },
                ])
              } catch {
                resolve([ticker, { price: null, currency: "USD", history: [] }])
              }
            })
            child.on("error", () => resolve([ticker, { price: null, currency: "USD", history: [] }]))
          }),
      ),
    )
    for (const [ticker, data] of batchResults) {
      results.set(ticker, data)
    }
  }

  return results
}