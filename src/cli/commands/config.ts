#!/usr/bin/env bun
/**
 * Configuration management subcommands.
 *
 * Stores defaults in ~/.tradingagents/config.json:
 *   account   — default account balance (e.g. 50000)
 *   risk      — default risk per trade (e.g. 0.02)
 *   platform  — default platform (ig, ajbell, aviva, nsandi)
 *   mode      — default trade mode (shares, spreadbet)
 */

import { defineCommand } from "citty"

export const configCommand = defineCommand({
  meta: {
    name: "config",
    description: "Manage CLI defaults (account, risk, platform, mode)",
  },
  subCommands: {
    get: () => import("./config-get.ts").then((m) => m.configGetCommand),
    set: () => import("./config-set.ts").then((m) => m.configSetCommand),
    list: () => import("./config-list.ts").then((m) => m.configListCommand),
    delete: () => import("./config-delete.ts").then((m) => m.configDeleteCommand),
    path: () => import("./config-path.ts").then((m) => m.configPathCommand),
  },
})
