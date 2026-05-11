#!/usr/bin/env bun
/**
 * Agent Coordination — Sync State.
 *
 * Check: my session vs main, staged changes, task ownership, collisions.
 * Run before starting work or after resuming a session.
 *
 * Usage:
 *   bun scripts/agent-sync.ts              # full sync
 *   bun scripts/agent-sync.ts --my-tasks   # just my tasks
 *   bun scripts/agent-sync.ts --collisions # just collision check
 */

import { execSync } from "node:child_process"

const mode = Bun.argv.includes("--my-tasks")
  ? "tasks"
  : Bun.argv.includes("--collisions")
    ? "collisions"
    : "full"

function sh(cmd: string, fallback = ""): string {
  try {
    return execSync(cmd, { encoding: "utf8", timeout: 10000 }).trim()
  } catch {
    return fallback
  }
}

// ── Session info ──────────────────────────────────────────────────────────

const whoami = sh("td whoami 2>/dev/null")
const sessionId = whoami.match(/(\w+-\w{6})/)?.[1] || "unknown"
const wsRaw = sh("td ws current 2>/dev/null")
const workspace = wsRaw.split("\n")[0] || "(no workspace)"

// ── My tasks ─────────────────────────────────────────────────────────────

const myTasks = sh("td list --status in_progress 2>/dev/null", "(none)")
const myCount = (myTasks.match(/in_progress/g) || []).length

// ── Git state ────────────────────────────────────────────────────────────

sh("git fetch origin main 2>/dev/null", "")
const behind = parseInt(sh("git rev-list --count HEAD..origin/main 2>/dev/null") || "0", 10)
const staged = sh("git diff --cached --stat 2>/dev/null | tail -3") || "(none)"
const unstaged = sh("git status --short 2>/dev/null") || "(none)"

// ── Collision detection ─────────────────────────────────────────────────

function checkCollisions() {
  const list = sh("td list --status in_progress 2>/dev/null", "")
  const ids = [...list.matchAll(/td-([a-f0-9]+)/g)].map((m) => m[0])

  if (ids.length === 0) return "  No in-progress tasks."

  const claimedFiles = new Map<string, string[]>()
  for (const id of ids) {
    const files = sh(`td files ${id} 2>/dev/null`)
      .split("\n")
      .filter((f) => f.trim() && !f.includes("No files") && !f.includes("No linked"))
    for (const file of files) {
      const clean = file.replace(/^\s*[*!]?\s*/, "").trim()
      if (clean) {
        if (!claimedFiles.has(clean)) claimedFiles.set(clean, [])
        claimedFiles.get(clean)?.push(id)
      }
    }
  }

  const collisions = [...claimedFiles.entries()].filter(([, ids]) => ids.length > 1)
  if (collisions.length === 0) return "  No file collisions detected."

  return collisions.map(([file, ids]) => `  ⚠  ${file}: claimed by ${ids.join(", ")}`).join("\n")
}

// ── Output ───────────────────────────────────────────────────────────────

console.log("")
console.log("\x1b[36m── Session ──────────────────────────────\x1b[0m")
console.log(`  ID:        ${sessionId}`)
console.log(`  Workspace: ${workspace}`)
console.log("")
console.log("\x1b[36m── My Tasks ─────────────────────────────\x1b[0m")
if (mode !== "collisions") {
  console.log(`  In-progress: ${myCount}`)
  if (myCount > 0) {
    console.log(myTasks.split("\n").slice(0, 10).join("\n"))
  } else {
    console.log("  (none — run agent-claim.ts to start)")
  }
}
console.log("")
console.log("\x1b[36m── Git ───────────────────────────────────\x1b[0m")
console.log(`  Behind main: ${behind} commits`)
console.log(`  Staged:\n${staged}`)
if (unstaged !== "(none)") {
  console.log(`  Unstaged:\n${unstaged}`)
}
console.log("")
console.log("\x1b[36m── File Collisions ───────────────────────\x1b[0m")
console.log(checkCollisions())
console.log("")
console.log("\x1b[33mHint:\x1b[0m Run `bun scripts/agent-claim.ts <id>` before touching any file.")
console.log("")
