#!/usr/bin/env bun
/**
 * Sync prices from Yahoo Finance.
 *
 * Usage: trading sync prices [TICKER]
 */

import { defineCommand } from "citty"

export const syncPricesCommand = defineCommand({
  meta: { name: "prices", description: "Sync prices from Yahoo Finance" },
  args: {
    ticker: {
      type: "positional",
      description: "Ticker to sync (default: all open positions)",
    },
    all: {
      type: "boolean",
      description: "Sync all tickers (full backfill)",
      default: false,
    },
  },
  run: async ({ args }) => {
    const flags: string[] = []
    if (args.ticker) flags.push("--ticker", args.ticker)
    if (args.all) flags.push("--all")

    const proc = Bun.spawn(["bun", "scripts/sync-prices.ts", ...flags], {
      stdout: "inherit",
      stderr: "inherit",
    })

    const exitCode = await proc.exited
    if (exitCode !== 0) {
      process.exit(exitCode)
    }
  },
})
