#!/usr/bin/env bun
/**
 * Sync prices from Yahoo Finance.
 *
 * Delegates to scripts/sync-prices.ts
 * Usage: trading sync prices [TICKER]
 */

import { defineCommand } from "citty"

export const syncCommand = defineCommand({
  meta: {
    name: "sync",
    description: "Sync market data (prices, analyses)",
  },
  subCommands: {
    prices: () => import("./sync-prices.ts").then((m) => m.syncPricesCommand),
  },
})
