#!/usr/bin/env bun

/**
 * Show watchlist — prospects being tracked but not owned.
 *
 * Usage: trading watchlist
 */

import { DatabaseFactory } from "@lib/db"
import { cfg } from "@lib/settings"
import { defineCommand } from "citty"

interface WatchlistRow {
  ticker: string
  platform: string
  exchange: string
  thesis: string | null
  priority: string
  stage: string
  added_date: string
  last_signal: string | null
  research_doc: string | null
  last_research_update: string | null
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
        `SELECT ticker, platform, exchange, thesis, priority, stage, added_date, last_signal, research_doc, last_research_update
         FROM watchlist
         ORDER BY
           CASE WHEN research_doc IS NULL THEN 1 ELSE 0 END,
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

    const wTicker = 8
    const wExch = 7
    const wPriority = 9
    const wStage = 12
    const wResearch = 16
    const wUpdated = 12
    const wThesis = 22

    const header = `${"Ticker".padEnd(wTicker)} ${"Exch".padEnd(wExch)} ${"Pri".padEnd(wPriority)} ${"Stage".padEnd(wStage)} ${"Research Doc".padEnd(wResearch)} ${"Updated".padEnd(wUpdated)} Thesis`
    const line = "─".repeat(100)

    console.log("")
    console.log("WATCHLIST")
    console.log(line)
    console.log(header)
    console.log(line)

    let staleCount = 0
    for (const r of rows) {
      const stale = !r.research_doc
      if (stale) staleCount++
      const thesisShort = r.thesis
        ? r.thesis.length > wThesis
          ? `${r.thesis.slice(0, wThesis - 3)}...`
          : r.thesis
        : "—"
      const priColor =
        r.priority === "high" ? "\x1b[31m" : r.priority === "medium" ? "\x1b[33m" : "\x1b[0m"
      const reset = "\x1b[0m"
      const docStr = r.research_doc ?? "\x1b[33munlinked\x1b[0m"
      const updatedStr = r.last_research_update ?? "—"
      const staleFlag = stale ? " \x1b[33m⚠\x1b[0m" : ""

      console.log(
        `${r.ticker.padEnd(wTicker)} ${r.exchange.padEnd(wExch)} ${priColor}${r.priority.padEnd(wPriority)}${reset} ${r.stage.padEnd(wStage)} ${docStr.padEnd(wResearch)} ${updatedStr.padEnd(wUpdated)} ${thesisShort}${staleFlag}`,
      )
    }

    console.log(line)
    console.log(`  ${rows.length} prospect${rows.length === 1 ? "" : "s"} on watchlist`)
    if (staleCount > 0) {
      console.log(
        `  ${staleCount} stale (no research doc — run 'trading research coverage' for details)`,
      )
    }
    console.log("")
  },
})
