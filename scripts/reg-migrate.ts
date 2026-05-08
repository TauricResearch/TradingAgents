#!/usr/bin/env bun
/**
 * Migrate document indexes to unified schema.
 *
 * Unified schema for all indexes:
 *   {
 *     "file": "filename.md",
 *     "date": "YYYY-MM-DD",
 *     "status": "done|open|accepted|canonical|...",
 *     "summary": "human-readable description",
 *     "tags": ["tag1", "tag2"],
 *     "meta": { registry-specific fields }
 *   }
 *
 * Usage:
 *   bun scripts/reg-migrate.ts --dry-run    # preview
 *   bun scripts/reg-migrate.ts --apply      # execute
 */

import { readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"

interface UnifiedEntry {
  file: string
  date: string
  status: string
  summary: string
  tags?: string[]
  meta?: Record<string, unknown>
}

function migrateBriefs(raw: Record<string, unknown>): UnifiedEntry {
  return {
    file: String(raw.file),
    date: String(raw.date),
    status: String(raw.status ?? "unknown"),
    summary: String(raw.summary ?? ""),
    meta: {
      epic: raw.epic ?? null,
    },
  }
}

function migrateDebriefs(raw: Record<string, unknown>): UnifiedEntry {
  return {
    file: String(raw.file),
    date: String(raw.date),
    status: "done",
    summary: String(raw.decision ?? raw.summary ?? ""),
    meta: {
      epic: raw.epic ?? null,
      adr: raw.adr ?? null,
      session: raw.session ?? null,
    },
  }
}

function migrateDecisions(raw: Record<string, unknown>): UnifiedEntry {
  return {
    file: String(raw.file),
    date: String(raw.date),
    status: String(raw.status ?? "unknown"),
    summary: String(raw.summary ?? ""),
    meta: {
      supersedes: raw.supersedes ?? null,
      superseded_by: raw.superseded_by ?? null,
    },
  }
}

function migratePlaybooks(raw: Record<string, unknown>): UnifiedEntry {
  return {
    file: String(raw.file),
    date: String(raw.last_mined ?? "2026-05-08"),
    status: raw.canonical === true ? "canonical" : "project",
    summary: String(raw.covers ?? ""),
    meta: {
      source: raw.source ?? null,
      mining_candidate: raw.mining_candidate ?? false,
      mining_note: raw.mining_note ?? null,
      last_mined: raw.last_mined ?? null,
    },
  }
}

function loadJsonl(path: string): Record<string, unknown>[] {
  const content = readFileSync(path, "utf-8").trim()
  if (!content) return []
  return content.split("\n").map((line) => JSON.parse(line))
}

function saveJsonl(path: string, entries: UnifiedEntry[]) {
  const lines = entries.map((e) => JSON.stringify(e)).join("\n")
  writeFileSync(path, lines + "\n")
}

const MIGRATIONS: Array<{
  registry: string
  path: string
  migrate: (raw: Record<string, unknown>) => UnifiedEntry
}> = [
  { registry: "briefs", path: "briefs/INDEX.jsonl", migrate: migrateBriefs },
  { registry: "debriefs", path: "debriefs/INDEX.jsonl", migrate: migrateDebriefs },
  { registry: "decisions", path: "decisions/INDEX.jsonl", migrate: migrateDecisions },
  { registry: "playbooks", path: "playbooks/REGISTRY.jsonl", migrate: migratePlaybooks },
]

function main() {
  const dryRun = Bun.argv.includes("--dry-run")
  const apply = Bun.argv.includes("--apply")

  if (!dryRun && !apply) {
    console.error("Usage: bun scripts/reg-migrate.ts --dry-run | --apply")
    process.exit(1)
  }

  for (const { registry, path, migrate } of MIGRATIONS) {
    const fullPath = join(process.cwd(), path)
    const raw = loadJsonl(fullPath)
    const unified = raw.map(migrate)

    console.log(`\n── ${registry.toUpperCase()} ──`)
    console.log(`  entries: ${unified.length}`)
    console.log(`  sample:`)
    console.log(
      JSON.stringify(unified[0], null, 2)
        .split("\n")
        .map((l) => `    ${l}`)
        .join("\n"),
    )

    if (apply) {
      const backupPath = `${fullPath}.backup`
      writeFileSync(backupPath, readFileSync(fullPath))
      saveJsonl(fullPath, unified)
      console.log(`  → migrated (backup: ${backupPath})`)
    }
  }

  if (dryRun) {
    console.log("\n\nRun with --apply to execute migration.")
  }
}

main()
