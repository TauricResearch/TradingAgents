#!/usr/bin/env bun
/**
 * alerts create — create a new alert rule.
 *
 * Usage:
 *   trading alerts create --name "NVDA below 100" \
 *     --ticker NVDA \
 *     --condition '{"type":"price_below","threshold":100}' \
 *     [--severity critical] [--channel telegram]
 */

import { defineCommand } from "citty"
import { DatabaseFactory } from "../../../src/lib/db.ts"
import { createAlert } from "../../../src/server/lib/alerts-db.ts"
import { cfg } from "../../../src/server/lib/settings.ts"
import type { AlertCondition } from "../../../src/server/lib/types.ts"

export const alertsCreateCommand = defineCommand({
  meta: {
    name: "alerts create",
    description: "Create a new custom alert rule",
  },
  args: {
    name: {
      type: "positional",
      description: "Alert name (must be unique)",
      required: true,
    },
    "--ticker": {
      type: "string",
      description: "Ticker to monitor (omit for cross-ticker/portfolio-level alerts)",
    },
    "--condition": {
      type: "string",
      description: 'JSON condition object, e.g. \'{"type":"price_below","threshold":100}\'',
      required: true,
    },
    "--platform": {
      type: "string",
      description: "Filter by platform: 'all' (default) or specific platform",
    },
    "--severity": {
      type: "string",
      description: "Severity: critical | warning | info (default: warning)",
    },
    "--message": {
      type: "string",
      description: "Custom alert message (optional, uses default if omitted)",
    },
    "--channel": {
      type: "string",
      description: "Notification channel: telegram | email | webhook | none (default: telegram)",
    },
  },
  run: async ({ args }) => {
    // Parse condition JSON
    let condition: AlertCondition
    try {
      condition = JSON.parse(args["--condition"] ?? "{}") as AlertCondition
    } catch {
      console.error("Error: --condition must be valid JSON")
      process.exit(1)
    }

    const validTypes = [
      "price_below",
      "price_above",
      "pct_change_day",
      "pct_change_week",
      "signal_change",
      "price_cross",
    ]
    if (!validTypes.includes(condition.type)) {
      console.error(`Error: condition.type must be one of: ${validTypes.join(", ")}`)
      process.exit(1)
    }

    const validSeverities = ["critical", "warning", "info"]
    const severity = args["--severity"] as "critical" | "warning" | "info" | undefined
    if (severity && !validSeverities.includes(severity)) {
      console.error(`Error: --severity must be one of: ${validSeverities.join(", ")}`)
      process.exit(1)
    }

    const validChannels = ["telegram", "email", "webhook", "none"]
    const channel = args["--channel"] as "telegram" | "email" | "webhook" | "none" | undefined
    if (channel && !validChannels.includes(channel)) {
      console.error(`Error: --channel must be one of: ${validChannels.join(", ")}`)
      process.exit(1)
    }

    DatabaseFactory.connect(cfg.portfolio.db)

    try {
      const alert = createAlert({
        name: args.name as string,
        ticker: args["--ticker"] as string | undefined,
        condition,
        platform: args["--platform"] as string | undefined,
        severity: severity as "critical" | "warning" | "info" | undefined,
        message: args["--message"] as string | undefined,
        channel: channel as "telegram" | "email" | "webhook" | "none" | undefined,
      })

      console.log("")
      console.log(`  ✓ Created alert #${alert.id}: ${alert.name}`)
      console.log(`    Ticker: ${alert.ticker ?? "(portfolio)"}`)
      console.log(`    Condition: ${JSON.stringify(alert.condition)}`)
      console.log(`    Severity: ${alert.severity}`)
      console.log(`    Channel: ${alert.channel}`)
      console.log("")
    } catch (err) {
      if (String(err).includes("UNIQUE constraint")) {
        console.error(`Error: an alert named "${args.name}" already exists.`)
        process.exit(1)
      }
      throw err
    }
  },
})
