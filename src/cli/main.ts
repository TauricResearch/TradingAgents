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
    config: () => import("./commands/config.ts").then((m) => m.configCommand),
    help: () => import("./commands/help.ts").then((m) => m.helpCommand),
  },
})

runMain(main)
