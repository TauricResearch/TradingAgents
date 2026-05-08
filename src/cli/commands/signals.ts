#!/usr/bin/env bun
/**
 * Show latest AI-generated signals.
 *
 * Usage: trading signals [ticker]
 */

import { defineCommand } from "citty"
import { DatabaseFactory } from "../../lib/db.ts"
import { cfg } from "../../server/lib/settings.ts"

interface SignalRow {
  ticker: string
  platform: string
  date: string
  signal: string
  confidence: string | null
  reasoning: string | null
}

export const signalsCommand = defineCommand({
  meta: {
    name: "signals",
    description: "Show latest AI-generated trading signals",
  },
  args: {
    ticker: {
      type: "positional",
      description: "Filter to a specific ticker",
      required: false,
    },
    limit: {
      type: "string",
      description: "Max signals to show",
      alias: "n",
      default: "20",
    },
  },
  run: ({ args }) => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const limit = parseInt(args.limit, 10)
    const ticker = args.ticker

    let rows: SignalRow[]
    if (ticker) {
      rows = db
        .query(
          `SELECT ticker, platform, date, signal, confidence, reasoning
           FROM signals
           WHERE ticker = ?
           ORDER BY date DESC
           LIMIT ?`,
        )
        .all(ticker, limit) as SignalRow[]
    } else {
      // Latest signal per ticker
      rows = db
        .query(
          `SELECT s.ticker, s.platform, s.date, s.signal, s.confidence, s.reasoning
           FROM signals s
           INNER JOIN (
             SELECT ticker, MAX(date) as max_date
             FROM signals
             GROUP BY ticker
           ) latest ON s.ticker = latest.ticker AND s.date = latest.max_date
           ORDER BY s.date DESC
           LIMIT ?`,
        )
        .all(limit) as SignalRow[]
    }

    if (rows.length === 0) {
      console.log("No signals found.")
      if (ticker) {
        console.log(`Run \`trading analyze ${ticker}\` to generate a signal.`)
      } else {
        console.log("Run `trading analyze <TICKER>` to generate signals.")
      }
      return
    }

    const wTicker = 12
    const wDate = 12
    const wSignal = 14
    const wConf = 12

    const header = `${"Ticker".padEnd(wTicker)} ${"Date".padEnd(wDate)} ${"Signal".padEnd(wSignal)} ${"Confidence".padEnd(wConf)} Reasoning`
    const line = "─".repeat(90)

    console.log("")
    console.log(ticker ? `SIGNALS FOR ${ticker.toUpperCase()}` : "LATEST SIGNALS")
    console.log(line)
    console.log(header)
    console.log(line)

    for (const r of rows) {
      let signalColor = "\x1b[0m"
      if (r.signal === "buy" || r.signal === "overweight") signalColor = "\x1b[32m"
      if (r.signal === "sell" || r.signal === "underweight") signalColor = "\x1b[31m"
      if (r.signal === "hold") signalColor = "\x1b[33m"
      const reset = "\x1b[0m"

      const reasoningShort = r.reasoning
        ? r.reasoning.length > 45
          ? r.reasoning.slice(0, 42) + "..."
          : r.reasoning
        : "—"

      console.log(
        `${r.ticker.padEnd(wTicker)} ${r.date.padEnd(wDate)} ${signalColor}${r.signal.padEnd(wSignal)}${reset} ${(r.confidence ?? "—").padEnd(wConf)} ${reasoningShort}`,
      )
    }

    console.log(line)
    console.log(`  ${rows.length} signal${rows.length === 1 ? "" : "s"}`)
    console.log("")
  },
})
