#!/usr/bin/env bun
/**
 * Show trade history.
 *
 * Usage: trading trades [ticker]
 */

import { defineCommand } from "citty"
import { DatabaseFactory } from "../../lib/db.ts"
import { cfg } from "../../server/lib/settings.ts"

interface TradeRow {
  ticker: string
  action: string
  quantity: number
  price: number
  date: string
  reason: string | null
  fees: number | null
}

function fmtGBP(n: number | null): string {
  if (n == null) return "—"
  return `£${n.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export const tradesCommand = defineCommand({
  meta: {
    name: "trades",
    description: "Show trade history",
  },
  args: {
    ticker: {
      type: "positional",
      description: "Filter to a specific ticker",
      required: false,
    },
    limit: {
      type: "string",
      description: "Max trades to show",
      alias: "n",
      default: "30",
    },
  },
  run: ({ args }) => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const limit = parseInt(args.limit, 10)
    const ticker = args.ticker

    let rows: TradeRow[]
    if (ticker) {
      rows = db
        .query(
          `SELECT ticker, action, quantity, price, date, reason, fees
           FROM trades
           WHERE ticker = ?
           ORDER BY date DESC
           LIMIT ?`,
        )
        .all(ticker, limit) as TradeRow[]
    } else {
      rows = db
        .query(
          `SELECT ticker, action, quantity, price, date, reason, fees
           FROM trades
           ORDER BY date DESC
           LIMIT ?`,
        )
        .all(limit) as TradeRow[]
    }

    if (rows.length === 0) {
      console.log("No trades found.")
      console.log("Trades are recorded when you execute orders via `trading execute`.")
      return
    }

    const wDate = 12
    const wTicker = 12
    const wAction = 8
    const wQty = 8
    const wPrice = 12
    const wFees = 10

    const header = `${"Date".padEnd(wDate)} ${"Ticker".padEnd(wTicker)} ${"Action".padEnd(wAction)} ${"Qty".padStart(wQty)} ${"Price".padStart(wPrice)} ${"Fees".padStart(wFees)} Reason`
    const line = "─".repeat(90)

    console.log("")
    console.log(ticker ? `TRADES FOR ${ticker.toUpperCase()}` : "TRADE HISTORY")
    console.log(line)
    console.log(header)
    console.log(line)

    for (const r of rows) {
      const actionColor = r.action === "buy" ? "\x1b[32m" : "\x1b[31m"
      const reset = "\x1b[0m"
      const reasonShort = r.reason
        ? r.reason.length > 35
          ? `${r.reason.slice(0, 32)}...`
          : r.reason
        : "—"

      console.log(
        `${r.date.padEnd(wDate)} ${r.ticker.padEnd(wTicker)} ${actionColor}${r.action.padEnd(wAction)}${reset} ${String(r.quantity).padStart(wQty)} ${fmtGBP(r.price).padStart(wPrice)} ${fmtGBP(r.fees ?? 0).padStart(wFees)} ${reasonShort}`,
      )
    }

    console.log(line)

    // Summary stats
    const buys = rows.filter((r) => r.action === "buy")
    const sells = rows.filter((r) => r.action === "sell")
    const totalBuyValue = buys.reduce((sum, r) => sum + r.quantity * r.price + (r.fees ?? 0), 0)
    const totalSellValue = sells.reduce((sum, r) => sum + r.quantity * r.price - (r.fees ?? 0), 0)

    console.log(
      `  ${rows.length} trade${rows.length === 1 ? "" : "s"}: ${buys.length} buy, ${sells.length} sell`,
    )
    console.log(`  Total buy value:  ${fmtGBP(totalBuyValue)}`)
    console.log(`  Total sell value: ${fmtGBP(totalSellValue)}`)
    console.log("")
  },
})
