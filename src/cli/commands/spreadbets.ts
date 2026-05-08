#!/usr/bin/env bun
/**
 * Show spread bet positions.
 *
 * Usage: trading spreadbets
 */

import { defineCommand } from "citty"
import { DatabaseFactory } from "../../lib/db.ts"
import { cfg } from "../../server/lib/settings.ts"

interface SpreadBetRow {
  ticker: string
  direction: string
  stake_per_point: number
  entry_price: number
  entry_date: string
  stop_price: number | null
  target_price: number | null
  current_price: number | null
  pnl_gbp: number | null
  notes: string | null
}

function fmtGBP(n: number | null): string {
  if (n == null) return "—"
  const sign = n < 0 ? "-" : ""
  return `${sign}£${Math.abs(n).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export const spreadbetsCommand = defineCommand({
  meta: {
    name: "spreadbets",
    description: "Show spread bet positions",
  },
  args: {},
  run: () => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const rows = db
      .query(
        `SELECT ticker, direction, stake_per_point, entry_price, entry_date,
                stop_price, target_price, current_price, pnl_gbp, notes
         FROM spreadbet_positions
         WHERE status = 'open'
         ORDER BY ticker`,
      )
      .all() as SpreadBetRow[]

    if (rows.length === 0) {
      console.log("No open spread bet positions.")
      console.log("Open positions via the dashboard or IG API.")
      return
    }

    const wTicker = 12
    const wDir = 6
    const wStake = 10
    const wEntry = 10
    const wCurrent = 10
    const wPnl = 14

    const header = `${"Ticker".padEnd(wTicker)} ${"Dir".padEnd(wDir)} ${"Stake".padStart(wStake)} ${"Entry".padStart(wEntry)} ${"Current".padStart(wCurrent)} ${"P&L".padStart(wPnl)} Notes`
    const line = "─".repeat(90)

    console.log("")
    console.log("SPREAD BET POSITIONS")
    console.log(line)
    console.log(header)
    console.log(line)

    let totalPnl = 0
    for (const r of rows) {
      totalPnl += r.pnl_gbp ?? 0
      const pnlColor = (r.pnl_gbp ?? 0) >= 0 ? "\x1b[32m" : "\x1b[31m"
      const reset = "\x1b[0m"
      const notesShort = r.notes
        ? r.notes.length > 25
          ? r.notes.slice(0, 22) + "..."
          : r.notes
        : "—"

      console.log(
        `${r.ticker.padEnd(wTicker)} ${r.direction.padEnd(wDir)} ${fmtGBP(r.stake_per_point).padStart(wStake)} ${r.entry_price.toFixed(2).padStart(wEntry)} ${(r.current_price?.toFixed(2) ?? "—").padStart(wCurrent)} ${pnlColor}${fmtGBP(r.pnl_gbp).padStart(wPnl)}${reset} ${notesShort}`,
      )
    }

    console.log(line)
    const totalColor = totalPnl >= 0 ? "\x1b[32m" : "\x1b[31m"
    console.log(
      `${"TOTAL".padEnd(wTicker + wDir + wStake + wEntry + wCurrent + 4)} ${totalColor}${fmtGBP(totalPnl).padStart(wPnl)}\x1b[0m`,
    )
    console.log("")
  },
})
