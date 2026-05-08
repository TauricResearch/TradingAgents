#!/usr/bin/env bun
/**
 * Server Lifecycle CLI
 *
 * Manage the TradingAgents dashboard server.
 * Uses PID files for exact process tracking — no ps | grep fragility.
 *
 * Usage:
 *   bun scripts/server-lifecycle.ts status    # show service status
 *   bun scripts/server-lifecycle.ts start     # start dashboard server
 *   bun scripts/server-lifecycle.ts serve     # alias for start
 *   bun scripts/server-lifecycle.ts stop      # stop dashboard server
 *   bun scripts/server-lifecycle.ts restart   # restart dashboard server
 *   bun scripts/server-lifecycle.ts ports     # show listening ports
 */

import { execSync, spawn } from "node:child_process"
import { existsSync, mkdirSync } from "node:fs"
import { readFile, rename, unlink, writeFile } from "node:fs/promises"
import { join } from "node:path"
import { gum } from "./lib/gum.ts"

// ── Constants ───────────────────────────────────────────────────────────────

const RUNTIME_DIR = join(Bun.env.HOME ?? "~", ".tradingagents")
const PID_FILE = join(RUNTIME_DIR, "server.pid")
const LOG_FILE = join(RUNTIME_DIR, "server.log")
const PREV_LOG = join(RUNTIME_DIR, "server.prev.log")
const PORT = parseInt(Bun.env.TA_DASHBOARD_PORT ?? "3000", 10)

// ── Helpers ─────────────────────────────────────────────────────────────────

function ensureRuntimeDir(): void {
  if (!existsSync(RUNTIME_DIR)) {
    mkdirSync(RUNTIME_DIR, { recursive: true })
  }
}

async function readPid(): Promise<number | null> {
  try {
    const text = await readFile(PID_FILE, "utf-8")
    const pid = parseInt(text.trim(), 10)
    return Number.isNaN(pid) ? null : pid
  } catch {
    return null
  }
}

function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

async function cleanupStalePid(): Promise<boolean> {
  const pid = await readPid()
  if (pid && !isProcessAlive(pid)) {
    await unlink(PID_FILE).catch(() => {})
    return true
  }
  return false
}

function isPortFree(port: number): boolean {
  try {
    const out = execSync(`lsof -i :${port} 2>/dev/null`, { encoding: "utf-8" })
    return out.trim().length === 0
  } catch {
    return true
  }
}

async function rotateLog(): Promise<void> {
  if (existsSync(LOG_FILE)) {
    await rename(LOG_FILE, PREV_LOG).catch(() => {})
  }
}

// ── Status ──────────────────────────────────────────────────────────────────

interface ServiceRow {
  name: string
  status: string
  pid: string
  port: string
}

async function getDashboardRow(): Promise<ServiceRow> {
  const pid = await readPid()
  if (!pid) {
    return {
      name: "Dashboard Server",
      status: "stopped",
      pid: "—",
      port: String(PORT),
    }
  }
  if (!isProcessAlive(pid)) {
    await unlink(PID_FILE).catch(() => {})
    return {
      name: "Dashboard Server",
      status: "stopped",
      pid: "—",
      port: String(PORT),
    }
  }
  const listening = !isPortFree(PORT)
  return {
    name: "Dashboard Server",
    status: listening ? "running" : "unknown",
    pid: String(pid),
    port: String(PORT),
  }
}

function getDatabaseRow(): ServiceRow {
  const dbPath = Bun.env.PORTFOLIO_DB ?? "./portfolio.db"
  const active =
    Bun.env.TEST_MODE === "1" ? (Bun.env.TEST_PORTFOLIO_DB ?? "./test_portfolio.db") : dbPath
  return {
    name: `SQLite (${Bun.env.TEST_MODE === "1" ? "TEST" : "LIVE"})`,
    status: existsSync(active) ? "running" : "unknown",
    pid: "—",
    port: "—",
  }
}

function getGitnexusRow(): ServiceRow {
  let indexed = false
  try {
    const out = execSync("gitnexus list 2>/dev/null", { encoding: "utf-8" })
    indexed = out.includes("TradingAgents")
  } catch {
    // ignore
  }
  return {
    name: "GitNexus Index",
    status: indexed ? "running" : "stopped",
    pid: "—",
    port: "—",
  }
}

// ── Commands ─────────────────────────────────────────────────────────────────

async function cmdStatus(): Promise<void> {
  const rows = [await getDashboardRow(), getDatabaseRow(), getGitnexusRow()]

  const tableLines = [
    "Service            Status     PID     Port",
    "───────────────────────────────────────────",
    ...rows.map(
      (r) =>
        `${r.name.padEnd(18)} ● ${r.status.padEnd(8)} ${r.pid.padStart(6)} ${r.port.padStart(5)}`,
    ),
    "",
    "Run just service-help for available commands",
  ].join("\n")

  console.log("")
  console.log(
    await gum("TradingAgents Services", [
      "--bold",
      "--foreground",
      "212",
      "--width",
      "64",
      "--align",
      "center",
    ]),
  )
  console.log(await gum(tableLines, ["--border", "rounded", "--padding", "1 2", "--width", "64"]))

  const dashboard = rows.find((r) => r.name === "Dashboard Server")
  if (dashboard?.status === "running") {
    try {
      execSync(`curl -s http://localhost:${PORT}/health >/dev/null`, { timeout: 2000 })
      console.log(
        await gum(`  ✓ Dashboard responding on http://localhost:${PORT}`, ["--foreground", "2"]),
      )
    } catch {
      console.log(
        await gum("  ! Dashboard process running but not responding", ["--foreground", "3"]),
      )
    }
  } else {
    console.log(
      await gum("  ✗ Dashboard not running — start with: just start", ["--foreground", "1"]),
    )
  }
  console.log("")
}

async function cmdStart(): Promise<void> {
  ensureRuntimeDir()

  // Check if already running
  const existingPid = await readPid()
  if (existingPid && isProcessAlive(existingPid)) {
    console.log(await gum(`Dashboard already running (PID ${existingPid})`, ["--foreground", "3"]))
    return
  }

  // Clean stale PID
  if (await cleanupStalePid()) {
    console.log("Cleaned up stale PID file")
  }

  // Check port
  if (!isPortFree(PORT)) {
    console.log(await gum(`Port ${PORT} is already in use`, ["--foreground", "1"]))
    return
  }

  console.log("Starting dashboard server...")

  // Rotate log
  await rotateLog()

  // Spawn server with log capture
  const logFd = await Bun.file(LOG_FILE).writer()
  const child = spawn("bun", ["run", "src/server/index.tsx"], {
    detached: true,
    stdio: ["ignore", "pipe", "pipe"],
  })

  if (child.stdout) {
    child.stdout.on("data", (d: Buffer) => logFd.write(d))
  }
  if (child.stderr) {
    child.stderr.on("data", (d: Buffer) => logFd.write(d))
  }

  child.unref()

  // Write PID
  await writeFile(PID_FILE, String(child.pid))

  // Wait for health check
  await new Promise((r) => setTimeout(r, 2000))

  try {
    execSync(`curl -s http://localhost:${PORT}/health >/dev/null`, { timeout: 3000 })
    console.log(await gum(`✓ Dashboard started (PID ${child.pid})`, ["--foreground", "2"]))
    console.log(`  http://localhost:${PORT}`)
  } catch {
    console.log(
      await gum(`⚠ Server started (PID ${child.pid}) but health check failed`, [
        "--foreground",
        "3",
      ]),
    )
    console.log(`  http://localhost:${PORT}`)
  }
}

async function cmdStop(): Promise<void> {
  const pid = await readPid()
  if (!pid) {
    console.log(await gum("Dashboard not running (no PID file)", ["--foreground", "3"]))
    return
  }

  if (!isProcessAlive(pid)) {
    await unlink(PID_FILE).catch(() => {})
    console.log(await gum("Dashboard not running (stale PID removed)", ["--foreground", "3"]))
    return
  }

  console.log(`Stopping dashboard (PID ${pid})...`)
  try {
    process.kill(pid, "SIGTERM")
  } catch (e) {
    console.error(`Failed to send SIGTERM: ${e instanceof Error ? e.message : String(e)}`)
    return
  }

  // Wait for graceful shutdown
  for (let i = 0; i < 10; i++) {
    await new Promise((r) => setTimeout(r, 500))
    if (!isProcessAlive(pid)) {
      await unlink(PID_FILE).catch(() => {})
      console.log(await gum("✓ Dashboard stopped", ["--foreground", "2"]))
      return
    }
  }

  // Force kill
  console.log("Forcing SIGKILL...")
  try {
    process.kill(pid, "SIGKILL")
    await unlink(PID_FILE).catch(() => {})
    console.log(await gum("✓ Dashboard killed", ["--foreground", "2"]))
  } catch (e) {
    console.error(
      await gum(`✗ Failed to kill: ${e instanceof Error ? e.message : String(e)}`, [
        "--foreground",
        "1",
      ]),
    )
  }
}

async function cmdRestart(): Promise<void> {
  await cmdStop()
  await new Promise((r) => setTimeout(r, 500))
  await cmdStart()
}

function cmdPorts(): void {
  console.log("")
  console.log("Listening ports:")
  try {
    const output = execSync("lsof -i -P | grep LISTEN | grep -E 'bun|node|python'", {
      encoding: "utf-8",
      shell: "/bin/bash",
    })
    console.log(output)
  } catch {
    console.log("No listening ports found for bun/node/python")
  }
  console.log("")
}

async function cmdLogs(): Promise<void> {
  if (existsSync(LOG_FILE)) {
    console.log(await gum(`Server log: ${LOG_FILE}`, ["--bold"]))
    try {
      const tail = execSync(`tail -n 20 "${LOG_FILE}"`, { encoding: "utf-8" })
      console.log(tail)
    } catch {
      console.log("(log file empty or unreadable)")
    }
  } else {
    console.log("No log file found. Start the server first.")
  }
  if (existsSync(PREV_LOG)) {
    console.log(`Previous log: ${PREV_LOG}`)
  }
}

async function cmdServiceHelp(): Promise<void> {
  const lines = [
    "Dashboard Server",
    "  just start     Start dashboard server",
    "  just stop      Stop dashboard server",
    "  just restart   Restart dashboard server",
    "  just logs      Show recent server logs",
    "  just ports     Show listening ports",
    "",
    "GitNexus Index",
    "  just gn-diagrams      Generate project graphs",
    "  just gn-analyze       Re-index the repository",
    "",
    "Database",
    "  just backup           Create database backup",
    "  just db-stats         Show database statistics",
  ].join("\n")
  console.log("")
  console.log(
    await gum("Service Commands", [
      "--bold",
      "--foreground",
      "212",
      "--width",
      "64",
      "--align",
      "center",
    ]),
  )
  console.log(await gum(lines, ["--border", "rounded", "--padding", "1 2", "--width", "64"]))
  console.log("")
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  const command = Bun.argv[2] ?? "status"

  switch (command) {
    case "status":
    case "s":
      await cmdStatus()
      break
    case "start":
    case "serve":
      await cmdStart()
      break
    case "stop":
      await cmdStop()
      break
    case "restart":
    case "r":
      await cmdRestart()
      break
    case "ports":
      cmdPorts()
      break
    case "logs":
      await cmdLogs()
      break
    case "service-help":
    case "h":
      await cmdServiceHelp()
      break
    default:
      console.log("Usage: bun scripts/server-lifecycle.ts <command>")
      console.log("")
      console.log("Commands:")
      console.log("  status         Show all service status")
      console.log("  start          Start dashboard server")
      console.log("  serve          Alias for start")
      console.log("  stop           Stop dashboard server")
      console.log("  restart        Restart dashboard server")
      console.log("  ports          Show listening ports")
      console.log("  logs           Show recent server logs")
      console.log("  service-help   Show available commands")
      console.log("")
      console.log("Examples:")
      console.log("  bun scripts/server-lifecycle.ts status")
      console.log("  bun scripts/server-lifecycle.ts restart")
      process.exit(1)
  }
}

main()
