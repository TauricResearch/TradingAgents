#!/usr/bin/env bun
/**
 * Seed database with test data.
 *
 * Delegates to scripts/seed_database.ts
 * Usage: trading seed [--positions] [--signals] [--prices]
 */

import { defineCommand } from "citty"

export const seedCommand = defineCommand({
  meta: { name: "seed", description: "Seed database with test data" },
  args: {
    positions: {
      type: "boolean",
      description: "Seed positions only",
      default: false,
    },
    signals: {
      type: "boolean",
      description: "Seed signals only",
      default: false,
    },
    prices: {
      type: "boolean",
      description: "Seed prices from Yahoo Finance",
      default: false,
    },
    watchlist: {
      type: "boolean",
      description: "Seed watchlist items",
      default: false,
    },
  },
  run: async ({ args }) => {
    const flags: string[] = []
    if (args.positions) flags.push("--positions")
    if (args.signals) flags.push("--signals")
    if (args.prices) flags.push("--prices")
    if (args.watchlist) flags.push("--watchlist")

    const proc = Bun.spawn(["bun", "scripts/seed_database.ts", ...flags], {
      stdout: "inherit",
      stderr: "inherit",
    })

    const exitCode = await proc.exited
    if (exitCode !== 0) {
      process.exit(exitCode)
    }
  },
})
