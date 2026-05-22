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
    alerts: () => import("./commands/alerts.ts").then((m) => m.alertsCommand),
    analyze: () => import("./commands/analyze.ts").then((m) => m.analyzeCommand),
    benchmark: () => import("./commands/benchmark.ts").then((m) => m.benchmarkCommand),
    buylist: () => import("./commands/buylist.ts").then((m) => m.buylistCommand),
    completion: () => import("./commands/completion.ts").then((m) => m.completionCommand),
    config: () => import("./commands/config.ts").then((m) => m.configCommand),
    data: () => import("./commands/data.ts").then((m) => m.dataCommand),
    execute: () => import("./commands/execute.ts").then((m) => m.executeCommand),
    help: () => import("./commands/help.ts").then((m) => m.helpCommand),
    ig: () => import("./commands/ig.ts").then((m) => m.igCommand),
    plan: () => import("./commands/plan.ts").then((m) => m.planCommand),
    portfolio: () => import("./commands/portfolio.ts").then((m) => m.portfolioCommand),
    prices: () => import("./commands/prices.ts").then((m) => m.pricesCommand),
    regime: () => import("./commands/regime.ts").then((m) => m.regimeCommand),
    scan: () => import("./commands/scan.ts").then((m) => m.scanCommand),
    research: () => import("./commands/research.ts").then((m) => m.researchCommand),
    screen: () => import("./commands/screen.ts").then((m) => m.screenCommand),
    seed: () => import("./commands/seed.ts").then((m) => m.seedCommand),
    signals: () => import("./commands/signals.ts").then((m) => m.signalsCommand),
    spreadbets: () => import("./commands/spreadbets.ts").then((m) => m.spreadbetsCommand),
    status: () => import("./commands/status.ts").then((m) => m.statusCommand),
    summarize: () => import("./commands/summarize.ts").then((m) => m.summarizeCommand),
    sync: () => import("./commands/sync.ts").then((m) => m.syncCommand),
    trades: () => import("./commands/trades.ts").then((m) => m.tradesCommand),
    watchlist: () => import("./commands/watchlist.ts").then((m) => m.watchlistCommand),
  },
})

runMain(main)
