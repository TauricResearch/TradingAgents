#!/usr/bin/env bun

/**
 * Agent Coordination — Structured Handoff.
 *
 * Capture done/remaining/decisions for a task before closing.
 * This is the formal handoff protocol — run before td close.
 *
 * Usage:
 *   bun scripts/agent-handoff.ts td-abc123 --done "phase 1 done" --remaining "finish phase 2"
 *   bun scripts/agent-handoff.ts td-abc123 --done @done.txt   # from file
 *   bun scripts/agent-handoff.ts td-abc123 --decision "chose X over Y"
 */

import { execSync } from "node:child_process"
import { existsSync, readFileSync } from "node:fs"

const taskId = Bun.argv[2]
if (!taskId) {
  console.error("Usage: bun scripts/agent-handoff.ts <task-id> [options]")
  console.error("  --done <text>         completed item (repeatable)")
  console.error("  --remaining <text>    outstanding item (repeatable)")
  console.error("  --decision <text>     decision made (repeatable)")
  console.error("  --note <text>        simple note")
  console.error("  --done @file.txt      read from file (one line per item)")
  process.exit(1)
}

function sh(cmd: string): { ok: boolean; out: string } {
  try {
    return { ok: true, out: execSync(cmd, { encoding: "utf8", timeout: 15000 }).trim() }
  } catch (e: unknown) {
    return { ok: false, out: (e as Error).message }
  }
}

function green(msg: string) {
  console.log(`\x1b[32m✓\x1b[0m ${msg}`)
}

function readItems(prefix: string): string[] {
  const items: string[] = []
  for (let i = 3; i < Bun.argv.length; i++) {
    const arg = Bun.argv[i]
    if (arg === prefix && Bun.argv[i + 1] && !Bun.argv[i + 1].startsWith("--")) {
      const val = Bun.argv[++i]
      if (val.startsWith("@")) {
        const file = val.slice(1)
        if (existsSync(file)) {
          items.push(
            ...readFileSync(file, "utf8")
              .split("\n")
              .filter((l) => l.trim()),
          )
        }
      } else {
        items.push(val)
      }
    }
  }
  return items
}

const done = readItems("--done")
const remaining = readItems("--remaining")
const decisions = readItems("--decision")
const noteIdx = Bun.argv.indexOf("--note")
const note = noteIdx > 0 ? Bun.argv[noteIdx + 1] : null

// Build td handoff command
const args: string[] = [taskId]

if (note) {
  args.push("--note", note)
} else {
  for (const d of done) {
    args.push("--done", d)
  }
  for (const r of remaining) {
    args.push("--remaining", r)
  }
  for (const d of decisions) {
    args.push("--decision", d)
  }
}

// Capture before state
const show = sh(`td show ${taskId} 2>/dev/null`)
const title = show.out.match(/^[^:]+/)?.[0]?.trim() || taskId
const status = show.out.match(/Status:\s*\[(\w+)\]/)?.[1] || "unknown"

console.log("")
console.log(`\x1b[36mHandoff: ${title}\x1b[0m`)
console.log(`  Status before: ${status}`)
if (done.length) console.log(`  Done: ${done.join(", ")}`)
if (remaining.length) console.log(`  Remaining: ${remaining.join(", ")}`)
if (decisions.length) console.log(`  Decisions: ${decisions.join("; ")}`)
console.log("")

// Run handoff
const cmd = `td handoff ${args.join(" ")}`
const result = sh(cmd)

if (result.ok) {
  green(`Handoff captured for ${taskId}`)
  if (result.out) console.log(result.out)
} else {
  console.error(`\x1b[31mHandoff failed:\x1b[0m ${result.out}`)
  process.exit(1)
}

console.log("")
console.log(
  `\x1b[32m✓ Handoff done.\x1b[0m Next agent: \x1b[33mtd show ${taskId}\x1b[0m to see context.`,
)
console.log("")
