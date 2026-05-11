#!/usr/bin/env bun
/**
 * alerts — custom alert rules (Phase 2).
 *
 * Subcommands:
 *   trading alerts create   — define a new alert rule
 *   trading alerts list     — list all rules
 *   trading alerts delete   — remove a rule
 *   trading alerts edit     — update a rule
 *   trading alerts check    — run matching engine (dry-run)
 *   trading alerts fire     — manually trigger dispatch for a rule
 */

import { defineCommand } from "citty"

export const alertsCommand = defineCommand({
  meta: {
    name: "alerts",
    description: "Custom alert rules — create, list, delete, edit, check",
  },
  subCommands: {
    create: () => import("./alerts-create.ts").then((m) => m.alertsCreateCommand),
    list: () => import("./alerts-list.ts").then((m) => m.alertsListCommand),
    delete: () => import("./alerts-delete.ts").then((m) => m.alertsDeleteCommand),
    check: () => import("./alerts-check.ts").then((m) => m.alertsCheckCommand),
  },
})
