#!/usr/bin/env bun
/**
 * Migrate lexicon from v1 (unified schema) to v2 (merged schema with CTX features).
 *
 * Changes:
 *   - Add stable "id" field (term-001, oh-001, etc.)
 *   - Add "type" field (term, operational-heuristic, pattern, failure-mode, philosophy)
 *   - Replace flat "meta.related" with structured "meta.tags" using bracket notation
 *   - Keep all existing fields for backward compatibility
 *
 * Usage:
 *   bun scripts/lexicon-migrate.ts --dry-run
 *   bun scripts/lexicon-migrate.ts --apply
 */

import { readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"

interface V1Entry {
  file: string
  date: string
  status: string
  summary: string
  meta: {
    category: string
    origin: string
    heuristic: string
    usage: string
    related?: string[]
    coined_by: string
    [key: string]: unknown
  }
}

interface V2Entry {
  file: string
  id: string
  date: string
  status: string
  type: string
  summary: string
  meta: {
    category: string
    origin: string
    heuristic: string
    usage: string
    tags: string[]
    related: string[]
    coined_by: string
    [key: string]: unknown
  }
}

const TYPE_MAP: Record<string, string> = {
  process: "operational-heuristic",
  architecture: "pattern",
  pattern: "pattern",
  "failure-mode": "operational-heuristic",
  philosophy: "term",
}

const CATEGORY_TAG: Record<string, string> = {
  process: "[#process]",
  architecture: "[#architecture]",
  pattern: "[#pattern]",
  "failure-mode": "[#failure-mode]",
  philosophy: "[#philosophy]",
}

function generateId(index: number, type: string): string {
  const prefix = type === "operational-heuristic" ? "oh" : "term"
  return `${prefix}-${String(index).padStart(3, "0")}`
}

function migrateEntry(entry: V1Entry, index: number): V2Entry {
  const category = entry.meta.category ?? "process"
  const type = TYPE_MAP[category] ?? "term"
  const id = generateId(index + 1, type)

  const tags: string[] = [CATEGORY_TAG[category] ?? `[#${category}]`]

  // Add quality tag based on status
  if (entry.status === "active") tags.push("[Quality: silver]")
  if (entry.status === "draft") tags.push("[Quality: bronze]")

  // Add related terms as tags
  if (entry.meta.related) {
    for (const r of entry.meta.related) {
      tags.push(`[Related: ${r}]`)
    }
  }

  // Add origin tag
  if (entry.meta.origin) {
    tags.push(`[Origin: ${entry.meta.origin}]`)
  }

  return {
    file: entry.file,
    id,
    date: entry.date,
    status: entry.status,
    type,
    summary: entry.summary,
    meta: {
      ...entry.meta,
      tags,
      related: entry.meta.related ?? [],
    },
  }
}

function loadJsonl(path: string): V1Entry[] {
  const content = readFileSync(path, "utf-8").trim()
  if (!content) return []
  return content.split("\n").map((line) => JSON.parse(line))
}

function saveJsonl(path: string, entries: V2Entry[]) {
  const lines = entries.map((e) => JSON.stringify(e)).join("\n")
  writeFileSync(path, `${lines}\n`)
}

function main() {
  const dryRun = Bun.argv.includes("--dry-run")
  const apply = Bun.argv.includes("--apply")

  if (!dryRun && !apply) {
    console.error("Usage: bun scripts/lexicon-migrate.ts --dry-run | --apply")
    process.exit(1)
  }

  const path = join(process.cwd(), "debriefs/lexicon.jsonl")
  const entries = loadJsonl(path)
  const migrated = entries.map((e, i) => migrateEntry(e, i))

  console.log(`── LEXICON MIGRATION ──`)
  console.log(`  entries: ${entries.length}`)
  console.log(`\n  Sample (first entry):`)
  console.log(JSON.stringify(migrated[0], null, 2))
  console.log(`\n  Sample (last entry):`)
  console.log(JSON.stringify(migrated[migrated.length - 1], null, 2))

  const typeCounts = new Map<string, number>()
  for (const e of migrated) {
    typeCounts.set(e.type, (typeCounts.get(e.type) ?? 0) + 1)
  }
  console.log(`\n  Type distribution:`)
  for (const [t, n] of typeCounts) {
    console.log(`    ${t}: ${n}`)
  }

  if (apply) {
    const backupPath = `${path}.v1.backup`
    writeFileSync(backupPath, readFileSync(path))
    saveJsonl(path, migrated)
    console.log(`\n  → migrated (backup: ${backupPath})`)
  } else {
    console.log(`\n  Run with --apply to execute migration.`)
  }
}

main()
