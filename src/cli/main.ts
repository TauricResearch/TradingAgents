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
    help: () => import("./commands/help.ts").then((m) => m.helpCommand),
  },
})

runMain(main)
