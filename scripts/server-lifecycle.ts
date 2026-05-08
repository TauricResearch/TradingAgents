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
  if (pid && isAlive(pid)) {
    console.log(`Server running (PID ${pid}, port ${PORT})`)
  } else {
    console.log(`Server stopped (port ${PORT})`)
  }
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
