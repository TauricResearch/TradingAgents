#!/usr/bin/env bun
/**
 * Exit plan alerts — Phase 1
 *
 * Checks all exit plans against latest prices and reports alerts.
 * No configuration required — every position with an exit plan is monitored.
 *
 * Usage:
 *   trading alerts              # check all exit plans
 *   trading alerts --json       # machine-readable output
 */

import { defineCommand } from "citty"
import { gum } from "../../../scripts/lib/gum.ts"
import { DatabaseFactory } from "../../lib/db.ts"
import { computeExitStatus, loadAllPlans } from "../../server/lib/positions.ts"
import { cfg } from "../../server/lib/settings.ts"

interface Alert {
  ticker: string
  platform: string
  severity: "critical" | "warning" | "info" | "ok" | "no_price"
  message: string
  price: number | null
  stopPrice: number
  nextTarget: number | undefined
  daysLeft: number | undefined
}

function latestPrice(db: ReturnType<typeof DatabaseFactory.get>, ticker: string): number | null {
  const row = db
    .query<{ close: number }, [string]>(
      "SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
    )
    .get(ticker)
  return row ? row.close : null
}

function checkAlert(plan: ReturnType<typeof loadAllPlans>[number], price: number | null): Alert {
  const status = computeExitStatus(plan, price ?? undefined)
  const invalidation = plan.invalidation ?? {
    price: plan.invalidation_price ?? 0,
    thesis: plan.invalidation_thesis ?? "",
  }

  let severity: Alert["severity"] = "ok"
  let message = ""

  if (price == null) {
    severity = "no_price"
    message = "No price data — run just sync-prices"
  } else {
    // Stop check (most severe)
    if (price <= invalidation.price) {
      severity = "critical"
      message = `STOP: £${price.toFixed(2)} ≤ £${invalidation.price.toFixed(2)}  (P&L: ${status.pnlPct.toFixed(1)}%)`
    } else if (status.targetsHit > 0) {
      // Target hit
      severity = "info"
      const total = plan.targets?.length ?? 0
      const highest = plan.targets?.[status.targetsHit - 1]
      message = `TARGET ${status.targetsHit}/${total}: £${highest?.price.toFixed(2) ?? "?"}  (P&L: ${status.pnlPct.toFixed(1)}%)`
    } else if (status.timeStopDaysLeft != null && status.timeStopDaysLeft <= 30) {
      if (status.timeStopDaysLeft <= 0) {
        severity = "warning"
        message = "TIME STOP EXPIRED"
      } else {
        severity = "warning"
        message = `Time stop: ${status.timeStopDaysLeft}d left`
      }
    }
  }

  return {
    ticker: plan.ticker,
    platform: plan.platform,
    severity,
    message,
    price,
    stopPrice: invalidation.price,
    nextTarget: status.nextTarget?.price,
    daysLeft: status.timeStopDaysLeft,
  }
}

// ── Display ────────────────────────────────────────────────────────────────

async function displayGum(alerts: Alert[]) {
  const dot: Record<string, string> = {
    critical: "\x1b[31m●\x1b[0m",
    warning: "\x1b[33m●\x1b[0m",
    info: "\x1b[32m●\x1b[0m",
    ok: "\x1b[90m●\x1b[0m",
    no_price: "\x1b[90m○\x1b[0m",
  }
  const name: Record<string, string> = {
    critical: "CRITICAL",
    warning: "WARNING",
    info: "INFO",
    ok: "ok",
    no_price: "no data",
  }

  const active = alerts.filter((a) => a.severity !== "ok")
  const okCount = alerts.filter((a) => a.severity === "ok").length
  const criticalCount = alerts.filter((a) => a.severity === "critical").length
  const warningCount = alerts.filter((a) => a.severity === "warning").length
  const infoCount = alerts.filter((a) => a.severity === "info").length

  // ── Summary header ──────────────────────────────────────────────────────
  const summary = `${criticalCount} critical  ·  ${warningCount} warning  ·  ${infoCount} info  ·  ${okCount} ok  ·  ${alerts.length} total`
  const header = await gum(summary, ["--foreground", "250", "--width", "60", "--align", "center"])
  console.log("")
  console.log(header)

  // ── Active alerts ───────────────────────────────────────────────────────
  if (active.length > 0) {
    const order = { critical: 0, warning: 1, info: 2, no_price: 3 }
    active.sort((a, b) => order[a.severity] - order[b.severity])

    const title = await gum("Active Alerts", ["--bold", "--foreground", "1"])
    console.log(`  ${title}`)

    const maxTicker = Math.max(...active.map((a) => a.ticker.length))
    const headerLine = `${"Ticker".padEnd(maxTicker + 2)}${"Severity".padEnd(10)}${"Price".padStart(10)} ${"Stop".padStart(10)} ${"Message"}`
    const lines = [headerLine, "─".repeat(headerLine.length + 20)]

    for (const a of active) {
      const price = a.price != null ? `£${a.price.toFixed(2)}` : "—"
      lines.push(
        `${dot[a.severity]} ${a.ticker.padEnd(maxTicker + 1)} ${name[a.severity].padEnd(9)} ${price.padStart(10)} ${a.stopPrice.toFixed(2).padStart(10)}  ${a.message}`,
      )
    }

    const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
    console.log(box)
    console.log("")
  }

  // ── All positions ───────────────────────────────────────────────────────
  const title = await gum("Exit Plan Status", ["--bold", "--foreground", "212"])
  console.log(`  ${title}`)

  const maxTicker = Math.max(6, ...alerts.map((a) => a.ticker.length))
  const headerLine = `${"Ticker".padEnd(maxTicker + 2)}${"Status".padEnd(10)}${"Price".padStart(10)} ${"Stop".padStart(10)} ${"Next Target".padStart(12)} ${"Time".padStart(6)}`
  const lines = [headerLine, "─".repeat(maxTicker + 54)]

  for (const a of alerts) {
    const price = a.price != null ? a.price.toFixed(2) : "—"
    const target = a.nextTarget != null ? a.nextTarget.toFixed(2) : "—"
    const time = a.daysLeft != null ? `${a.daysLeft}d` : "—"
    const label = a.severity === "ok" ? "ok" : name[a.severity]
    lines.push(
      `${dot[a.severity]} ${a.ticker.padEnd(maxTicker + 1)} ${label.padEnd(9)} ${price.padStart(10)} ${a.stopPrice.toFixed(2).padStart(10)} ${target.padStart(12)} ${time.padStart(6)}`,
    )
  }

  const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
  console.log(box)
  console.log(
    `  \x1b[90m● red = stop  ● yellow = time  ● green = target  ○ grey = no data  just sync-prices\x1b[0m`,
  )
  console.log("")
}

function displayJson(alerts: Alert[]) {
  console.log(JSON.stringify(alerts, null, 2))
}

// ── Command ────────────────────────────────────────────────────────────────

export const alertsCommand = defineCommand({
  meta: {
    name: "alerts",
    description: "Check exit plan alerts for all positions",
  },
  args: {
    json: {
      type: "boolean",
      description: "Output as JSON",
      default: false,
    },
  },
  run: async ({ args }) => {
    const plans = loadAllPlans()
    if (plans.length === 0) {
      console.log("No exit plans found. Create YAML files in ~/.tradingagents/positions/")
      return
    }

    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const alerts: Alert[] = []
    for (const plan of plans) {
      const price = latestPrice(db, plan.ticker)
      alerts.push(checkAlert(plan, price))
    }

    if (args.json) {
      displayJson(alerts)
    } else {
      await displayGum(alerts)
    }
  },
})
