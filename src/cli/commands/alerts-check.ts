#!/usr/bin/env bun
/**
 * alerts check — run the alert matching engine.
 *
 * Usage:
 *   trading alerts check       # dry-run: show what would fire
 *   trading alerts check --fire  # actually send notifications
 */

import { defineCommand } from "citty"
import { DatabaseFactory } from "../../../src/lib/db.ts"
import { listAlerts, setLastTriggered } from "../../../src/server/lib/alerts-db.ts"
import {
  loadPriceMap,
  matchAlerts,
  tickersFromAlerts,
} from "../../../src/server/lib/alerts-engine.ts"
import { cfg } from "../../../src/server/lib/settings.ts"
import { dispatchAlerts } from "../../../src/server/lib/telegram.ts"

export const alertsCheckCommand = defineCommand({
  meta: {
    name: "alerts check",
    description: "Run alert matching engine — show or fire triggered alerts",
  },
  args: {
    "--fire": {
      type: "boolean",
      description: "Actually send notifications (default: dry-run)",
      default: false,
    },
    "--json": {
      type: "boolean",
      description: "Output as JSON",
      default: false,
    },
  },
  run: async ({ args }) => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const alerts = listAlerts()
    if (alerts.length === 0) {
      console.log("No alert rules defined. Run: trading alerts create ...")
      return
    }

    const enabled = alerts.filter((a) => a.enabled)
    if (enabled.length === 0) {
      console.log("All alert rules are disabled.")
      return
    }

    const tickers = tickersFromAlerts(enabled)
    const prices = loadPriceMap(tickers, db)
    const triggered = matchAlerts(enabled, prices)

    if (args["--json"]) {
      console.log(
        JSON.stringify(
          {
            summary: { total: alerts.length, enabled: enabled.length, triggered: triggered.length },
            triggered,
          },
          null,
          2,
        ),
      )
      return
    }

    const dot: Record<string, string> = {
      critical: "\x1b[31m●\x1b[0m",
      warning: "\x1b[33m●\x1b[0m",
      info: "\x1b[32m●\x1b[0m",
    }

    console.log("")
    console.log(
      `  ${alerts.length} rules · ${enabled.length} enabled · ${triggered.length} triggered`,
    )
    console.log("")

    if (triggered.length === 0) {
      console.log("  ✓ No alerts triggered.")
      return
    }

    for (const ta of triggered) {
      const { alert, currentPrice, pctChange, message } = ta
      const d = dot[alert.severity] ?? "○"
      const price = currentPrice != null ? `£${currentPrice.toFixed(2)}` : "?"
      const pct = pctChange != null ? ` (${pctChange >= 0 ? "+" : ""}${pctChange.toFixed(1)}%)` : ""
      console.log(`${d} [${alert.severity.toUpperCase()}] ${alert.name}`)
      console.log(`  Ticker: ${alert.ticker ?? "(portfolio)"} | Price: ${price}${pct}`)
      console.log(`  ${message}`)
      console.log("")
    }

    if (!args["--fire"]) {
      console.log("  Run with --fire to send notifications.")
      return
    }

    const results = await dispatchAlerts(triggered)
    const sent = results.filter((r) => r.sent).length
    const failed = results.filter((r) => !r.sent)

    console.log(`Sent ${sent}/${triggered.length} notifications.`)
    if (failed.length > 0) {
      console.log("Failed:")
      for (const f of failed) {
        console.log(`  ${f.alertName}: ${f.error}`)
      }
    }

    const ts = new Date().toISOString()
    for (const ta of triggered) {
      setLastTriggered(ta.alert.id, ts)
    }
  },
})
