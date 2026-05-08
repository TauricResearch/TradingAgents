#!/usr/bin/env bun
/**
 * Portfolio holdings and P&L summary.
 *
 * Reads from SQLite (positions + prices + accounts).
 * Usage: trading portfolio
 */

import { defineCommand } from "citty"
import { DatabaseFactory } from "../../lib/db.ts"
import { cfg } from "../../server/lib/settings.ts"

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
  run: () => {
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

    // ── Print positions table ────────────────────────────────────────────────

    const wTicker = 12
    const wPlatform = 10
    const wQty = 6
    const wPrice = 10
    const wCost = 14
    const wValue = 14
    const wPnl = 14
    const wPct = 8

    const header = `${"Ticker".padEnd(wTicker)} ${"Platform".padEnd(wPlatform)} ${"Qty".padStart(wQty)} ${"Price".padStart(wPrice)} ${"Cost".padStart(wCost)} ${"Value".padStart(wValue)} ${"P&L".padStart(wPnl)} ${"%".padStart(wPct)}`
    const line = "─".repeat(header.length)

    console.log("")
    console.log("PORTFOLIO HOLDINGS")
    console.log(line)
    console.log(header)
    console.log(line)

    for (const r of rows) {
      const priceStr = r.price != null ? r.price.toFixed(2) : "—"
      const pnlStr = fmtGBP(r.pnlGBP)
      const pnlColor = r.pnlGBP >= 0 ? "\x1b[32m" : "\x1b[31m"
      const reset = "\x1b[0m"
      console.log(
        `${r.ticker.padEnd(wTicker)} ${r.platform.padEnd(wPlatform)} ${String(r.qty).padStart(wQty)} ${priceStr.padStart(wPrice)} ${fmtGBP(r.costGBP).padStart(wCost)} ${fmtGBP(r.valueGBP).padStart(wValue)} ${pnlColor}${pnlStr.padStart(wPnl)}${reset} ${fmtPct(r.pnlPct).padStart(wPct)}`,
      )
    }

    console.log(line)

    const totalPnlGBP = totalValueGBP - totalCostGBP
    const totalPnlPct = totalCostGBP > 0 ? totalPnlGBP / totalCostGBP : null
    console.log(
      `${"TOTAL".padEnd(wTicker + wPlatform + wQty + wPrice + 3)} ${fmtGBP(totalCostGBP).padStart(wCost)} ${fmtGBP(totalValueGBP).padStart(wValue)} ${totalPnlGBP >= 0 ? "\x1b[32m" : "\x1b[31m"}${fmtGBP(totalPnlGBP).padStart(wPnl)}\x1b[0m ${fmtPct(totalPnlPct).padStart(wPct)}`,
    )
    console.log("")

    // ── Print cash summary ───────────────────────────────────────────────────

    let totalCash = 0
    console.log("CASH & ACCOUNTS")
    console.log(line)
    console.log(`${"Account".padEnd(28)} ${"Type".padEnd(12)} ${"Balance".padStart(14)}`)
    console.log(line)
    for (const ac of accounts) {
      totalCash += ac.balance
      console.log(
        `${ac.name.padEnd(28)} ${ac.account_type.padEnd(12)} ${fmtGBP(ac.balance).padStart(14)}`,
      )
    }
    console.log(line)
    console.log(`${"TOTAL CASH".padEnd(28 + 12)} ${fmtGBP(totalCash).padStart(14)}`)
    console.log("")

    // ── Print net worth summary ────────────────────────────────────────────

    const netWorth = totalValueGBP + totalCash
    console.log("NET WORTH SUMMARY")
    console.log(`  Investments: ${fmtGBP(totalValueGBP)}`)
    console.log(`  Cash:        ${fmtGBP(totalCash)}`)
    console.log(`  ──────────────────────`)
    console.log(`  Total:       ${fmtGBP(netWorth)}`)
    console.log("")
  },
})
