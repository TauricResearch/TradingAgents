/**
 * Stocks view — card grid for positions + watchlist items.
 *
 * Routes (mounted at /stocks):
 *   GET /stocks           → full page with card grid
 *   GET /stocks/api       → JSON card data
 *   GET /stocks/api/html  → server-rendered card grid (HTMX)
 */

import { Hono } from "hono"
import { DatabaseFactory } from "@lib/db"
import type { OHLCVBar } from "../lib/indicators.ts"
import { computeSnapshot, evaluateScan } from "../lib/indicators.ts"
import { StockCardGrid, type StockCardData } from "../views/components/StockCard.tsx"

const stocks = new Hono()

// ── Data fetching ────────────────────────────────────────────

interface PositionRow { ticker: string; exchange: string; platform: string; quantity: number; avg_cost: number; status: string }
interface WatchlistRow { ticker: string; exchange: string; platform: string; priority: string }
interface PriceRow { date: string; close: number | string; open: number | string; high: number | string; low: number | string; volume: number | string; gbp_rate: number | null }
interface IndicatorRow {
  price: number | string
  rsi_14: number | string; bb_lower: number | string; bb_middle: number | string; bb_upper: number | string
  ma_20: number | string; ma_150: number | string; adx_14: number | string
  macd_line: number | string; macd_signal: number | string; macd_histogram: number | string
  volume: number | string; volume_20avg: number | string
}

const SPARK_POINTS = 20

function sampleSparkline(closes: number[], n = SPARK_POINTS): number[] {
  if (closes.length === 0) return []
  if (closes.length <= n) return closes
  const step = (closes.length - 1) / (n - 1)
  return Array.from({ length: n }, (_, i) => closes[Math.round(i * step)]!)
}

function parseFloatOrNull(v: number | string | null): number | null {
  if (v === null || v === undefined) return null
  const n = parseFloat(String(v))
  return isNaN(n) ? null : n
}

function getAllTickers(db: ReturnType<typeof DatabaseFactory.get>): string[] {
  const positions = db.query("SELECT DISTINCT ticker FROM positions WHERE status = 'open'").all() as Array<{ ticker: string }>
  const watchlist = db.query("SELECT DISTINCT ticker FROM watchlist").all() as Array<{ ticker: string }>
  const set = new Set<string>()
  for (const r of positions) set.add(r.ticker)
  for (const r of watchlist) set.add(r.ticker)
  return Array.from(set)
}

function getPositions(db: ReturnType<typeof DatabaseFactory.get>): PositionRow[] {
  return db.query(
    "SELECT ticker, exchange, platform, quantity, avg_cost, status FROM positions WHERE status = 'open'",
  ).all() as PositionRow[]
}

function getWatchlist(db: ReturnType<typeof DatabaseFactory.get>): WatchlistRow[] {
  return db.query(
    "SELECT ticker, exchange, platform, priority FROM watchlist",
  ).all() as WatchlistRow[]
}

function getPriceHistory(db: ReturnType<typeof DatabaseFactory.get>, ticker: string): PriceRow[] {
  return db.query(
    "SELECT date, close, open, high, low, volume, gbp_rate FROM prices WHERE ticker = ? ORDER BY date ASC",
  ).all(ticker) as PriceRow[]
}

function getIndicatorReading(db: ReturnType<typeof DatabaseFactory.get>, ticker: string): IndicatorRow | null {
  return db.query(
    "SELECT price, rsi_14, bb_lower, bb_middle, bb_upper, ma_20, ma_150, adx_14, macd_line, macd_signal, macd_histogram, volume, volume_20avg FROM indicator_readings WHERE ticker = ? ORDER BY date DESC LIMIT 1",
  ).get(ticker) as IndicatorRow | undefined ?? null
}

function computeCard(ticker: string, isHolding: boolean, quantity: number | undefined, avgCost: number | undefined, db: ReturnType<typeof DatabaseFactory.get>): StockCardData {
  // Latest price
  const latest = db.query(
    "SELECT close, date, gbp_rate FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
  ).get(ticker) as { close: number; date: string; gbp_rate: number | null } | undefined

  const currentPrice = latest ? parseFloatOrNull(latest.close) : null
  const lastPriceDate = latest?.date ?? null

  // Sparkline
  const allBars = db.query(
    "SELECT close FROM prices WHERE ticker = ? ORDER BY date ASC",
  ).all(ticker) as Array<{ close: number | string }>
  const closes = allBars.map(r => parseFloatOrNull(r.close) ?? 0)
  const sparkline = sampleSparkline(closes)

  // Change calculation (yesterday vs today)
  const changePct: number | null =
    allBars.length >= 2
      ? (() => {
          const today = parseFloatOrNull(allBars[allBars.length - 1]!.close) ?? 0
          const yesterday = parseFloatOrNull(allBars[allBars.length - 2]!.close) ?? 0
          return yesterday > 0 ? ((today - yesterday) / yesterday) * 100 : null
        })()
      : null

  // Indicators: try cached reading first, then compute from prices
  let indicators = null
  let signal: "buy" | "no_buy" | "sell" | null = null
  let gatesPassed = 0; let gatesTotal = 6
  let firstFailure: string | null = null
  let exitStatus: string | null = null

  const cached = getIndicatorReading(db, ticker)
  if (cached) {
    const snapshot = {
      ticker,
      date: lastPriceDate ?? "",
      price: parseFloatOrNull(cached.price) ?? 0,
      rsi_14: parseFloatOrNull(cached.rsi_14) ?? 0,
      bb_lower: parseFloatOrNull(cached.bb_lower) ?? 0,
      bb_middle: parseFloatOrNull(cached.bb_middle) ?? 0,
      bb_upper: parseFloatOrNull(cached.bb_upper) ?? 0,
      ma_20: parseFloatOrNull(cached.ma_20) ?? 0,
      ma_150: parseFloatOrNull(cached.ma_150) ?? 0,
      adx_14: parseFloatOrNull(cached.adx_14) ?? 0,
      adx_plus_di: 0,
      adx_minus_di: 0,
      macd_line: parseFloatOrNull(cached.macd_line) ?? 0,
      macd_signal: parseFloatOrNull(cached.macd_signal) ?? 0,
      macd_histogram: parseFloatOrNull(cached.macd_histogram) ?? 0,
      volume: parseFloatOrNull(cached.volume) ?? 0,
      volume_20avg: parseFloatOrNull(cached.volume_20avg) ?? 0,
      volume_confirmed: false,
    }
    signal = evaluateScan(ticker, snapshot).signal
    gatesPassed = evaluateScan(ticker, snapshot).gatesPassed
    firstFailure = evaluateScan(ticker, snapshot).gates.find(g => !g.pass && !g.relaxed)?.threshold ?? null
    exitStatus = evaluateScan(ticker, snapshot).exitTriggers[0] ?? "clear"
  } else if (closes.length >= 150) {
    // Compute fresh from prices
    const priceRows = getPriceHistory(db, ticker)
    const bars: OHLCVBar[] = priceRows.map(r => ({
      date: r.date,
      open: parseFloatOrNull(r.open) ?? 0,
      high: parseFloatOrNull(r.high) ?? 0,
      low: parseFloatOrNull(r.low) ?? 0,
      close: parseFloatOrNull(r.close) ?? 0,
      volume: parseFloatOrNull(r.volume) ?? 0,
    }))
    const snapshot = computeSnapshot(ticker, bars)
    if (snapshot) {
      const result = evaluateScan(ticker, snapshot)
      signal = result.signal
      gatesPassed = result.gatesPassed
      firstFailure = result.gates.find(g => !g.pass && !g.relaxed)?.threshold ?? null
      exitStatus = result.exitTriggers[0] ?? "clear"
      indicators = snapshot
    }
  }

  return {
    ticker,
    platform: "unknown",
    isHolding,
    quantity,
    avgCost,
    currentPrice,
    changePct,
    lastPriceDate,
    sparkline,
    indicators,
    signal,
    gatesPassed,
    gatesTotal,
    firstFailure,
    exitStatus,
  }
}

function buildCards(): StockCardData[] {
  const db = DatabaseFactory.get()
  const positions = getPositions(db)
  const watchlist = getWatchlist(db)

  const holdingTickers = new Set(positions.map(p => p.ticker))

  const cards: StockCardData[] = []

  // Positions first
  for (const p of positions) {
    cards.push(computeCard(p.ticker, true, p.quantity, p.avg_cost, db))
  }

  // Watchlist items not already in positions
  for (const w of watchlist) {
    if (!holdingTickers.has(w.ticker)) {
      cards.push(computeCard(w.ticker, false, undefined, undefined, db))
    }
  }

  return cards
}

// ── Routes ─────────────────────────────────────────────────

// GET /stocks — full page
stocks.get("/", (c) => {
  const cards = buildCards()
  const grid = <StockCardGrid cards={cards} />
  return c.html(
    `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>Stocks — TradingAgents</title><link rel="stylesheet" href="/static/style.css"/><link rel="stylesheet" href="/static/hljs.css"/><script src="https://unpkg.com/htmx.org@2.0.4"/></head><body><div id="content">${String(grid)}</div></body></html>`,
  )
})

// GET /stocks/api — JSON
stocks.get("/api", (c) => {
  const cards = buildCards()
  return c.json({ cards })
})

// GET /stocks/api/html — server-rendered card grid (HTMX)
stocks.get("/api/html", (c) => {
  const cards = buildCards()
  return c.html(<StockCardGrid cards={cards} />)
})

export { stocks }