#!/usr/bin/env bun

/**
 * Quick price lookup for a ticker.
 *
 * Delegates to scripts/py/get_price.py
 * Usage: trading prices <ticker>
 */

import { existsSync } from "node:fs"
import { join } from "node:path"
import { defineCommand } from "citty"

interface PriceResult {
  ticker: string
  price: number | null
  currency: string
  previousClose: number | null
  dayHigh: number | null
  dayLow: number | null
  volume: number | null
  history: { date: string; close: number }[]
  timestamp: string
}

export const pricesCommand = defineCommand({
  meta: {
    name: "prices",
    description: "Quick price lookup for a ticker",
  },
  args: {
    ticker: {
      type: "positional",
      description: "Stock ticker (e.g. AAPL, TKA.DE, VWCE.DE)",
      required: true,
    },
  },
  run: async ({ args }) => {
    const ticker = args.ticker
    const script = join(process.cwd(), "scripts", "py", "get_price.py")

    if (!existsSync(script)) {
      console.error(`❌ Error: get_price.py not found at ${script}`)
      process.exit(1)
    }

    const proc = Bun.spawn(["python3", script, ticker], {
      stdout: "pipe",
      stderr: "pipe",
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    })

    let stdout = ""
    let stderr = ""

    for await (const chunk of proc.stdout) {
      stdout += new TextDecoder().decode(chunk)
    }
    for await (const chunk of proc.stderr) {
      stderr += new TextDecoder().decode(chunk)
    }

    const exitCode = await proc.exited
    if (exitCode !== 0) {
      console.error(`❌ Price lookup failed for ${ticker}`)
      if (stderr) console.error(stderr.trim())
      process.exit(1)
    }

    let data: PriceResult
    try {
      data = JSON.parse(stdout.trim())
    } catch {
      console.error(`❌ Failed to parse price response for ${ticker}`)
      process.exit(1)
    }

    if (data.price == null) {
      console.log(`❌ No price data available for ${ticker}`)
      return
    }

    const change = data.previousClose != null ? data.price - data.previousClose : null
    const changePct =
      data.previousClose != null && data.previousClose !== 0 && change != null
        ? change / data.previousClose
        : null

    const changeStr =
      change != null
        ? `${change >= 0 ? "+" : ""}${change.toFixed(2)} (${changePct != null ? (changePct * 100).toFixed(2) : "—"}%)`
        : "—"

    const changeColor = change != null && change >= 0 ? "\x1b[32m" : "\x1b[31m"
    const reset = "\x1b[0m"

    console.log("")
    console.log(`${data.ticker}  ${data.currency}`)
    console.log(`  Price:         ${data.price.toFixed(2)}`)
    console.log(`  Change:        ${changeColor}${changeStr}${reset}`)
    if (data.dayHigh != null && data.dayLow != null) {
      console.log(`  Day range:     ${data.dayLow.toFixed(2)} – ${data.dayHigh.toFixed(2)}`)
    }
    if (data.volume != null) {
      console.log(`  Volume:        ${data.volume.toLocaleString()}`)
    }
    if (data.history != null && data.history.length > 0) {
      const closes = data.history.map((h) => h.close)
      const min = Math.min(...closes)
      const max = Math.max(...closes)
      console.log(`  ${data.history.length}d range:    ${min.toFixed(2)} – ${max.toFixed(2)}`)
    }
    console.log("")
  },
})
