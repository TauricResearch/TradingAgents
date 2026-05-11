#!/usr/bin/env bun
/**
 * alerts list — list all alert rules.
 */

import { defineCommand } from "citty"
import { DatabaseFactory } from "../../../src/lib/db.ts"
import { listAlerts } from "../../../src/server/lib/alerts-db.ts"
import { cfg } from "../../../src/server/lib/settings.ts"

export const alertsListCommand = defineCommand({
  meta: {
    name: "alerts list",
    description: "List all custom alert rules",
  },
  args: {
    json: {
      type: "boolean",
      description: "Output as JSON",
      default: false,
    },
  },
  run: async ({ args }) => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const alerts = listAlerts()

    if (alerts.length === 0) {
      console.log("No alert rules defined. Run: trading alerts create ...")
      return
    }

    if (args.json) {
      console.log(JSON.stringify(alerts, null, 2))
      return
    }

    const enabled = alerts.filter((a) => a.enabled).length
    console.log("")
    console.log(`  ${alerts.length} rules · ${enabled} enabled`)
    console.log("")

    const dot: Record<string, string> = {
      critical: "\x1b[31m●\x1b[0m",
      warning: "\x1b[33m●\x1b[0m",
      info: "\x1b[32m●\x1b[0m",
    }

    const maxName = Math.max(4, ...alerts.map((a) => a.name.length))
    const maxTick = Math.max(6, ...alerts.map((a) => (a.ticker ?? "(none)").length))
    const header = `${"ID".padStart(4)}  ${"Name".padEnd(maxName + 2)}  ${"Ticker".padEnd(maxTick + 2)}  ${"Severity".padEnd(10)}  ${"Condition".padEnd(20)}  ${"Enabled"}`
    console.log(header)
    console.log("─".repeat(header.length + 30))

    for (const a of alerts) {
      const d = dot[a.severity] ?? "○"
      const enabled_ = a.enabled ? "✓" : "✗"
      const cond = JSON.stringify(a.condition)
      const condShort = cond.length > 18 ? `${cond.slice(0, 18)}…` : cond
      console.log(
        `${String(a.id).padStart(4)}  ${a.name.padEnd(maxName + 2)}  ${(a.ticker ?? "(none)").padEnd(maxTick + 2)}  ${a.severity.padEnd(10)}  ${condShort.padEnd(20)}  ${d} ${enabled_}`,
      )
    }
    console.log("")
  },
})
