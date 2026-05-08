/** Signals data layer — extracted from route for reuse. */
import { spawn } from "node:child_process"
import { join } from "node:path"
import { DatabaseFactory } from "../../lib/db.ts"
import { sanitizeForDb } from "./sanitize.ts"
import { findProjectRoot } from "./utils.ts"

export interface Signal {
  id?: number
  ticker: string
  platform: string
  date: string
  signal: string
  reasoning: string | null
  confidence: number | null
  [key: string]: unknown
}

export interface PriceWithHistory {
  price: number | null
  currency: string
  history: { date: string; close: number }[]
}

// ── Helpers ─────────────────────────────────────────────────────────────────

export function escSignals(s: string | null | undefined): string {
  if (s == null) return ""
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

export function fmtDateSignals(d: string): string {
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
  const [_year, month, day] = parts as [string, string, string]
  return `${parseInt(day, 10)}-${months[parseInt(month, 10) - 1] ?? ""}`
}

export function signalClassSignals(signal: string): string {
  const s = (signal || "").toLowerCase()
  if (s.includes("buy") || s.includes("overweight")) return "status-buy"
  if (s.includes("sell") || s.includes("underweight")) return "status-sell"
  return "status-hold"
}

function norm(vals: number[]): number[] {
  if (!vals || vals.length === 0) return []
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const rng = hi - lo
  if (rng === 0) return vals.map(() => 50)
  return vals.map((v) => Math.round(((v - lo) / rng) * 100))
}

export function sparkline(history: Array<{ close: number }> | null): string | null {
  if (!history || history.length === 0) return null
  const closes = history
    .slice(-20)
    .map((h) => h.close)
    .reverse()
  const n = norm(closes)
  return n.length > 0 ? `{l:${n.join(",")}}` : null
}

// ── Batch price fetch with history (for sparklines) ─────────────────────────

export async function batchFetchPricesWithHistory(
  tickers: string[],
): Promise<Map<string, PriceWithHistory>> {
  const results = new Map<string, PriceWithHistory>()
  if (tickers.length === 0) return results

  const root = findProjectRoot()
  const script = join(root, "scripts", "py", "get_price.py")

  // Fetch in parallel batches of 4 (yfinance is the bottleneck)
  const BATCH_SIZE = 4
  for (let i = 0; i < tickers.length; i += BATCH_SIZE) {
    const batch = tickers.slice(i, i + BATCH_SIZE)
    const batchResults = await Promise.all(
      batch.map(
        (ticker) =>
          new Promise<[string, PriceWithHistory]>((resolve) => {
            const child = spawn("python3", [script, ticker], {
              env: { ...process.env, PYTHONUNBUFFERED: "1" },
              timeout: 12_000,
            })
            let stdout = ""
            child.stdout.on("data", (d: Buffer) => {
              stdout += d.toString()
            })
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
            child.on("error", () =>
              resolve([ticker, { price: null, currency: "USD", history: [] }]),
            )
          }),
      ),
    )
    for (const [ticker, data] of batchResults) {
      results.set(ticker, data)
    }
  }

  return results
}

// ── Fetch signals with price history ────────────────────────────────────────

export interface SignalsFetchResult {
  signals: Signal[]
  priceData: Map<string, PriceWithHistory>
}

export async function fetchSignalsWithHistory(
  ticker: string | undefined,
  platform: string | undefined,
): Promise<SignalsFetchResult> {
  const db = DatabaseFactory.get()

  let rows: unknown[]
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

  const signals = rows as Signal[]
  const tickers = [...new Set(signals.map((r) => r.ticker))]
  const priceData = await batchFetchPricesWithHistory(tickers)
  return { signals, priceData }
}

// ── CRUD helpers ────────────────────────────────────────────────────────────

export function getSignals(ticker: string | undefined, platform: string | undefined): Signal[] {
  const db = DatabaseFactory.get()
  if (ticker && platform) {
    return db
      .query("SELECT * FROM signals WHERE ticker = ? AND platform = ? ORDER BY date DESC, id DESC")
      .all(ticker, platform) as Signal[]
  }
  if (ticker) {
    return db
      .query("SELECT * FROM signals WHERE ticker = ? ORDER BY date DESC, id DESC")
      .all(ticker) as Signal[]
  }
  if (platform) {
    return db
      .query("SELECT * FROM signals WHERE platform = ? ORDER BY date DESC, id DESC")
      .all(platform) as Signal[]
  }
  return db.query("SELECT * FROM signals ORDER BY date DESC, id DESC").all() as Signal[]
}

export function getSignalsForTicker(ticker: string): Signal[] {
  const db = DatabaseFactory.get()
  return db
    .query("SELECT * FROM signals WHERE ticker = ? ORDER BY date DESC, id DESC")
    .all(ticker) as Signal[]
}

export function getDistinctPlatforms(): string[] {
  const db = DatabaseFactory.get()
  return (
    db.query("SELECT DISTINCT platform FROM signals ORDER BY platform").all() as Array<{
      platform: string
    }>
  ).map((r) => r.platform)
}

export function getDistinctTickers(): string[] {
  const db = DatabaseFactory.get()
  return (
    db.query("SELECT DISTINCT ticker FROM signals ORDER BY ticker").all() as Array<{
      ticker: string
    }>
  ).map((r) => r.ticker)
}

export function createSignal(body: {
  ticker: string
  date?: string
  signal: string
  reasoning?: string
  confidence?: number
  platform?: string
}): { id: number; ticker: string; platform: string; date: string; signal: string } {
  const db = DatabaseFactory.get()
  const { ticker, date, signal, reasoning, confidence, platform } = body

  const VALID_SIGNALS = ["buy", "overweight", "hold", "underweight", "sell"]
  const normalised = String(signal).toLowerCase()
  if (!VALID_SIGNALS.includes(normalised)) {
    throw new Error(`signal must be one of: ${VALID_SIGNALS.join(", ")}`)
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

  return {
    id: Number(result.lastInsertRowid),
    ticker,
    platform: platform ?? "unknown",
    date: date ?? new Date().toISOString().slice(0, 10),
    signal: normalised,
  }
}
