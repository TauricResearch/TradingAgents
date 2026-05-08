#!/usr/bin/env bun

/**
 * System status overview.
 *
 * Usage: trading status
 */

import { existsSync, statSync } from "node:fs"
import { defineCommand } from "citty"
import { DatabaseFactory } from "../../lib/db.ts"
import { cfg } from "../../server/lib/settings.ts"

function fmtBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function fmtDate(d: string | null): string {
  if (!d) return "—"
  return d
}

export const statusCommand = defineCommand({
  meta: {
    name: "status",
    description: "System status overview",
  },
  args: {},
  run: async () => {
    // ── Database ────────────────────────────────────────────────────────────

    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const posCount = (
      db.query("SELECT COUNT(*) as n FROM positions WHERE status = 'open'").get() as { n: number }
    ).n
    const signalCount = (db.query("SELECT COUNT(*) as n FROM signals").get() as { n: number }).n
    const tradeCount = (db.query("SELECT COUNT(*) as n FROM trades").get() as { n: number }).n
    const watchlistCount = (db.query("SELECT COUNT(*) as n FROM watchlist").get() as { n: number })
      .n
    const analysisCount = (db.query("SELECT COUNT(*) as n FROM analyses").get() as { n: number }).n
    const latestPrice = db.query("SELECT MAX(date) as d FROM prices").get() as { d: string | null }
    const dbSize = existsSync(cfg.portfolio.db) ? statSync(cfg.portfolio.db).size : 0

    // ── Files ───────────────────────────────────────────────────────────────

    const configPath = `${process.env.HOME}/.tradingagents/config.json`
    const configExists = existsSync(configPath)
    const memoryLogPath = cfg.paths.memoryLog
    const memoryLogExists = existsSync(memoryLogPath)

    // ── Server ──────────────────────────────────────────────────────────────

    let serverRunning = false
    try {
      const resp = await fetch("http://localhost:3000/", { signal: AbortSignal.timeout(2000) })
      serverRunning = resp.status === 200
    } catch {
      serverRunning = false
    }

    // ── Print ───────────────────────────────────────────────────────────────

    console.log("")
    console.log("SYSTEM STATUS")
    console.log("─".repeat(50))
    console.log("")

    console.log("Database")
    console.log(`  File:    ${cfg.portfolio.db}`)
    console.log(`  Size:    ${fmtBytes(dbSize)}`)
    console.log(`  Open positions:   ${posCount}`)
    console.log(`  Signals:          ${signalCount}`)
    console.log(`  Trades:           ${tradeCount}`)
    console.log(`  Watchlist:        ${watchlistCount}`)
    console.log(`  Analyses:         ${analysisCount}`)
    console.log(`  Latest price:     ${fmtDate(latestPrice.d)}`)
    console.log("")

    console.log("Configuration")
    console.log(`  Config store:     ${configExists ? `✓ ${configPath}` : "✗ not found"}`)
    console.log(`  Memory log:       ${memoryLogExists ? `✓ ${memoryLogPath}` : "✗ not found"}`)
    console.log(`  Dashboard port:   ${cfg.app.dashboardPort}`)
    console.log("")

    console.log("Server")
    console.log(`  Status:           ${serverRunning ? "✓ Running on :3000" : "✗ Not running"}`)
    console.log("")
  },
})
