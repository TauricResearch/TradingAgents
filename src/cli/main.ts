#!/usr/bin/env bun
/**
 * Unified Trading CLI
 *
 * Usage: trading <command> [args]
 */

import { defineCommand, runMain } from "citty"

const main = defineCommand({
  meta: {
    name: "trading",
    version: "0.1.0",
    description: "TradingAgents CLI — trade planning, portfolio, analysis, and data sync",
  },
  subCommands: {
    plan: () => import("./commands/plan.ts").then((m) => m.planCommand),
    execute: () => import("./commands/execute.ts").then((m) => m.executeCommand),
    ig: () => import("./commands/ig.ts").then((m) => m.igCommand),
    portfolio: () => import("./commands/portfolio.ts").then((m) => m.portfolioCommand),
    config: () => import("./commands/config.ts").then((m) => m.configCommand),
    seed: () => import("./commands/seed.ts").then((m) => m.seedCommand),
    sync: () => import("./commands/sync.ts").then((m) => m.syncCommand),
    backup: () => import("./commands/backup.ts").then((m) => m.backupCommand),
    trades: () => import("./commands/trades.ts").then((m) => m.tradesCommand),
    signals: () => import("./commands/signals.ts").then((m) => m.signalsCommand),
    watchlist: () => import("./commands/watchlist.ts").then((m) => m.watchlistCommand),
    analyze: () => import("./commands/analyze.ts").then((m) => m.analyzeCommand),
    summarize: () => import("./commands/summarize.ts").then((m) => m.summarizeCommand),
    help: () => import("./commands/help.ts").then((m) => m.helpCommand),
  },
})

runMain(main)
