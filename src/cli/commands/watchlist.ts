#!/usr/bin/env bun
/**
 * Show watchlist — prospects being tracked but not owned.
 *
 * Usage: trading watchlist
 */

import { defineCommand } from "citty"
import { DatabaseFactory } from "../../lib/db.ts"
import { cfg } from "../../server/lib/settings.ts"

interface WatchlistRow {
  ticker: string
  platform: string
  exchange: string
  thesis: string | null
  priority: string
  stage: string
  added_date: string
  last_signal: string | null
}

export const watchlistCommand = defineCommand({
  meta: {
    name: "watchlist",
    description: "Show prospects being tracked but not owned",
  },
  args: {},
  run: () => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const rows = db
      .query(
        `SELECT ticker, platform, exchange, thesis, priority, stage, added_date, last_signal
         FROM watchlist
         ORDER BY
           CASE priority
             WHEN 'high' THEN 1
             WHEN 'medium' THEN 2
             WHEN 'low' THEN 3
           END,
           ticker`,
      )
      .all() as WatchlistRow[]

    if (rows.length === 0) {
      console.log("Watchlist is empty.")
      console.log("Add tickers via the dashboard or seed data.")
      return
    }

    const wTicker = 12
    const wExch = 8
    const wPriority = 10
    const wStage = 14
    const wAdded = 12
    const wSignal = 14

    const header = `${"Ticker".padEnd(wTicker)} ${"Exch".padEnd(wExch)} ${"Priority".padEnd(wPriority)} ${"Stage".padEnd(wStage)} ${"Added".padEnd(wAdded)} ${"Last Signal".padEnd(wSignal)} Thesis`
    const line = "─".repeat(80)

    console.log("")
    console.log("WATCHLIST")
    console.log(line)
    console.log(header)
    console.log(line)

    for (const r of rows) {
      const thesisShort = r.thesis
        ? r.thesis.length > 35
          ? r.thesis.slice(0, 32) + "..."
          : r.thesis
        : "—"
      const priColor =
        r.priority === "high" ? "\x1b[31m" : r.priority === "medium" ? "\x1b[33m" : "\x1b[0m"
      const reset = "\x1b[0m"
      console.log(
        `${r.ticker.padEnd(wTicker)} ${r.exchange.padEnd(wExch)} ${priColor}${r.priority.padEnd(wPriority)}${reset} ${r.stage.padEnd(wStage)} ${r.added_date.padEnd(wAdded)} ${(r.last_signal ?? "—").padEnd(wSignal)} ${thesisShort}`,
      )
    }

    console.log(line)
    console.log(`  ${rows.length} prospect${rows.length === 1 ? "" : "s"} on watchlist`)
    console.log("")
  },
})
