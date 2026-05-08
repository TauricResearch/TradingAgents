#!/usr/bin/env bun
/**
 * Lab: Status Display Template Experiments
 *
 * Tries multiple Gum-styled layouts for service status.
 * Each template uses LIVE detection so output is real, not mocked.
 *
 * Run: bun scripts/lab/status-templates.ts
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

// ── Live detection ─────────────────────────────────────────────────────────

interface ServiceStatus {
  name: string
  state: "running" | "stopped" | "error" | "unknown"
  detail: string
  justVerb: string
}

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

function gatherServices(): ServiceStatus[] {
  const pid = readPid()
  const dashboardRunning = pid !== null && isAlive(pid)
  const portOccupied = detectPort(PORT)

  const services: ServiceStatus[] = [
    {
      name: "Dashboard Server",
      state: dashboardRunning ? "running" : portOccupied ? "error" : "stopped",
      detail: dashboardRunning
        ? `PID ${pid}  port ${PORT}`
        : portOccupied
          ? `port ${PORT} occupied (stale?)`
          : `port ${PORT} free`,
      justVerb: "just serve",
    },
    {
      name: "SQLite (LIVE)",
      state: existsSync(DB_PATH) ? "running" : "stopped",
      detail: existsSync(DB_PATH) ? DB_PATH : "not found",
      justVerb: "just db-stats",
    },
    {
      name: "SQLite (TEST)",
      state: existsSync(TEST_DB_PATH) ? "running" : "stopped",
      detail: existsSync(TEST_DB_PATH) ? TEST_DB_PATH : "not found",
      justVerb: "just test-db-stats",
    },
    {
      name: "hLedger",
      state: detectHledger() ? "running" : "error",
      detail: detectHledger() ? "~/.hledger.journal" : "journal not loadable",
      justVerb: "just hl",
    },
    {
      name: "Python venv",
      state: detectVenv() ? "running" : "stopped",
      detail: detectVenv() ? ".venv ready" : "missing .venv",
      justVerb: "uv sync",
    },
    {
      name: "GitNexus",
      state: detectGitNexus() ? "running" : "unknown",
      detail: detectGitNexus() ? "index ready" : "index status unknown",
      justVerb: "just gn-status",
    },
    {
      name: "td tasks",
      state: detectTd() ? "running" : "stopped",
      detail: detectTd() ? ".todos active" : "not initialised",
      justVerb: "just td-status",
    },
  ]

  return services
}

// ── Styling helpers ────────────────────────────────────────────────────────

const COLOUR = {
  running: "2", // green
  stopped: "8", // grey
  error: "1", // red
  unknown: "3", // yellow
}

const DOT = {
  running: "●",
  stopped: "○",
  error: "◉",
  unknown: "◐",
}

function dot(state: ServiceStatus["state"]): string {
  // Gum --foreground only; we embed the dot directly in text
  // and colour the whole line via gum's --foreground if we wanted per-line colour.
  // But gum style applies to the whole block, so we use ANSI for inline dots.
  const c = COLOUR[state]
  const d = DOT[state]
  return `\x1b[38;5;${c}m${d}\x1b[0m`
}

// ── Template A: Classic bordered table ─────────────────────────────────────

async function templateA(services: ServiceStatus[]) {
  const header = "Service               Status    Detail"
  const rule = "───────────────────────────────────────────────"

  const lines = [header, rule]
  for (const s of services) {
    const name = s.name.padEnd(21)
    const state = s.state.padEnd(9)
    const detail = s.detail.length > 30 ? s.detail.slice(0, 27) + "..." : s.detail
    lines.push(`${name} ${dot(s.state)} ${state} ${detail}`)
  }

  const body = lines.join("\n")
  const title = await gum("TradingAgents — Service Status", [
    "--bold",
    "--foreground",
    "212",
    "--width",
    "58",
    "--align",
    "center",
  ])
  const table = await gum(body, ["--border", "rounded", "--padding", "1 2", "--width", "58"])
  const hint = await gum("hint: just <service>  →  just serve, just db-stats, just hl …", [
    "--foreground",
    "8",
    "--width",
    "58",
    "--align",
    "center",
    "--italic",
  ])

  console.log("")
  console.log(title)
  console.log(table)
  console.log(hint)
  console.log("")
}

// ── Template B: Compact vertical list with just verbs inline ───────────────

async function templateB(services: ServiceStatus[]) {
  const maxName = Math.max(...services.map((s) => s.name.length))

  const lines = services.map((s) => {
    const name = s.name.padEnd(maxName + 2)
    const state = s.state.padEnd(9)
    return `${dot(s.state)} ${name}${state}  ${s.justVerb}`
  })

  const body = [
    `${"Service".padEnd(maxName + 2)}${"Status".padEnd(9)}  just verb`,
    "─".repeat(maxName + 2 + 9 + 10),
    ...lines,
  ].join("\n")

  const title = await gum("TradingAgents", [
    "--bold",
    "--foreground",
    "212",
    "--width",
    "52",
    "--align",
    "center",
  ])
  const table = await gum(body, ["--border", "rounded", "--padding", "1 2", "--width", "52"])
  const hint = await gum("just <verb>  —  serve  db-stats  hl  test-db-stats  …", [
    "--foreground",
    "8",
    "--width",
    "52",
    "--align",
    "center",
  ])

  console.log("")
  console.log("═══ Template B: Compact with inline verbs ═══")
  console.log("")
  console.log(title)
  console.log(table)
  console.log(hint)
  console.log("")
}

// ── Template C: Two-column cards (service + detail) ────────────────────────

async function templateC(services: ServiceStatus[]) {
  const cardWidth = 24
  const cards: string[] = []

  for (const s of services) {
    const stateColour = COLOUR[s.state]
    const top = `${dot(s.state)} ${s.name}`
    const mid = `  ${s.state}  ·  ${s.detail}`
    const bot = `  → ${s.justVerb}`

    const cardText = `${top}\n${mid}\n${bot}`
    const card = await gum(cardText, [
      "--border",
      "rounded",
      "--padding",
      "0 1",
      "--width",
      String(cardWidth),
      "--foreground",
      "250",
    ])
    cards.push(card)
  }

  const title = await gum("TradingAgents — Services", [
    "--bold",
    "--foreground",
    "212",
    "--width",
    "52",
    "--align",
    "center",
  ])
  const hint = await gum("run a service: just <verb>", [
    "--foreground",
    "8",
    "--width",
    "52",
    "--align",
    "center",
    "--italic",
  ])

  // Simple side-by-side: print two cards per row
  console.log("")
  console.log("═══ Template C: Two-column cards ═══")
  console.log("")
  console.log(title)
  console.log("")

  for (let i = 0; i < cards.length; i += 2) {
    const left = cards[i].split("\n")
    const right = cards[i + 1]?.split("\n") ?? []
    const maxH = Math.max(left.length, right.length)
    for (let j = 0; j < maxH; j++) {
      const l = left[j] ?? "".padEnd(cardWidth + 4)
      const r = right[j] ?? ""
      console.log(`${l}  ${r}`)
    }
    console.log("")
  }

  console.log(hint)
  console.log("")
}

// ── Template D: Minimal, no box, pure ANSI + gum accent ─────────────────────

async function templateD(services: ServiceStatus[]) {
  const maxName = Math.max(...services.map((s) => s.name.length))

  const rows = services.map((s) => {
    const name = s.name.padEnd(maxName + 1)
    const state = s.state.padEnd(8)
    return `  ${dot(s.state)} ${name} ${state}  ${s.justVerb}`
  })

  const title = await gum("TradingAgents", ["--bold", "--foreground", "212"])
  const subtitle = await gum("Service Status", ["--foreground", "245"])

  console.log("")
  console.log("═══ Template D: Minimal, no border ═══")
  console.log("")
  console.log(`  ${title}`)
  console.log(`  ${subtitle}`)
  console.log("  " + "─".repeat(42))
  for (const r of rows) console.log(r)
  console.log("  " + "─".repeat(42))
  console.log(`  \x1b[38;5;8mhint:\x1b[0m just <verb>  →  serve  db-stats  hl  test-db-stats  …`)
  console.log("")
}

// ── Main ───────────────────────────────────────────────────────────────────

async function main() {
  const services = gatherServices()

  console.log("\x1b[2J\x1b[H") // clear screen
  console.log("")
  console.log("═══════════════════════════════════════════════════════════════")
  console.log("  STATUS DISPLAY TEMPLATES — compare and pick a winner")
  console.log("═══════════════════════════════════════════════════════════════")
  console.log("")

  await templateA(services)
  await templateB(services)
  await templateC(services)
  await templateD(services)

  console.log("═══════════════════════════════════════════════════════════════")
  console.log("  END OF TEMPLATES")
  console.log("═══════════════════════════════════════════════════════════════")
  console.log("")
}

main()
