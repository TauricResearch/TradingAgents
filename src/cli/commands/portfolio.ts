#!/usr/bin/env bun

/**
 * Portfolio holdings and P&L summary.
 *
 * Reads from SQLite (positions + prices + accounts).
 * Usage: trading portfolio
 */

import { DatabaseFactory } from "@lib/db"
import { cfg } from "@lib/settings"
import { defineCommand } from "citty"
import { gum } from "../../../scripts/lib/gum.ts"

interface PositionRow {
  ticker: string
  exchange: string
  platform: string
  quantity: number
  avg_cost: number
  entry_date: string
}

interface PriceRow {
  close: number
  currency: string
  gbp_rate: number | null
}

interface AccountRow {
  id: string
  provider: string
  account_type: string
  name: string
  balance: number
  currency: string
}

function fmtGBP(n: number | null): string {
  if (n == null) return "—"
  const sign = n < 0 ? "-" : ""
  const abs = Math.abs(n)
  return `${sign}£${abs.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtPct(n: number | null): string {
  if (n == null) return "—"
  const sign = n >= 0 ? "+" : ""
  return `${sign}${(n * 100).toFixed(1)}%`
}

export const portfolioCommand = defineCommand({
  meta: {
    name: "portfolio",
    description: "Show portfolio holdings, P&L, and cash summary",
  },
  args: {},
  run: async () => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    // ── Fetch data ──────────────────────────────────────────────────────────

    const positions = db
      .query(
        `SELECT ticker, exchange, platform, quantity, avg_cost, entry_date
         FROM positions
         WHERE status = 'open'
         ORDER BY platform, ticker`,
      )
      .all() as PositionRow[]

    if (positions.length === 0) {
      console.log("No open positions.")
      console.log("Run `trading seed --positions` to add test data.")
      return
    }

    // Latest price per ticker
    const tickers = [...new Set(positions.map((p) => p.ticker))]
    const priceMap = new Map<string, PriceRow>()
    for (const ticker of tickers) {
      const row = db
        .query(
          `SELECT close, currency, gbp_rate
           FROM prices
           WHERE ticker = ?
           ORDER BY date DESC
           LIMIT 1`,
        )
        .get(ticker) as PriceRow | null
      if (row) priceMap.set(ticker, row)
    }

    // Accounts
    const accounts = db
      .query(
        `SELECT id, provider, account_type, name, balance, currency
         FROM accounts
         ORDER BY balance DESC`,
      )
      .all() as AccountRow[]

    // ── Compute P&L ─────────────────────────────────────────────────────────

    let totalCostGBP = 0
    let totalValueGBP = 0

    const rows: Array<{
      ticker: string
      platform: string
      qty: number
      avgCost: number
      price: number | null
      costGBP: number
      valueGBP: number
      pnlGBP: number
      pnlPct: number | null
      currency: string
    }> = []

    for (const pos of positions) {
      const priceRow = priceMap.get(pos.ticker)
      const price = priceRow?.close ?? null
      const gbpRate = priceRow?.gbp_rate ?? (priceRow?.currency === "GBP" ? 1 : null)
      const currency = priceRow?.currency ?? "?"

      const costGBP = pos.quantity * pos.avg_cost * (gbpRate ?? 1)
      const valueGBP = price != null && gbpRate != null ? pos.quantity * price * gbpRate : null
      const pnlGBP = valueGBP != null ? valueGBP - costGBP : null
      const pnlPct = valueGBP != null && costGBP > 0 ? (valueGBP - costGBP) / costGBP : null

      totalCostGBP += costGBP
      if (valueGBP != null) totalValueGBP += valueGBP

      rows.push({
        ticker: pos.ticker,
        platform: pos.platform,
        qty: pos.quantity,
        avgCost: pos.avg_cost,
        price,
        costGBP,
        valueGBP: valueGBP ?? 0,
        pnlGBP: pnlGBP ?? 0,
        pnlPct,
        currency,
      })
    }

    // ── Print positions table (Gum-styled) ────────────────────────────────

    const maxTicker = Math.max(6, ...rows.map((r) => r.ticker.length))
    const maxPlatform = Math.max(8, ...rows.map((r) => r.platform.length))

    const totalPnlGBP = totalValueGBP - totalCostGBP
    const totalPnlPct = totalCostGBP > 0 ? totalPnlGBP / totalCostGBP : null

    const posLines = [
      `${"Ticker".padEnd(maxTicker + 2)}${"Platform".padEnd(maxPlatform + 2)}${"Qty".padStart(6)} ${"Price".padStart(10)} ${"Cost".padStart(14)} ${"Value".padStart(14)} ${"P&L".padStart(14)} ${"%".padStart(8)}`,
      "─".repeat(maxTicker + maxPlatform + 78),
    ]

    for (const r of rows) {
      const pnlColour = r.pnlGBP >= 0 ? "\x1b[32m" : "\x1b[31m"
      const reset = "\x1b[0m"
      const priceStr = r.price != null ? r.price.toFixed(2) : "—"
      posLines.push(
        `${r.ticker.padEnd(maxTicker + 2)}${r.platform.padEnd(maxPlatform + 2)}${String(r.qty).padStart(6)} ${priceStr.padStart(10)} ${fmtGBP(r.costGBP).padStart(14)} ${fmtGBP(r.valueGBP).padStart(14)} ${pnlColour}${fmtGBP(r.pnlGBP).padStart(14)}${reset} ${fmtPct(r.pnlPct).padStart(8)}`,
      )
    }

    posLines.push("─".repeat(maxTicker + maxPlatform + 78))
    posLines.push(
      `${"TOTAL".padEnd(maxTicker + maxPlatform + 20)} ${fmtGBP(totalCostGBP).padStart(14)} ${fmtGBP(totalValueGBP).padStart(14)} ${totalPnlGBP >= 0 ? "\x1b[32m" : "\x1b[31m"}${fmtGBP(totalPnlGBP).padStart(14)}\x1b[0m ${fmtPct(totalPnlPct).padStart(8)}`,
    )

    const box = await gum(posLines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
    const title = await gum("Portfolio", ["--bold", "--foreground", "212"])

    console.log("")
    console.log(`  ${title}`)
    console.log(box)

    // ── Print cash summary ───────────────────────────────────────────────────

    let totalCash = 0
    const cashTitle = await gum("Cash & Accounts", ["--bold", "--foreground", "250"])
    console.log(`  ${cashTitle}`)

    const cashLine = "─".repeat(54)
    console.log(`  ${cashLine}`)
    console.log(`  ${"Account".padEnd(28)} ${"Type".padEnd(12)} ${"Balance".padStart(14)}`)
    console.log(`  ${cashLine}`)
    for (const ac of accounts) {
      totalCash += ac.balance
      console.log(
        `  ${ac.name.padEnd(28)} ${ac.account_type.padEnd(12)} ${fmtGBP(ac.balance).padStart(14)}`,
      )
    }
    console.log(`  ${cashLine}`)
    console.log(`  ${"TOTAL CASH".padEnd(40)} ${fmtGBP(totalCash).padStart(14)}`)
    console.log("")

    // ── Print net worth summary ────────────────────────────────────────────

    const netWorth = totalValueGBP + totalCash
    const nwTitle = await gum("Net Worth", ["--bold", "--foreground", "250"])
    console.log(`  ${nwTitle}`)
    console.log(`  ${cashLine}`)
    console.log(`  ${"Investments:".padEnd(16)} ${fmtGBP(totalValueGBP).padStart(14)}`)
    console.log(`  ${"Cash:".padEnd(16)} ${fmtGBP(totalCash).padStart(14)}`)
    console.log(`  ${cashLine}`)
    console.log(`  ${"Total:".padEnd(16)} ${fmtGBP(netWorth).padStart(14)}`)
    console.log("")
  },
})
