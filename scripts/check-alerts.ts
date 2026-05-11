#!/usr/bin/env bun

/**
 * check-alerts — alert matching + dispatch runner.
 *
 * Reads all enabled alerts from SQLite, fetches current prices,
 * evaluates conditions, dispatches notifications.
 *
 * Usage:
 *   bun scripts/check-alerts.ts              # dry-run: show what would fire
 *   bun scripts/check-alerts.ts --fire       # actually send notifications
 *   just check-alerts [fire]
 */

import { readFileSync } from "node:fs"
import { DatabaseFactory } from "../src/lib/db.ts"
import { listAlerts, setLastTriggered } from "../src/server/lib/alerts-db.ts"
import { loadPriceMap, matchAlerts, tickersFromAlerts } from "../src/server/lib/alerts-engine.ts"
import { cfg } from "../src/server/lib/settings.ts"
import { dispatchAlerts } from "../src/server/lib/telegram.ts"

// ── CLI ─────────────────────────────────────────────────────────────────────

const fire = process.argv.includes("--fire")
const json = process.argv.includes("--json")

// ── Main ────────────────────────────────────────────────────────────────────

DatabaseFactory.connect(cfg.portfolio.db)

// Ensure alerts table exists (CREATE TABLE IF NOT EXISTS is safe)
const schemaPath = new URL("../src/server/lib/schema.sql", import.meta.url).pathname
const schema = readFileSync(schemaPath, "utf-8")
DatabaseFactory.get().exec(schema)

const db = DatabaseFactory.get()

const alerts = listAlerts()
if (alerts.length === 0) {
  console.log("No alert rules defined. Run: trading alerts create ...")
  process.exit(0)
}

const enabled = alerts.filter((a) => a.enabled)
if (enabled.length === 0) {
  console.log("All alert rules are disabled.")
  process.exit(0)
}

const tickers = tickersFromAlerts(enabled)
const prices = loadPriceMap(tickers, db)
const triggered = matchAlerts(enabled, prices)

if (json) {
  console.log(
    JSON.stringify(
      {
        summary: {
          total: alerts.length,
          enabled: enabled.length,
          triggered: triggered.length,
        },
        triggered,
      },
      null,
      2,
    ),
  )
  process.exit(0)
}

// ── Display ────────────────────────────────────────────────────────────────

const dot: Record<string, string> = {
  critical: "\x1b[31m●\x1b[0m",
  warning: "\x1b[33m●\x1b[0m",
  info: "\x1b[32m●\x1b[0m",
}

console.log("")
console.log(`  ${alerts.length} rules · ${enabled.length} enabled · ${triggered.length} triggered`)
console.log("")

if (triggered.length === 0) {
  console.log("  ✓ No alerts triggered.")
  process.exit(0)
}

// Show triggered alerts
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

if (!fire) {
  console.log("  Run with --fire to send notifications.")
  process.exit(0)
}

// ── Dispatch ────────────────────────────────────────────────────────────────

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

// Update last_triggered timestamps — only for successfully sent alerts
const ts = new Date().toISOString()
for (let i = 0; i < triggered.length; i++) {
  if (results[i]?.sent) {
    setLastTriggered(triggered[i].alert.id, ts)
  }
}
