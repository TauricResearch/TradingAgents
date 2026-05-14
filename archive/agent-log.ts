#!/usr/bin/env bun
/**
 * Agent Coordination — Log Progress.
 *
 * Append a timestamped log entry to a task.
 * Usage:
 *   bun scripts/agent-log.ts td-abc123 "completed phase 1"
 *   bun scripts/agent-log.ts td-abc123 "blocked on X" --type blocked
 */

import { execSync } from "node:child_process"

const taskId = Bun.argv[2]
const message = Bun.argv[3]
const isBlocked = Bun.argv.includes("--blocked")

if (!taskId || !message) {
  console.error("Usage: bun scripts/agent-log.ts <task-id> <message> [--blocked]")
  process.exit(1)
}

function sh(cmd: string): string {
  try {
    return execSync(cmd, { encoding: "utf8", timeout: 10000 }).trim()
  } catch {
    return ""
  }
}

const ts = new Date().toLocaleTimeString("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
})

const prefix = isBlocked ? `[${ts}] 🔴 BLOCKED: ${message}` : `[${ts}] ${message}`

const out = sh(`td log ${taskId} "${prefix}"`)
if (out) {
  console.log(`\x1b[32m✓\x1b[0m Logged to ${taskId}: ${message}`)
  console.log(out)
} else {
  console.log(`\x1b[32m✓\x1b[0m Logged to ${taskId}: ${message}`)
}
