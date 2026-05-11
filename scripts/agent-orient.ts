#!/usr/bin/env bun

/**
 * Agent Coordination — Orientation.
 *
 * Full session startup: git state + td session + what's in flight.
 * Run this at the start of every new agent session.
 *
 * Usage:
 *   bun scripts/agent-orient.ts            # full report
 *   bun scripts/agent-orient.ts --compact  # one-line summary
 *   bun scripts/agent-orient.ts --next      # what to work on next
 */

import { execSync } from "node:child_process"

const mode = Bun.argv.includes("--compact")
  ? "compact"
  : Bun.argv.includes("--next")
    ? "next"
    : "full"

function sh(cmd: string): string {
  try {
    return execSync(cmd, { encoding: "utf8", timeout: 5000 }).trim()
  } catch {
    return "(unavailable)"
  }
}

function section(label: string, content: string, color = "CYAN") {
  const fmt: Record<string, string> = {
    CYAN: "\x1b[36m",
    GREEN: "\x1b[32m",
    YELLOW: "\x1b[33m",
    RED: "\x1b[31m",
    RESET: "\x1b[0m",
  }
  return `${fmt[color]}${label}${fmt.RESET}\n${content}`
}

// ── Git state ───────────────────────────────────────────────────────────

function gitState() {
  const branch = sh("git branch -v 2>/dev/null | grep '^\\*'").replace(/^\* /, "").trim()
  const status = sh("git status --short 2>/dev/null")
  const behind = parseInt(sh("git rev-list --count HEAD..origin/main 2>/dev/null") || "0", 10)

  if (mode === "compact") {
    return `${branch} | behind main: ${behind} | changes: ${status ? "YES" : "none"}`
  }

  return [
    `  Branch:    ${branch}`,
    `  Behind:    ${behind} commits`,
    `  Changes:   ${status || "(none)"}`,
  ].join("\n")
}

// ── TD session state ──────────────────────────────────────────────────────

function tdState() {
  if (mode === "compact") {
    const session = sh("td whoami 2>/dev/null | grep session | awk '{print $NF}'").trim()
    const ws = sh("td ws current 2>/dev/null").split("\n")[0] || "(no workspace)"
    const mine =
      sh("td list --status in_progress 2>/dev/null | grep -c 'in_progress'").trim() || "0"
    return `session: ${session || "?"} | workspace: ${ws} | my tasks: ${mine}`
  }

  const usage = sh("td usage 2>/dev/null").split("\n").slice(0, 25).join("\n")
  const ws = sh("td ws current 2>/dev/null")
  return [usage, "", ws].join("\n")
}

// ── What's in flight ──────────────────────────────────────────────────────

function tdInFlight() {
  const list = sh("td list 2>/dev/null")
  const reviewable = sh("td reviewable 2>/dev/null").split("\n").slice(0, 10).join("\n")

  if (mode === "compact") {
    const inProg = (list.match(/in_progress/g) || []).length
    const inReview = (list.match(/in_review/g) || []).length
    return `in_progress: ${inProg} | in_review: ${inReview} | reviewable: ${reviewable ? "YES" : "none"}`
  }

  return [list, "", reviewable ? `Reviewable:\n${reviewable}` : ""].join("\n")
}

// ── Recommended next action ───────────────────────────────────────────────

function tdNext() {
  const next = sh("td next 2>/dev/null").split("\n").slice(0, 15).join("\n")
  const ready = sh("td ready 2>/dev/null").split("\n").slice(0, 10).join("\n")
  return `Next:\n${next}\n\nReady:\n${ready}`
}

// ── File collisions ───────────────────────────────────────────────────────

function fileCollisions() {
  // Find all in_progress tasks and check for file conflicts
  const list = sh("td list --status in_progress 2>/dev/null")
  const taskIds = [...list.matchAll(/td-([a-f0-9]+)/g)].map((m) => m[0])

  if (taskIds.length === 0) return "  No in-progress tasks."

  const claimedFiles = new Map<string, string[]>()
  for (const id of taskIds) {
    const files = sh(`td files ${id} 2>/dev/null`)
      .split("\n")
      .filter((f) => f.trim() && !f.includes("No files"))
    if (files.length > 0) {
      for (const f of files) {
        if (!claimedFiles.has(f)) claimedFiles.set(f, [])
        claimedFiles.get(f)?.push(id)
      }
    }
  }

  const collisions = [...claimedFiles.entries()].filter(([, ids]) => ids.length > 1)
  if (collisions.length === 0) return "  No file collisions detected."

  return collisions.map(([file, ids]) => `  ⚠ ${file}: claimed by ${ids.join(", ")}`).join("\n")
}

// ── Output ────────────────────────────────────────────────────────────────

console.log("")
console.log("\x1b[36m═══════════════════════════════════\x1b[0m")
console.log("\x1b[36m  AGENT ORIENTATION\x1b[0m")
console.log("\x1b═══════════════════════════════════\x1b[0m")
console.log("")

console.log(section("Git:", gitState()))
console.log("")
console.log(section("Session:", tdState()))
console.log("")

if (mode === "next") {
  console.log(section("Recommended next:", tdNext()))
} else {
  console.log(section("In flight:", tdInFlight()))
  console.log("")
  console.log(section("File collisions:", fileCollisions()))
  console.log("")
  console.log(
    "\x1b[33mHint:\x1b[0m Run `bun scripts/agent-orient.ts --next` to see recommended tasks.",
  )
}

console.log("")
