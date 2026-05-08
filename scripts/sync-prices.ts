#!/usr/bin/env bun
/**
 * Sync daily price records for open positions.
 *
 * Usage:
 *   bun run scripts/sync-prices.ts               # Catch up all open positions to today
 *   bun run scripts/sync-prices.ts --ticker AAPL # Backfill single ticker from entry date
 *   bun run scripts/sync-prices.ts --all         # Full catch-up (gap fill + latest)
 *
 * DB resolution (mirrors src/server/index.tsx):
 *   --db PATH       Explicit path
 *   TEST_MODE=1     Uses TEST_PORTFOLIO_DB
 *   default         ./portfolio.db
 */

import type { Database } from "bun:sqlite"
import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { DatabaseFactory } from "../src/lib/db.ts"

const DEFAULT_DB = join(process.cwd(), "portfolio.db")

// ─── DB path resolution ──────────────────────────────────────────────────────

function resolveDbPath(explicitPath?: string): string {
  if (explicitPath)
    return explicitPath.startsWith("/") ? explicitPath : join(process.cwd(), explicitPath)
  if (process.env.PORTFOLIO_DB) return process.env.PORTFOLIO_DB
  if (process.env.TEST_MODE === "1") return process.env.TEST_PORTFOLIO_DB ?? "./test_portfolio.db"
  return DEFAULT_DB
}

// ─── Price fetching (reuse get_price.ts) ────────────────────────────────────

interface PriceBar {
  date: string
  open: number | null
  high: number | null
  low: number | null
  close: number
  volume: number | null
}

function fetchHistory(ticker: string): { bars: PriceBar[]; currency: string } {
  const proc = Bun.spawnSync({
    cmd: ["bun", "run", join(__dirname, "get_price.ts"), ticker],
    stdout: "pipe",
    stderr: "pipe",
  })

  if (proc.exitCode !== 0) {
    const err = new TextDecoder().decode(proc.stderr).trim()
    throw new Error(`get_price.ts failed for ${ticker}: ${err}`)
  }

  const data = JSON.parse(new TextDecoder().decode(proc.stdout)) as {
    history?: PriceBar[]
    currency?: string
  }
  return { bars: data.history ?? [], currency: data.currency ?? "USD" }
}

interface FxRates {
  GBPUSD: number
  GBPEUR: number
}

function fetchFxRates(): FxRates {
  const port = process.env.TA_DASHBOARD_PORT ?? "3000"
  const proc = Bun.spawnSync({
    cmd: ["curl", "-sf", `http://localhost:${port}/api/portfolio/fx-rates`],
    stdout: "pipe",
    stderr: "pipe",
  })

  if (proc.exitCode !== 0) {
    // Fallback: hardcoded rates (approx May 2026)
    return { GBPUSD: 1.27, GBPEUR: 1.18 }
  }

  try {
    const data = JSON.parse(new TextDecoder().decode(proc.stdout)) as FxRates
    return { GBPUSD: data.GBPUSD ?? 1.27, GBPEUR: data.GBPEUR ?? 1.18 }
  } catch {
    return { GBPUSD: 1.27, GBPEUR: 1.18 }
  }
}

// ─── Core sync logic ─────────────────────────────────────────────────────────

interface SyncResult {
  ticker: string
  action: string
  upserted: number
  skipped: number
  error?: string
}

function upsertPrices(
  db: Database,
  ticker: string,
  bars: PriceBar[],
  currency: string,
  gbpRate: number | null,
  dryRun = false,
): { upserted: number; skipped: number } {
  if (bars.length === 0) return { upserted: 0, skipped: 0 }

  const stmt = db.prepare(`
    INSERT OR REPLACE INTO prices (ticker, date, open, high, low, close, volume, currency, gbp_rate)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `)

  let upserted = 0
  const skipped = 0

  for (const bar of bars) {
    if (dryRun) {
      console.log(`    [dry-run] upsert ${ticker} ${bar.date} close=${bar.close}`)
      upserted++
    } else {
      stmt.run(
        ticker,
        bar.date,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
        currency,
        gbpRate,
      )
      upserted++
    }
  }

  return { upserted, skipped }
}

type GbpRateMap = Record<string, number>

function catchUpTicker(
  db: Database,
  ticker: string,
  options: { dryRun?: boolean; gbpRateMap?: GbpRateMap } = {},
): SyncResult {
  try {
    const { bars, currency } = fetchHistory(ticker)
    if (bars.length === 0) {
      return { ticker, action: "catch-up", upserted: 0, skipped: 0, error: "no data returned" }
    }

    const gbpRate = options.gbpRateMap?.[currency] ?? null
    const { upserted, skipped } = upsertPrices(db, ticker, bars, currency, gbpRate, options.dryRun)
    return { ticker, action: "catch-up", upserted, skipped }
  } catch (e: unknown) {
    return { ticker, action: "catch-up", upserted: 0, skipped: 0, error: (e as Error).message }
  }
}

function _backfillTicker(
  db: Database,
  ticker: string,
  fromDate: string,
  options: { dryRun?: boolean; gbpRateMap?: GbpRateMap } = {},
): SyncResult {
  try {
    const { bars, currency } = fetchHistory(ticker)
    if (bars.length === 0) {
      return { ticker, action: "backfill", upserted: 0, skipped: 0, error: "no data returned" }
    }

    // Filter bars to only those >= fromDate
    const filtered = bars.filter((b) => b.date >= fromDate)

    if (filtered.length === 0) {
      return {
        ticker,
        action: "backfill",
        upserted: 0,
        skipped: 0,
        error: `no bars on or after ${fromDate}`,
      }
    }

    const gbpRate = options.gbpRateMap?.[currency] ?? null
    const { upserted } = upsertPrices(db, ticker, filtered, currency, gbpRate, options.dryRun)
    return { ticker, action: "backfill", upserted, skipped: bars.length - filtered.length }
  } catch (e: unknown) {
    return { ticker, action: "backfill", upserted: 0, skipped: 0, error: (e as Error).message }
  }
}

function detectGaps(db: Database, ticker: string): { from: string; to: string }[] {
  const rows = db
    .query(`SELECT date FROM prices WHERE ticker = ? ORDER BY date ASC`)
    .all(ticker) as { date: string }[]

  if (rows.length < 2) return []

  const gaps: { from: string; to: string }[] = []
  for (let i = 1; i < rows.length; i++) {
    const prev = new Date(rows[i - 1].date)
    const curr = new Date(rows[i].date)
    // Count only weekdays between prev and curr (exclude weekends)
    let weekdays = 0
    const cursor = new Date(prev)
    cursor.setDate(cursor.getDate() + 1)
    while (cursor < curr) {
      const dow = cursor.getDay()
      if (dow !== 0 && dow !== 6) weekdays++
      cursor.setDate(cursor.getDate() + 1)
    }
    if (weekdays > 1) {
      // Real gap: prev +1 weekday to curr -1 weekday
      const gapStart = new Date(prev)
      let d = gapStart.getDay()
      do {
        gapStart.setDate(gapStart.getDate() + 1)
        d = gapStart.getDay()
      } while (d === 0 || d === 6)
      const gapEnd = new Date(curr)
      do {
        gapEnd.setDate(gapEnd.getDate() - 1)
        d = gapEnd.getDay()
      } while (d === 0 || d === 6)
      gaps.push({
        from: gapStart.toISOString().split("T")[0],
        to: gapEnd.toISOString().split("T")[0],
      })
    }
  }
  return gaps
}

function fillGap(
  db: Database,
  ticker: string,
  fromDate: string,
  toDate: string,
  options: { dryRun?: boolean; gbpRateMap?: GbpRateMap } = {},
): SyncResult {
  // Yahoo Finance returns up to 1mo of history. For gap fill, we'll re-fetch
  // the ticker and selectively upsert only bars within the gap window.
  // For large gaps (>30 days) we may miss data — warn about it.
  try {
    const { bars, currency } = fetchHistory(ticker)
    const filtered = bars.filter((b) => b.date >= fromDate && b.date <= toDate)

    if (filtered.length === 0) {
      return {
        ticker,
        action: "fill-gap",
        upserted: 0,
        skipped: 0,
        error: `no bars for gap ${fromDate}–${toDate} (may exceed 1mo window)`,
      }
    }

    const gbpRate = options.gbpRateMap?.[currency] ?? null
    const { upserted } = upsertPrices(db, ticker, filtered, currency, gbpRate, options.dryRun)
    return { ticker, action: "fill-gap", upserted, skipped: 0 }
  } catch (e: unknown) {
    return { ticker, action: "fill-gap", upserted: 0, skipped: 0, error: (e as Error).message }
  }
}

// ─── CLI args ────────────────────────────────────────────────────────────────

interface CliArgs {
  db?: string
  ticker?: string
  all?: boolean
  dryRun?: boolean
  verbose?: boolean
}

function parseArgs(): CliArgs {
  const args = Bun.argv.slice(2)
  const flags: CliArgs = {}
  let i = 0
  while (i < args.length) {
    const a = args[i]
    if (a === "--db") flags.db = args[++i]
    else if (a === "--ticker") flags.ticker = args[++i]
    else if (a === "--all") flags.all = true
    else if (a === "--dry-run") flags.dryRun = true
    else if (a === "--verbose" || a === "-v") flags.verbose = true
    i++
  }
  return flags
}

// ─── Main ────────────────────────────────────────────────────────────────────

async function main() {
  const flags = parseArgs()
  const dbPath = resolveDbPath(flags.db)
  const db = DatabaseFactory.connect(dbPath)

  // Auto-apply schema
  const schemaPath = join(__dirname, "..", "server", "lib", "schema.sql")
  if (existsSync(schemaPath)) db.exec(readFileSync(schemaPath, "utf-8"))
  const isTest = dbPath.includes("test")

  console.log(`sync-prices${isTest ? " [TEST MODE]" : ""}`)
  console.log(`  Target DB: ${dbPath}`)

  const results: SyncResult[] = []

  // Fetch FX rates once and build gbp_rate map (GBP per unit of native currency)
  const fx = fetchFxRates()
  const gbpRateMap: GbpRateMap = {
    USD: 1 / fx.GBPUSD, // e.g. 0.787 — GBP per USD
    EUR: 1 / fx.GBPEUR, // e.g. 0.847 — GBP per EUR
    GBP: 1, // no conversion needed
  }
  if (flags.verbose) {
    console.log(
      `  FX: GBPUSD=${fx.GBPUSD} GBPEUR=${fx.GBPEUR} -> gbp_rate map: USD=${gbpRateMap.USD.toFixed(4)} EUR=${gbpRateMap.EUR.toFixed(4)}`,
    )
  }

  if (flags.ticker) {
    // ── Single ticker: catch up
    if (flags.verbose) console.log(`  Mode: catch-up single ticker`)
    const result = catchUpTicker(db, flags.ticker, { dryRun: flags.dryRun, gbpRateMap })
    results.push(result)
  } else if (flags.all) {
    // ── Full sync: gap fill + catch-up for all open positions
    if (flags.verbose) console.log(`  Mode: full sync (gap fill + catch-up)`)

    const tickers = db
      .query(`SELECT DISTINCT ticker FROM positions WHERE status = 'open'`)
      .all() as { ticker: string }[]

    if (tickers.length === 0) {
      console.log(`  No open positions.`)
      return
    }

    for (const { ticker } of tickers) {
      // 1. Detect and fill gaps
      const gaps = detectGaps(db, ticker)
      if (gaps.length > 0) {
        if (flags.verbose) console.log(`  ${ticker}: ${gaps.length} gap(s) detected`)
        for (const gap of gaps) {
          const r = fillGap(db, ticker, gap.from, gap.to, { dryRun: flags.dryRun, gbpRateMap })
          results.push(r)
        }
      }

      // 2. Catch up to today (upsert latest bar if not already there)
      const r = catchUpTicker(db, ticker, { dryRun: flags.dryRun, gbpRateMap })
      results.push(r)
    }
  } else {
    // ── Default: catch up all open positions
    if (flags.verbose) console.log(`  Mode: catch-up all open positions`)

    const tickers = db
      .query(`SELECT DISTINCT ticker FROM positions WHERE status = 'open'`)
      .all() as { ticker: string }[]

    if (tickers.length === 0) {
      console.log(`  No open positions.`)
      return
    }

    for (const { ticker } of tickers) {
      const r = catchUpTicker(db, ticker, { dryRun: flags.dryRun, gbpRateMap })
      results.push(r)
    }
  }

  // ── Summary
  console.log(`\nResults:`)
  let totalUpserted = 0
  let totalErrors = 0

  for (const r of results) {
    if (r.error) {
      console.log(`  ❌ ${r.ticker}: ${r.error}`)
      totalErrors++
    } else {
      console.log(`  ✅ ${r.ticker}: ${r.action} +${r.upserted} bars`)
      totalUpserted += r.upserted
    }
  }

  console.log(
    `\n  Total: ${totalUpserted} bars upserted${totalErrors > 0 ? `, ${totalErrors} errors` : ""}`,
  )
}

main().catch((err) => {
  console.error("sync-prices failed:", err)
  process.exit(1)
})
