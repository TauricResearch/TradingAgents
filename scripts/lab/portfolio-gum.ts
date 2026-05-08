#!/usr/bin/env bun
/**
 * Lab: Portfolio display with Gum styling
 *
 * Tests layout for a multi-column financial table.
 * Run: bun scripts/lab/portfolio-gum.ts
 */

import { gum } from "../lib/gum.ts"

interface Row {
  ticker: string
  platform: string
  qty: number
  price: number | null
  cost: number
  value: number
  pnl: number
  pnlPct: number | null
}

const rows: Row[] = [
  {
    ticker: "TKA.DE",
    platform: "ig-shares",
    qty: 115,
    price: 10.76,
    cost: 994.07,
    value: 1048.64,
    pnl: 54.58,
    pnlPct: 0.055,
  },
  {
    ticker: "TKMS.DE",
    platform: "ig-shares",
    qty: 5,
    price: 76.9,
    cost: 0,
    value: 325.85,
    pnl: 325.85,
    pnlPct: null,
  },
  {
    ticker: "AAPL",
    platform: "degiro",
    qty: 50,
    price: 195.42,
    cost: 8500.0,
    value: 9771.0,
    pnl: 1271.0,
    pnlPct: 0.1495,
  },
  {
    ticker: "VWRL",
    platform: "isa",
    qty: 200,
    price: 108.35,
    cost: 18500.0,
    value: 21670.0,
    pnl: 3170.0,
    pnlPct: 0.171,
  },
]

function fmtGBP(n: number): string {
  const sign = n < 0 ? "-" : ""
  return `${sign}£${Math.abs(n).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtPct(n: number | null): string {
  if (n == null) return "—"
  const sign = n >= 0 ? "+" : ""
  return `${sign}${(n * 100).toFixed(1)}%`
}

// ── Experiment: Single bordered table ────────────────────────────────────

async function singleTable() {
  const maxTicker = Math.max(...rows.map((r) => r.ticker.length))
  const maxPlatform = Math.max(...rows.map((r) => r.platform.length))

  const lines = [
    `${"Ticker".padEnd(maxTicker + 2)}${"Platform".padEnd(maxPlatform + 2)}${"Qty".padStart(6)} ${"Price".padStart(10)} ${"Cost".padStart(14)} ${"Value".padStart(14)} ${"P&L".padStart(14)} ${"%".padStart(8)}`,
    "─".repeat(maxTicker + maxPlatform + 78),
  ]

  for (const r of rows) {
    const pnlColour = r.pnl >= 0 ? "\x1b[32m" : "\x1b[31m"
    const reset = "\x1b[0m"
    const priceStr = r.price != null ? r.price.toFixed(2) : "—"
    lines.push(
      `${r.ticker.padEnd(maxTicker + 2)}${r.platform.padEnd(maxPlatform + 2)}${String(r.qty).padStart(6)} ${priceStr.padStart(10)} ${fmtGBP(r.cost).padStart(14)} ${fmtGBP(r.value).padStart(14)} ${pnlColour}${fmtGBP(r.pnl).padStart(14)}${reset} ${fmtPct(r.pnlPct).padStart(8)}`,
    )
  }

  const body = lines.join("\n")
  const box = await gum(body, ["--border", "rounded", "--padding", "1 2"])
  const title = await gum("Portfolio Holdings", ["--bold", "--foreground", "212"])

  console.log("")
  console.log(`  ${title}`)
  console.log(box)
  console.log("")
}

// ── Experiment: Separate sections ────────────────────────────────────────

async function sections() {
  // Positions table
  const maxTicker = Math.max(...rows.map((r) => r.ticker.length))
  const maxPlatform = Math.max(...rows.map((r) => r.platform.length))

  const posLines = [
    `${"Ticker".padEnd(maxTicker + 2)}${"Platform".padEnd(maxPlatform + 2)}${"Qty".padStart(6)} ${"Price".padStart(10)} ${"Cost".padStart(14)} ${"Value".padStart(14)} ${"P&L".padStart(14)} ${"%".padStart(8)}`,
    "─".repeat(maxTicker + maxPlatform + 78),
  ]

  let totalCost = 0
  let totalValue = 0
  for (const r of rows) {
    totalCost += r.cost
    totalValue += r.value
    const pnlColour = r.pnl >= 0 ? "\x1b[32m" : "\x1b[31m"
    const reset = "\x1b[0m"
    const priceStr = r.price != null ? r.price.toFixed(2) : "—"
    posLines.push(
      `${r.ticker.padEnd(maxTicker + 2)}${r.platform.padEnd(maxPlatform + 2)}${String(r.qty).padStart(6)} ${priceStr.padStart(10)} ${fmtGBP(r.cost).padStart(14)} ${fmtGBP(r.value).padStart(14)} ${pnlColour}${fmtGBP(r.pnl).padStart(14)}${reset} ${fmtPct(r.pnlPct).padStart(8)}`,
    )
  }

  const totalPnl = totalValue - totalCost
  const totalPnlPct = totalCost > 0 ? totalPnl / totalCost : null
  posLines.push("─".repeat(maxTicker + maxPlatform + 78))
  posLines.push(
    `${"TOTAL".padEnd(maxTicker + maxPlatform + 20)} ${fmtGBP(totalCost).padStart(14)} ${fmtGBP(totalValue).padStart(14)} ${totalPnl >= 0 ? "\x1b[32m" : "\x1b[31m"}${fmtGBP(totalPnl).padStart(14)}\x1b[0m ${fmtPct(totalPnlPct).padStart(8)}`,
  )

  const box = await gum(posLines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
  const title = await gum("Portfolio", ["--bold", "--foreground", "212"])

  // Cash summary — plain text, no border
  const cashLines = [
    "",
    "  Cash & Accounts",
    "  " + "─".repeat(40),
    `  ${"Aviva SIPP".padEnd(28)} ${fmtGBP(134761.89).padStart(14)}`,
    `  ${"AJBell SIPP".padEnd(28)} ${fmtGBP(108221.44).padStart(14)}`,
    `  ${"IG ISA".padEnd(28)} ${fmtGBP(20868.5).padStart(14)}`,
    "  " + "─".repeat(40),
    `  ${"TOTAL CASH".padEnd(28)} ${fmtGBP(325508.96).padStart(14)}`,
    "",
    "  Net Worth",
    "  " + "─".repeat(40),
    `  Investments:  ${fmtGBP(totalValue).padStart(14)}`,
    `  Cash:         ${fmtGBP(325508.96).padStart(14)}`,
    `  ${"─".repeat(40)}`,
    `  Total:        ${fmtGBP(totalValue + 325508.96).padStart(14)}`,
    "",
  ]

  console.log("")
  console.log(`  ${title}`)
  console.log(box)
  for (const line of cashLines) console.log(line)
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  console.log("\x1b[2J\x1b[H")
  console.log("═══ Experiment 1: Single bordered table ═══")
  await singleTable()

  console.log("═══ Experiment 2: Bordered positions + plain cash/net worth ═══")
  await sections()
}

main()
