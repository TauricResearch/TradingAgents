#!/usr/bin/env bun
/**
 * Server lifecycle: start means start, stop means stop.
 *
 * Usage: bun scripts/server-lifecycle.ts <start|stop|restart|status>
 */

import { execSync } from "node:child_process"
import { existsSync, mkdirSync } from "node:fs"
import { join } from "node:path"

const HOME = process.env.HOME ?? "~"
const RUNTIME = join(HOME, ".tradingagents")
const PID_FILE = join(RUNTIME, "server.pid")
const LOG_FILE = join(RUNTIME, "server.log")
const PREV_LOG = join(RUNTIME, "server.prev.log")
const PORT = parseInt(process.env.TA_DASHBOARD_PORT ?? "3000", 10)

function ensureDir() {
  if (!existsSync(RUNTIME)) mkdirSync(RUNTIME, { recursive: true })
}

function readPid(): number | null {
  try {
    const text = require("fs").readFileSync(PID_FILE, "utf-8")
    const pid = parseInt(text.trim(), 10)
    return isNaN(pid) ? null : pid
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

function killPort(port: number) {
  try {
    execSync(`lsof -ti :${port} | xargs kill -9 2>/dev/null`, { shell: "/bin/bash" })
  } catch {
    /* no process on port */
  }
}

function status() {
  const pid = readPid()
  const running = pid !== null && isAlive(pid)

  // Check port
  let portOccupied = false
  try {
    execSync(`lsof -ti :${PORT}`, { shell: "/bin/bash" })
    portOccupied = true
  } catch {
    portOccupied = false
  }

  // Check hledger
  let hledgerOk = false
  try {
    execSync("hledger -f ~/.hledger.journal balance --tree >/dev/null 2>&1")
    hledgerOk = true
  } catch {
    hledgerOk = false
  }

  const wName = 18
  const wStatus = 10

  console.log("")
  console.log("╔════════════════════════════════════════════════════╗")
  console.log("║  SERVICES                                          ║")
  console.log("╠════════════════════════════════════════════════════╣")
  console.log(`║  ${"Service".padEnd(wName)} ${"Status".padStart(wStatus)}   Detail             ║`)
  console.log("║  ──────────────────────────────────────────────────  ║")
  console.log(
    `║  ${"Dashboard".padEnd(wName)} ${(running ? "\x1b[32mrunning\x1b[0m" : "\x1b[31mstopped\x1b[0m").padStart(wStatus + 9)}   ${running ? `PID ${pid}` : `port ${PORT} free`}    ║`,
  )
  console.log(
    `║  ${"hledger".padEnd(wName)} ${(hledgerOk ? "\x1b[32mrunning\x1b[0m" : "\x1b[31merror\x1b[0m").padStart(wStatus + 9)}   journal loaded     ║`,
  )
  console.log("╚════════════════════════════════════════════════════╝")

  if (!running && portOccupied) {
    console.log("")
    console.log("  ⚠ Port occupied but PID file missing — run: just restart")
  }

  console.log("")
}

function start() {
  ensureDir()

  // Kill whatever is on the port
  killPort(PORT)

  // Kill old PID if different
  const oldPid = readPid()
  if (oldPid && isAlive(oldPid)) {
    try {
      process.kill(oldPid, "SIGKILL")
    } catch {}
  }

  // Rotate log
  try {
    require("fs").renameSync(LOG_FILE, PREV_LOG)
  } catch {}

  // Start server — child writes directly to log file, parent exits immediately
  const cmd = `nohup bun run src/server/index.tsx > "${LOG_FILE}" 2>&1 & echo $!`
  const pid = parseInt(execSync(cmd, { shell: "/bin/bash", encoding: "utf-8" }).trim(), 10)

  // Write PID
  require("fs").writeFileSync(PID_FILE, String(pid))

  console.log(`Server started (PID ${pid}, port ${PORT})`)
}

function stop() {
  const pid = readPid()
  if (!pid) {
    console.log("Server not running")
    return
  }

  if (!isAlive(pid)) {
    console.log("Server not running (stale PID removed)")
    try {
      require("fs").unlinkSync(PID_FILE)
    } catch {}
    return
  }

  console.log(`Stopping server (PID ${pid})...`)
  try {
    process.kill(pid, "SIGTERM")
  } catch {}

  // Wait up to 5s
  for (let i = 0; i < 10; i++) {
    require("fs").writeFileSync("/dev/null", "") // small sleep hack
    const start = Date.now()
    while (Date.now() - start < 500) {} // 500ms busy-wait
    if (!isAlive(pid)) {
      console.log("Server stopped")
      try {
        require("fs").unlinkSync(PID_FILE)
      } catch {}
      return
    }
  }

  // Force kill
  try {
    process.kill(pid, "SIGKILL")
  } catch {}
  try {
    require("fs").unlinkSync(PID_FILE)
  } catch {}
  console.log("Server killed")
}

function restart() {
  stop()
  start()
}

// ── Main ─────────────────────────────────────────────────────────────────────

const cmd = Bun.argv[2] ?? "status"

switch (cmd) {
  case "status":
  case "s":
    status()
    break
  case "start":
    start()
    break
  case "stop":
    stop()
    break
  case "restart":
  case "r":
    restart()
    break
  default:
    console.log("Usage: bun scripts/server-lifecycle.ts <start|stop|restart|status>")
    process.exit(1)
}
