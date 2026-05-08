#!/usr/bin/env bun
/**
 * Lab: Template E — The simplest correct version
 *
 * One border. Dynamic width. No wrapping. Hint outside.
 *
 * Run: bun scripts/lab/status-template-e.ts
 */

import { execSync } from "node:child_process"
import { existsSync } from "node:fs"
import { join } from "node:path"
import { gum } from "../lib/gum.ts"

const HOME = process.env.HOME ?? "~"
const PID_FILE = join(HOME, ".tradingagents", "server.pid")
const PORT = parseInt(process.env.TA_DASHBOARD_PORT ?? "3000", 10)
const DB_PATH = process.env.PORTFOLIO_DB ?? "./portfolio.db"
const TEST_DB_PATH = process.env.TEST_PORTFOLIO_DB ?? "./test_portfolio.db"

// ── Detection ──────────────────────────────────────────────────────────────

function readPid(): number | null {
  try {
    const text = require("node:fs").readFileSync(PID_FILE, "utf-8")
    const pid = parseInt(text.trim(), 10)
    return Number.isNaN(pid) ? null : pid
  } catch {
    return null
  }
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

function detectPort(port: number): boolean {
  try {
    execSync(`lsof -ti :${port}`, { shell: "/bin/bash" })
    return true
  } catch {
    return false
  }
}

function detectHledger(): boolean {
  try {
    execSync("hledger -f ~/.hledger.journal balance --tree >/dev/null 2>&1")
    return true
  } catch {
    return false
  }
}

function detectVenv(): boolean {
  return existsSync(".venv/bin/activate")
}

function detectGitNexus(): boolean {
  try {
    execSync("gitnexus status", { shell: "/bin/bash" })
    return true
  } catch {
    return false
  }
}

function detectTd(): boolean {
  return existsSync(".todos")
}

interface Row {
  name: string
  state: "running" | "stopped" | "error" | "unknown"
  detail: string
  verb: string
}

function gather(): Row[] {
  const pid = readPid()
  const dashboardRunning = pid !== null && isAlive(pid)
  const portOccupied = detectPort(PORT)

  return [
    {
      name: "Dashboard Server",
      state: dashboardRunning ? "running" : portOccupied ? "error" : "stopped",
      detail: dashboardRunning
        ? `PID ${pid} · ${PORT}`
        : portOccupied
          ? `port ${PORT} stale?`
          : `port ${PORT} free`,
      verb: "just serve",
    },
    {
      name: "SQLite (LIVE)",
      state: existsSync(DB_PATH) ? "running" : "stopped",
      detail: existsSync(DB_PATH) ? DB_PATH : "not found",
      verb: "just db-stats",
    },
    {
      name: "SQLite (TEST)",
      state: existsSync(TEST_DB_PATH) ? "running" : "stopped",
      detail: existsSync(TEST_DB_PATH) ? TEST_DB_PATH : "not found",
      verb: "just test-db-stats",
    },
    {
      name: "hLedger",
      state: detectHledger() ? "running" : "error",
      detail: detectHledger() ? "journal ok" : "journal fail",
      verb: "just hl",
    },
    {
      name: "Python venv",
      state: detectVenv() ? "running" : "stopped",
      detail: detectVenv() ? ".venv ok" : "missing",
      verb: "uv sync",
    },
    {
      name: "GitNexus",
      state: detectGitNexus() ? "running" : "unknown",
      detail: detectGitNexus() ? "indexed" : "status unknown",
      verb: "just gn-status",
    },
    {
      name: "td tasks",
      state: detectTd() ? "running" : "stopped",
      detail: detectTd() ? ".todos ok" : "not init",
      verb: "just td-status",
    },
  ]
}

// ── Simplest correct display ─────────────────────────────────────────────

async function display(rows: Row[]) {
  const dotColour: Record<Row["state"], string> = {
    running: "\x1b[32m",
    stopped: "\x1b[90m",
    error: "\x1b[31m",
    unknown: "\x1b[33m",
  }
  const reset = "\x1b[0m"

  const maxName = Math.max(...rows.map((r) => r.name.length))
  const maxDetail = Math.max(...rows.map((r) => r.detail.length))

  // Build plain-text rows
  const lines: string[] = [
    `${"Service".padEnd(maxName + 2)}${"Status".padEnd(10)}${"Detail".padEnd(maxDetail + 2)}Verb`,
    "─".repeat(maxName + maxDetail + 24),
  ]

  for (const r of rows) {
    const dot = `${dotColour[r.state]}●${reset}`
    const name = r.name.padEnd(maxName + 1)
    const state = r.state.padEnd(9)
    const detail = r.detail.padEnd(maxDetail + 2)
    lines.push(`${dot} ${name} ${state} ${detail}${r.verb}`)
  }

  const body = lines.join("\n")

  // One border around the whole thing
  const box = await gum(body, ["--border", "rounded", "--padding", "1 2"])

  // Title outside the box (avoids fixed-width wrapping issues)
  const title = await gum("TradingAgents", ["--bold", "--foreground", "212"])

  // Hint outside the box — plain text, no wrapping risk
  const hint =
    "\x1b[90mhint: just <verb>  →  serve  db-stats  hl  test-db-stats  gn-status  td-status\x1b[0m"

  console.log("")
  console.log(`  ${title}`)
  console.log(box)
  console.log(`  ${hint}`)
  console.log("")
}

// ── Main ───────────────────────────────────────────────────────────────────

async function main() {
  const rows = gather()
  await display(rows)
}

main()
