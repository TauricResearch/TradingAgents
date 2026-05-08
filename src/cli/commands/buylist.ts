#!/usr/bin/env bun
/**
 * Contingency buylist — watchlist items with fair value targets.
 *
 * Shows prospects at or near their target buy price.
 * Sorted by proximity to fair value (best opportunities first).
 *
 * Usage:
 *   trading buylist              # show buylist
 *   trading buylist --fetch      # fetch missing prices from Yahoo Finance
 *   trading buylist --json       # machine-readable output
 */

import { defineCommand } from "citty"
import { gum } from "../../../scripts/lib/gum.ts"
import { DatabaseFactory } from "../../lib/db.ts"
import { cfg } from "../../server/lib/settings.ts"

interface BuyItem {
  ticker: string
  exchange: string
  fairValue: number | null
  maxPosition: number | null
  priority: string
  thesis: string | null
  currentPrice: number | null
}

interface BuyItemWithPrice extends BuyItem {
  currentPrice: number
  fairValue: number
}

function hasPriceAndFairValue(item: BuyItem): item is BuyItemWithPrice {
  return item.currentPrice != null && item.fairValue != null
}

function fmtGBP(n: number | null): string {
  if (n == null) return "—"
  return `£${n.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtPct(n: number): string {
  const sign = n >= 0 ? "+" : ""
  return `${sign}${(n * 100).toFixed(1)}%`
}

function latestPrice(db: ReturnType<typeof DatabaseFactory.get>, ticker: string): number | null {
  const row = db
    .query<{ close: number }, [string]>(
      "SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
    )
    .get(ticker)
  return row ? row.close : null
}

async function fetchPrice(ticker: string): Promise<number | null> {
  try {
    const proc = Bun.spawn({
      cmd: ["bun", "run", "scripts/get_price.ts", ticker],
      stdout: "pipe",
      stderr: "pipe",
    })
    const text = await new Response(proc.stdout).text()
    const data = JSON.parse(text)
    return data.price ?? null
  } catch {
    return null
  }
}

function loadBuylist(db: ReturnType<typeof DatabaseFactory.get>): BuyItem[] {
  const rows = db
    .query<
      {
        ticker: string
        exchange: string
        fair_value: number | null
        max_position_gbp: number | null
        priority: string
        thesis: string | null
      },
      []
    >(
      `SELECT ticker, exchange, fair_value, max_position_gbp, priority, thesis
       FROM watchlist
       WHERE fair_value IS NOT NULL
       ORDER BY ticker`,
    )
    .all()

  return rows.map((r) => ({
    ticker: r.ticker,
    exchange: r.exchange,
    fairValue: r.fair_value,
    maxPosition: r.max_position_gbp,
    priority: r.priority,
    thesis: r.thesis,
    currentPrice: null,
  }))
}

// ── Display ────────────────────────────────────────────────────────────────

async function displayGum(items: BuyItem[]) {
  if (items.length === 0) {
    console.log("No contingency buylist items.")
    console.log("Set fair_value on watchlist items to add them to the buylist.")
    return
  }

  const sorted = items
    .map((i) => ({
      ...i,
      proximity:
        i.currentPrice != null && i.fairValue != null
          ? (i.currentPrice - i.fairValue) / i.fairValue
          : Infinity,
    }))
    .sort((a, b) => a.proximity - b.proximity)

  const atBuyPrice = sorted.filter(
    (i): i is BuyItemWithPrice => hasPriceAndFairValue(i) && i.currentPrice <= i.fairValue,
  )
  const approaching = sorted.filter(
    (i): i is BuyItemWithPrice =>
      hasPriceAndFairValue(i) &&
      i.currentPrice > i.fairValue &&
      (i.currentPrice - i.fairValue) / i.fairValue <= 0.05,
  )

  // Summary header
  const summaryParts: string[] = []
  if (atBuyPrice.length > 0) summaryParts.push(`${atBuyPrice.length} at buy price`)
  if (approaching.length > 0) summaryParts.push(`${approaching.length} approaching`)
  summaryParts.push(`${sorted.length} total`)
  const summary = summaryParts.join("  ·  ")

  const header = await gum(summary, ["--foreground", "250", "--width", "60", "--align", "center"])
  console.log("")
  console.log(header)

  // ── Active alerts ───────────────────────────────────────────────────
  if (atBuyPrice.length > 0) {
    const title = await gum("At Buy Price", ["--bold", "--foreground", "32"])
    console.log(`  ${title}`)

    const maxTicker = Math.max(...atBuyPrice.map((i) => i.ticker.length))
    const headerLine = `${"Ticker".padEnd(maxTicker + 2)}${"Price".padStart(10)} ${"Fair Value".padStart(12)} ${"P&L".padStart(12)} ${"Max Pos".padStart(12)}`
    const lines = [headerLine, "─".repeat(headerLine.length + 4)]

    for (const i of atBuyPrice) {
      lines.push(
        `\x1b[32m●\x1b[0m ${i.ticker.padEnd(maxTicker + 1)} ${i.currentPrice.toFixed(2).padStart(10)} ${i.fairValue.toFixed(2).padStart(12)} ${fmtGBP(i.currentPrice - i.fairValue).padStart(12)} ${fmtGBP(i.maxPosition).padStart(12)}`,
      )
    }

    const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
    console.log(box)
    console.log("")
  }

  // ── Full table ────────────────────────────────────────────────────────
  const tableTitle = await gum("All Buylist Items", ["--bold", "--foreground", "212"])
  console.log(`  ${tableTitle}`)

  const maxTicker = Math.max(6, ...sorted.map((i) => i.ticker.length))
  const headerLine = `${"Ticker".padEnd(maxTicker + 2)}${"Price".padStart(10)} ${"Fair Value".padStart(12)} ${"Gap".padStart(8)} ${"Max Pos".padStart(12)} ${"Priority".padEnd(10)}`
  const lines = [headerLine, "─".repeat(maxTicker + 58)]

  for (const i of sorted) {
    const priceStr = i.currentPrice != null ? i.currentPrice.toFixed(2) : "—"
    const fairStr = i.fairValue != null ? i.fairValue.toFixed(2) : "—"
    const gapStr = i.currentPrice != null && i.fairValue != null ? fmtPct(i.proximity) : "—"
    const gapColour =
      i.currentPrice != null && i.fairValue != null && i.currentPrice <= i.fairValue
        ? "\x1b[32m"
        : "\x1b[0m"
    const reset = "\x1b[0m"
    const posStr = fmtGBP(i.maxPosition)
    const priColour =
      i.priority === "high" ? "\x1b[31m" : i.priority === "medium" ? "\x1b[33m" : "\x1b[0m"

    lines.push(
      `${priColour}●${reset} ${i.ticker.padEnd(maxTicker + 1)} ${priceStr.padStart(10)} ${fairStr.padStart(12)} ${gapColour}${gapStr.padStart(8)}${reset} ${posStr.padStart(12)} ${priColour}${i.priority.padEnd(10)}${reset}`,
    )
  }

  const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
  console.log(box)
  console.log(
    `  \x1b[90mSorted by proximity to fair value  ·  ● red = high priority  ·  green gap = at or below target\x1b[0m`,
  )
  console.log("")
}

function displayJson(items: BuyItem[]) {
  const sorted = items
    .map((i) => ({
      ...i,
      proximity:
        i.currentPrice != null && i.fairValue != null
          ? (i.currentPrice - i.fairValue) / i.fairValue
          : null,
    }))
    .sort((a, b) => (a.proximity ?? Infinity) - (b.proximity ?? Infinity))

  console.log(JSON.stringify(sorted, null, 2))
}

// ── Command ────────────────────────────────────────────────────────────────

export const buylistCommand = defineCommand({
  meta: {
    name: "buylist",
    description: "Contingency buylist — watchlist items with fair value targets",
  },
  args: {
    fetch: {
      type: "boolean",
      description: "Fetch missing prices from Yahoo Finance",
      default: false,
    },
    json: {
      type: "boolean",
      description: "Output as JSON",
      default: false,
    },
  },
  run: async ({ args }) => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const items = loadBuylist(db)
    if (items.length === 0) {
      console.log("No contingency buylist items.")
      console.log(
        "Set fair_value on watchlist items: UPDATE watchlist SET fair_value = ... WHERE ticker = ...",
      )
      return
    }

    // Fetch prices
    for (const item of items) {
      let price = latestPrice(db, item.ticker)
      if (price == null && args.fetch) {
        price = await fetchPrice(item.ticker)
      }
      item.currentPrice = price
    }

    if (args.json) {
      displayJson(items)
    } else {
      await displayGum(items)
    }
  },
})
