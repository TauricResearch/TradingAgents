#!/usr/bin/env bun
/**
 * CLI: Generate a strategic trade plan for a ticker.
 *
 * Usage:
 *   bun scripts/trade-calculator.ts AAPL --account 50000 --risk 0.02
 *   bun scripts/trade-calculator.ts TKA.DE --entry 45.50 --account 25000
 *
 * Data source: prices table (SQLite) or get_price.ts fallback.
 */

import { DatabaseFactory } from "../src/lib/db.ts"
import { calculateTradePlan } from "../src/lib/trade-calculator.ts"

interface PriceRow {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

function fetchPriceHistory(ticker: string): PriceRow[] {
  const db = DatabaseFactory.get()
  const rows = db
    .query(
      `SELECT date, open, high, low, close, volume
     FROM prices
     WHERE ticker = ?
     ORDER BY date ASC`,
    )
    .all(ticker) as Array<{
    date: string
    open: number | string
    high: number | string
    low: number | string
    close: number | string
    volume: number | string
  }>

  if (rows.length === 0) {
    throw new Error(`No price history for ${ticker}. Run: just sync-prices`)
  }

  return rows.map((r) => ({
    date: r.date,
    open: parseFloat(String(r.open)),
    high: parseFloat(String(r.high)),
    low: parseFloat(String(r.low)),
    close: parseFloat(String(r.close)),
    volume: parseInt(String(r.volume), 10),
  }))
}

function parseArgs(argv: string[]) {
  const args = argv.slice(2)
  const ticker = args[0]
  if (!ticker || ticker.startsWith("--")) {
    throw new Error(
      "Usage: bun scripts/trade-calculator.ts <TICKER> [--account N] [--risk N] [--entry N]",
    )
  }

  let account = 50000
  let risk = 0.02
  let entry: number | undefined

  for (let i = 1; i < args.length; i++) {
    if (args[i] === "--account" && args[i + 1]) account = parseFloat(args[++i])
    if (args[i] === "--risk" && args[i + 1]) risk = parseFloat(args[++i])
    if (args[i] === "--entry" && args[i + 1]) entry = parseFloat(args[++i])
  }

  return { ticker, account, risk, entry }
}

async function main() {
  const { ticker, account, risk, entry } = parseArgs(Bun.argv)

  const dbPath = process.env.PORTFOLIO_DB ?? "./portfolio.db"
  DatabaseFactory.connect(dbPath)

  const history = fetchPriceHistory(ticker)
  const plan = calculateTradePlan({
    ticker,
    priceHistory: history,
    accountBalance: account,
    riskPerTrade: risk,
    entryPrice: entry,
  })

  console.log(JSON.stringify(plan, null, 2))
}

main().catch((e) => {
  console.error(e.message)
  process.exit(1)
})
