#!/usr/bin/env bun

/**
 * Lab: Exit plan alerts — Phase 1 (refined)
 *
 * Cleaner alert display: separate active alerts from status summary.
 * Run: bun scripts/lab/alerts.ts
 */

import { existsSync, lstatSync, readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { load } from "js-yaml"
import { DatabaseFactory } from "../../src/lib/db.ts"
import { gum } from "../lib/gum.ts"

// ── Types ───────────────────────────────────────────────────────────────────

interface ExitTarget {
  price: number
  label: string
  fraction: number
}
interface ExitPlan {
  ticker: string
  platform: string
  entry_price: number
  quantity: number
  invalidation: { price: number }
  invalidation_price?: number
  targets: ExitTarget[]
  time_stop?: string
}

interface Alert {
  ticker: string
  platform: string
  price: number | null
  stopPrice: number
  entryPrice: number
  nextTarget: number | undefined
  daysLeft: number | undefined
  severity: "critical" | "warning" | "info" | "ok" | "no_price"
  message: string
}

// ── Load plans ──────────────────────────────────────────────────────────────

const POSITIONS_DIR =
  process.env.POSITIONS_DIR ?? join(process.env.HOME ?? "/tmp", ".tradingagents", "positions")

function loadPlans(): ExitPlan[] {
  if (!existsSync(POSITIONS_DIR)) return []
  const plans: ExitPlan[] = []
  for (const entry of readdirSync(POSITIONS_DIR)) {
    const p = join(POSITIONS_DIR, entry)
    if (lstatSync(p).isDirectory()) {
      for (const f of readdirSync(p)) {
        if (!f.endsWith(".yaml")) continue
        try {
          const raw = readFileSync(join(p, f), "utf-8")
          const plan = load(raw) as ExitPlan
          if (plan.ticker) plans.push({ ...plan, platform: plan.platform || entry })
        } catch {}
      }
    } else if (entry.endsWith(".yaml")) {
      try {
        const raw = readFileSync(p, "utf-8")
        const plan = load(raw) as ExitPlan
        if (plan.ticker) plans.push({ ...plan, platform: plan.platform || "unknown" })
      } catch {}
    }
  }
  return plans
}

// ── Fetch price ─────────────────────────────────────────────────────────────

function latestPrice(db: ReturnType<typeof DatabaseFactory.get>, ticker: string): number | null {
  const row = db
    .query<{ close: number }, [string]>(
      "SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
    )
    .get(ticker)
  return row ? row.close : null
}

// ── Compute alerts ────────────────────────────────────────────────────────

function checkPlan(plan: ExitPlan, price: number | null): Alert {
  const stopPrice = plan.invalidation?.price ?? plan.invalidation_price ?? 0
  const targets = plan.targets ?? []
  let severity: Alert["severity"] = "ok"
  let message = ""

  if (price == null) {
    severity = "no_price"
    message = "No price data"
  } else {
    // Stop check (most severe)
    if (price <= stopPrice) {
      severity = "critical"
      const pct = (((price - plan.entry_price) / plan.entry_price) * 100).toFixed(1)
      message = `STOP: £${price.toFixed(2)} ≤ £${stopPrice.toFixed(2)}  (P&L: ${pct}%)`
    }

    // Target check
    const hitTargets = targets.filter((t) => price >= t.price)
    if (hitTargets.length > 0 && severity === "ok") {
      severity = "info"
      const highest = hitTargets[hitTargets.length - 1]
      const pct = (((price - plan.entry_price) / plan.entry_price) * 100).toFixed(1)
      message = `TARGET ${hitTargets.length}/${targets.length}: £${highest.price.toFixed(2)}  (P&L: ${pct}%)`
    }

    // Time stop check (only if no stop/target alert)
    if (severity === "ok" && plan.time_stop) {
      const stopDate = new Date(plan.time_stop)
      const now = new Date()
      const days = Math.ceil((stopDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
      if (days <= 0) {
        severity = "warning"
        message = "TIME STOP EXPIRED"
      } else if (days <= 30) {
        severity = "warning"
        message = `Time stop: ${days}d left`
      }
    }
  }

  const daysLeft = plan.time_stop
    ? Math.ceil((new Date(plan.time_stop).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
    : undefined

  const nextTarget = targets.find((t) => !price || price < t.price)

  return {
    ticker: plan.ticker,
    platform: plan.platform,
    price,
    stopPrice,
    entryPrice: plan.entry_price,
    nextTarget: nextTarget?.price,
    daysLeft,
    severity,
    message,
  }
}

// ── Display ────────────────────────────────────────────────────────────────

async function display(alerts: Alert[]) {
  const dot: Record<string, string> = {
    critical: "\x1b[31m●\x1b[0m",
    warning: "\x1b[33m●\x1b[0m",
    info: "\x1b[32m●\x1b[0m",
    ok: "\x1b[90m●\x1b[0m",
    no_price: "\x1b[90m○\x1b[0m",
  }
  const severityName: Record<string, string> = {
    critical: "CRITICAL",
    warning: "WARNING",
    info: "INFO",
    ok: "ok",
    no_price: "no data",
  }

  const active = alerts.filter((a) => a.severity !== "ok")
  const ok = alerts.filter((a) => a.severity === "ok")

  // ── Active alerts ────────────────────────────────────────────────────────
  if (active.length > 0) {
    // Sort: critical first, then warning, then info
    const order = { critical: 0, warning: 1, info: 2, no_price: 3 }
    active.sort((a, b) => order[a.severity] - order[b.severity])

    const title = await gum("Active Alerts", ["--bold", "--foreground", "1"])
    console.log(`  ${title}`)

    const maxTicker = Math.max(...active.map((a) => a.ticker.length))
    const maxMsg = Math.max(30, ...active.map((a) => a.message.length))
    const header = `${"Ticker".padEnd(maxTicker + 2)}${"Severity".padEnd(10)}${"Price".padStart(10)} ${"Stop".padStart(10)} ${"Message"}`

    const lines = [header, "─".repeat(header.length + maxMsg - 20)]

    for (const a of active) {
      const price = a.price != null ? `£${a.price.toFixed(2)}` : "—"
      lines.push(
        `${dot[a.severity]} ${a.ticker.padEnd(maxTicker + 1)} ${severityName[a.severity].padEnd(9)} ${price.padStart(10)} ${a.stopPrice.toFixed(2).padStart(10)}  ${a.message}`,
      )
    }

    const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
    console.log(box)
    console.log("")
  }

  // ── All positions summary ─────────────────────────────────────────────
  const title = await gum("Exit Plan Status", ["--bold", "--foreground", "212"])
  console.log(`  ${title}`)

  const maxTicker = Math.max(6, ...alerts.map((a) => a.ticker.length))

  const header = `${"Ticker".padEnd(maxTicker + 2)}${"Status".padEnd(10)}${"Price".padStart(10)} ${"Stop".padStart(10)} ${"Next Target".padStart(12)} ${"Time".padStart(6)}`
  const lines = [header, "─".repeat(maxTicker + 54)]

  for (const a of alerts) {
    const price = a.price != null ? a.price.toFixed(2) : "—"
    const target = a.nextTarget != null ? a.nextTarget.toFixed(2) : "—"
    const time = a.daysLeft != null ? `${a.daysLeft}d` : "—"
    const label = a.severity === "ok" ? "ok" : severityName[a.severity]
    lines.push(
      `${dot[a.severity]} ${a.ticker.padEnd(maxTicker + 1)} ${label.padEnd(9)} ${price.padStart(10)} ${a.stopPrice.toFixed(2).padStart(10)} ${target.padStart(12)} ${time.padStart(6)}`,
    )
  }

  const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
  console.log(box)
  console.log(
    `  \x1b[90mhint: ● red = stop  ● yellow = time  ● green = target  ○ grey = no data  just sync-prices\x1b[0m`,
  )
  console.log("")
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  const plans = loadPlans()
  if (plans.length === 0) {
    console.log("No exit plans found. Create YAML files in ~/.tradingagents/positions/")
    return
  }

  DatabaseFactory.connect("./portfolio.db")
  const db = DatabaseFactory.get()

  const alerts: Alert[] = []
  for (const plan of plans) {
    const price = latestPrice(db, plan.ticker)
    alerts.push(checkPlan(plan, price))
  }

  await display(alerts)
}

main()
