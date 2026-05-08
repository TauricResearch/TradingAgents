#!/usr/bin/env bun
/**
 * IG trading subcommands.
 *
 * All commands authenticate on each invocation (no session persistence yet).
 * Credentials from environment: IG_DEMO_API_KEY, IG_DEMO_USERNAME, IG_DEMO_PASSWORD
 */

import { defineCommand } from "citty"

export const igCommand = defineCommand({
  meta: {
    name: "ig",
    description: "IG trading API commands — accounts, markets, prices, orders",
  },
  subCommands: {
    login: () => import("./ig-login.ts").then((m) => m.igLoginCommand),
    accounts: () => import("./ig-accounts.ts").then((m) => m.igAccountsCommand),
    search: () => import("./ig-search.ts").then((m) => m.igSearchCommand),
    prices: () => import("./ig-prices.ts").then((m) => m.igPricesCommand),
    positions: () => import("./ig-positions.ts").then((m) => m.igPositionsCommand),
    buy: () => import("./ig-buy.ts").then((m) => m.igBuyCommand),
    sell: () => import("./ig-sell.ts").then((m) => m.igSellCommand),
  },
})
