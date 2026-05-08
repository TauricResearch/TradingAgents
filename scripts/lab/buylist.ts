#!/usr/bin/env bun
/**
 * Lab: Contingency buylist display
 *
 * Tests layout for watchlist items with fair value targets.
 * Run: bun scripts/lab/buylist.ts
 */

import { gum } from "../lib/gum.ts"

interface BuyItem {
  ticker: string
  exchange: string
  fairValue: number
  currentPrice: number | null
  maxPosition: number | null
  priority: string
  thesis: string
}

const items: BuyItem[] = [
  {
    ticker: "AAPL",
    exchange: "US",
    fairValue: 150.0,
    currentPrice: 165.4,
    maxPosition: 5000,
    priority: "high",
    thesis: "Services growth, PE compression to 22x",
  },
  {
    ticker: "MSFT",
    exchange: "US",
    fairValue: 380.0,
    currentPrice: 410.2,
    maxPosition: 4000,
    priority: "high",
    thesis: "Azure growth, AI integration margin expansion",
  },
  {
    ticker: "NVDA",
    exchange: "US",
    fairValue: 120.0,
    currentPrice: 197.55,
    maxPosition: 3000,
    priority: "medium",
    thesis: "Data centre demand, but priced for perfection",
  },
  {
    ticker: "TKA.DE",
    exchange: "DE",
    fairValue: 8.5,
    currentPrice: 10.76,
    maxPosition: 2000,
    priority: "high",
    thesis: "KONE partnership, German industrial recovery",
  },
  {
    ticker: "VWRL",
    exchange: "LN",
    fairValue: 95.0,
    currentPrice: 108.35,
    maxPosition: 5000,
    priority: "low",
    thesis: "Global diversification, emerging markets exposure",
  },
]

function fmtGBP(n: number): string {
  return `£${n.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtPct(n: number): string {
  const sign = n >= 0 ? "+" : ""
  return `${sign}${(n * 100).toFixed(1)}%`
}

// ── Experiment 1: Fair value proximity table ──────────────────────────────

async function proximityTable() {
  // Sort by proximity to fair value (best opportunities first)
  const sorted = [...items]
    .map((i) => ({
      ...i,
      proximity: i.currentPrice != null ? (i.currentPrice - i.fairValue) / i.fairValue : Infinity,
    }))
    .sort((a, b) => a.proximity - b.proximity)

  const maxTicker = Math.max(6, ...sorted.map((i) => i.ticker.length))

  const lines = [
    `${"Ticker".padEnd(maxTicker + 2)}${"Price".padStart(10)} ${"Fair Value".padStart(12)} ${"Gap".padStart(8)} ${"Max Pos".padStart(12)} ${"Priority".padEnd(10)}`,
    "─".repeat(maxTicker + 56),
  ]

  for (const i of sorted) {
    const priceStr = i.currentPrice != null ? i.currentPrice.toFixed(2) : "—"
    const gapStr = i.currentPrice != null ? fmtPct(i.proximity) : "—"
    const gapColour =
      i.currentPrice != null && i.currentPrice <= i.fairValue ? "\x1b[32m" : "\x1b[0m"
    const posStr = i.maxPosition != null ? fmtGBP(i.maxPosition) : "—"
    const priColour =
      i.priority === "high" ? "\x1b[31m" : i.priority === "medium" ? "\x1b[33m" : "\x1b[0m"
    const reset = "\x1b[0m"

    lines.push(
      `${i.ticker.padEnd(maxTicker + 2)} ${priceStr.padStart(10)} ${i.fairValue.toFixed(2).padStart(12)} ${gapColour}${gapStr.padStart(8)}${reset} ${posStr.padStart(12)} ${priColour}${i.priority.padEnd(10)}${reset}`,
    )
  }

  const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
  const title = await gum("Contingency Buylist", ["--bold", "--foreground", "212"])

  console.log("")
  console.log(`  ${title}`)
  console.log(box)
  console.log(`  \x1b[90mSorted by proximity to fair value — green gap = at or below target\x1b[0m`)
  console.log("")
}

// ── Experiment 2: Detail cards ────────────────────────────────────────────

async function detailCards() {
  const sorted = [...items]
    .map((i) => ({
      ...i,
      proximity: i.currentPrice != null ? (i.currentPrice - i.fairValue) / i.fairValue : Infinity,
    }))
    .sort((a, b) => a.proximity - b.proximity)

  for (const i of sorted) {
    const status =
      i.currentPrice != null && i.currentPrice <= i.fairValue
        ? "\x1b[32m● AT BUY PRICE\x1b[0m"
        : i.currentPrice != null && (i.currentPrice - i.fairValue) / i.fairValue <= 0.05
          ? "\x1b[33m● APPROACHING\x1b[0m"
          : "\x1b[90m○ WATCHING\x1b[0m"

    const card = [
      `${i.ticker}  ${status}`,
      `  Price: ${i.currentPrice?.toFixed(2) ?? "—"}  ·  Fair: ${i.fairValue.toFixed(2)}  ·  Gap: ${i.currentPrice != null ? fmtPct((i.currentPrice - i.fairValue) / i.fairValue) : "—"}`,
      `  Max position: ${i.maxPosition != null ? fmtGBP(i.maxPosition) : "—"}  ·  Priority: ${i.priority}`,
      `  Thesis: ${i.thesis}`,
    ].join("\n")

    const box = await gum(card, ["--border", "rounded", "--padding", "0 1"])
    console.log("")
    console.log(box)
  }
  console.log("")
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  console.log("\x1b[2J\x1b[H")
  console.log("═══ Lab: Contingency Buylist ═══")
  console.log("")

  await proximityTable()
  await detailCards()
}

main()
