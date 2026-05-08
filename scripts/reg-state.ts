#!/usr/bin/env bun
/**
 * Project State Reporter.
 *
 * Consolidates status across all silo compartments:
 *   - briefs: open vs done count, recent items
 *   - debriefs: recent sessions, coverage
 *   - decisions: accepted vs proposed, superseded
 *   - playbooks: canonical vs project, mining candidates
 *   - docs: document count, schema coverage
 *   - td: open / in_progress / reviewable tasks
 *
 * Usage:
 *   bun scripts/reg-state.ts              # full report
 *   bun scripts/reg-state.ts --compact    # one-line summary
 *   bun scripts/reg-state.ts --tasks      # just tasks
 *   bun scripts/reg-state.ts --docs       # just document health
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"

interface UnifiedEntry {
  file: string
  date: string
  status: string
  summary: string
  meta?: Record<string, unknown>
}

interface RegistryDef {
  name: string
  path: string
}

const REGISTRIES: RegistryDef[] = [
  { name: "briefs", path: "briefs/INDEX.jsonl" },
  { name: "debriefs", path: "debriefs/INDEX.jsonl" },
  { name: "decisions", path: "decisions/INDEX.jsonl" },
  { name: "playbooks", path: "playbooks/REGISTRY.jsonl" },
  { name: "docs", path: "docs/INDEX.jsonl" },
]

function loadJsonl(path: string): UnifiedEntry[] {
  try {
    const content = readFileSync(path, "utf-8").trim()
    if (!content) return []
    return content.split("\n").map((line) => JSON.parse(line))
  } catch {
    return []
  }
}

function countByStatus(entries: UnifiedEntry[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const e of entries) {
    const s = (e.status ?? "unknown").toLowerCase()
    counts.set(s, (counts.get(s) ?? 0) + 1)
  }
  return counts
}

function recent(entries: UnifiedEntry[], days: number): UnifiedEntry[] {
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - days)
  return entries
    .filter((e) => new Date(e.date) >= cutoff)
    .sort((a, b) => b.date.localeCompare(a.date))
}

function formatStatusCounts(counts: Map<string, number>): string {
  const pairs = [...counts.entries()].sort((a, b) => b[1] - a[1])
  return pairs.map(([s, n]) => `${n} ${s}`).join(" | ")
}

function section(name: string, entries: UnifiedEntry[], compact = false) {
  if (compact) {
    const counts = countByStatus(entries)
    console.log(`  ${name.padEnd(12)} ${entries.length} total (${formatStatusCounts(counts)})`)
    return
  }

  const counts = countByStatus(entries)
  console.log(`\n── ${name.toUpperCase()} ──`)
  console.log(`  total: ${entries.length} (${formatStatusCounts(counts)})`)

  const recentItems = recent(entries, 7)
  if (recentItems.length > 0) {
    console.log(`  last 7 days:`)
    for (const e of recentItems.slice(0, 5)) {
      const flag = e.status.toLowerCase() === "open" ? "⚠" : "✓"
      console.log(`    ${flag} ${e.date} ${e.file}`)
    }
  }
}

function tdStatus() {
  try {
    const result = Bun.spawnSync({ cmd: ["td", "list", "--status", "open"] })
    const open = new TextDecoder()
      .decode(result.stdout)
      .trim()
      .split("\n")
      .filter((l) => l.includes("open")).length

    const ipResult = Bun.spawnSync({ cmd: ["td", "list", "--status", "in_progress"] })
    const inProgress = new TextDecoder()
      .decode(ipResult.stdout)
      .trim()
      .split("\n")
      .filter((l) => l.includes("in_progress")).length

    const revResult = Bun.spawnSync({ cmd: ["td", "reviewable"] })
    const reviewable = new TextDecoder()
      .decode(revResult.stdout)
      .trim()
      .split("\n")
      .filter((l) => l.length > 0).length

    return { open, inProgress, reviewable }
  } catch {
    return { open: 0, inProgress: 0, reviewable: 0 }
  }
}

function tdTasks() {
  try {
    const result = Bun.spawnSync({ cmd: ["td", "list", "--status", "open"] })
    const lines = new TextDecoder().decode(result.stdout).trim().split("\n")
    return lines.filter((l) => l.trim().length > 0)
  } catch {
    return []
  }
}

function tdInProgress() {
  try {
    const result = Bun.spawnSync({ cmd: ["td", "list", "--status", "in_progress"] })
    const lines = new TextDecoder().decode(result.stdout).trim().split("\n")
    return lines.filter((l) => l.trim().length > 0)
  } catch {
    return []
  }
}

function registryHealth(): boolean {
  try {
    const result = Bun.spawnSync({ cmd: ["bun", "scripts/reg-sync.ts", "--all"] })
    const output = new TextDecoder().decode(result.stdout)
    return !output.includes("⚠")
  } catch {
    return false
  }
}

function main() {
  const compact = Bun.argv.includes("--compact")
  const tasksOnly = Bun.argv.includes("--tasks")
  const docsOnly = Bun.argv.includes("--docs")

  if (tasksOnly) {
    const { open, inProgress, reviewable } = tdStatus()
    console.log(`── TASKS ──`)
    console.log(`  open:        ${open}`)
    console.log(`  in_progress: ${inProgress}`)
    console.log(`  reviewable:  ${reviewable}`)

    const openTasks = tdTasks()
    if (openTasks.length > 0) {
      console.log(`\n  Open tasks:`)
      for (const t of openTasks) console.log(`    ${t}`)
    }

    const ipTasks = tdInProgress()
    if (ipTasks.length > 0) {
      console.log(`\n  In progress:`)
      for (const t of ipTasks) console.log(`    ${t}`)
    }
    return
  }

  if (compact) {
    console.log("Project State")
    const { open, inProgress, reviewable } = tdStatus()
    console.log(`  tasks: ${open} open | ${inProgress} in_progress | ${reviewable} reviewable`)
    console.log(`  registries: ${registryHealth() ? "✓ all clean" : "⚠ drift detected"}`)
  }

  if (docsOnly || !tasksOnly) {
    for (const { name, path } of REGISTRIES) {
      const fullPath = join(process.cwd(), path)
      const entries = loadJsonl(fullPath)
      section(name, entries, compact)
    }
  }

  if (!docsOnly && !tasksOnly) {
    const { open, inProgress, reviewable } = tdStatus()
    console.log(`\n── TASKS (td) ──`)
    console.log(`  open:        ${open}`)
    console.log(`  in_progress: ${inProgress}`)
    console.log(`  reviewable:  ${reviewable}`)

    const openTasks = tdTasks()
    if (openTasks.length > 0) {
      console.log(`\n  Open tasks:`)
      for (const t of openTasks.slice(0, 5)) console.log(`    ${t}`)
    }

    const ipTasks = tdInProgress()
    if (ipTasks.length > 0) {
      console.log(`\n  In progress:`)
      for (const t of ipTasks.slice(0, 5)) console.log(`    ${t}`)
    }
  }

  if (!compact && !tasksOnly) {
    const healthy = registryHealth()
    console.log(`\n── HEALTH ──`)
    console.log(
      `  registries: ${healthy ? "✓ all indexes match filesystem" : "⚠ drift detected (run: just reg-sync)"}`,
    )
    console.log(`  commit gate: just check (biome + tsc + db gate + reg sync)`)
  }
}

main()
