#!/usr/bin/env bun
/**
 * Check if a document index is up-to-date, or regenerate it.
 *
 * Compares files on disk against entries in the index JSONL.
 * Reports:
 *   - MISSING: files on disk not in index (need to be added)
 *   - STALE:   entries in index for files that no longer exist
 *
 * Usage:
 *   bun scripts/reg-sync.ts briefs          # check briefs index
 *   bun scripts/reg-sync.ts docs            # check docs index
 *   bun scripts/reg-sync.ts --all           # check all known registries
 *   bun scripts/reg-sync.ts briefs --fix    # regenerate index from files
 */

import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs"
import { join, relative } from "node:path"

interface RegistryDef {
  indexPath: string
  dirPath: string
  filePattern: RegExp
  exclude?: RegExp[]
}

const REGISTRIES: Record<string, RegistryDef> = {
  briefs: {
    indexPath: "briefs/INDEX.jsonl",
    dirPath: "briefs",
    filePattern: /\.md$/,
    exclude: [/INDEX\.jsonl/],
  },
  debriefs: {
    indexPath: "debriefs/INDEX.jsonl",
    dirPath: "debriefs",
    filePattern: /\.md$/,
    exclude: [/INDEX\.jsonl/],
  },
  decisions: {
    indexPath: "decisions/INDEX.jsonl",
    dirPath: "decisions",
    filePattern: /\.md$/,
    exclude: [/INDEX\.jsonl/],
  },
  playbooks: {
    indexPath: "playbooks/REGISTRY.jsonl",
    dirPath: "playbooks",
    filePattern: /\.md$/,
    exclude: [/REGISTRY\.jsonl/, /README\.md/],
  },
  docs: {
    indexPath: "docs/INDEX.jsonl",
    dirPath: "docs",
    filePattern: /\.md$/,
    exclude: [/INDEX\.jsonl/],
  },
}

function loadIndex(path: string): Array<{ file: string }> {
  try {
    const content = readFileSync(path, "utf-8").trim()
    if (!content) return []
    return content.split("\n").map((line) => JSON.parse(line))
  } catch {
    return []
  }
}

function listFiles(def: RegistryDef): string[] {
  const results: string[] = []

  function walk(dir: string) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const fullPath = join(dir, entry.name)
      if (entry.isDirectory()) {
        walk(fullPath)
      } else if (entry.isFile() && def.filePattern.test(entry.name)) {
        const relPath = relative(def.dirPath, fullPath)
        if (def.exclude?.some((re) => re.test(relPath))) continue
        results.push(relPath)
      }
    }
  }

  walk(def.dirPath)
  return results.sort()
}

function checkRegistry(name: string, def: RegistryDef, fix: boolean): boolean {
  const indexEntries = loadIndex(def.indexPath)
  const indexedFiles = new Set(indexEntries.map((e) => e.file))
  const diskFiles = new Set(listFiles(def))

  const missing = [...diskFiles].filter((f) => !indexedFiles.has(f))
  const stale = [...indexedFiles].filter((f) => !diskFiles.has(f))

  console.log(`\n── ${name.toUpperCase()} ──`)
  console.log(`  index: ${def.indexPath} (${indexedFiles.size} entries)`)
  console.log(`  files: ${def.dirPath} (${diskFiles.size} files)`)

  if (missing.length === 0 && stale.length === 0) {
    console.log(`  ✓ up to date`)
    return true
  }

  if (missing.length > 0) {
    console.log(`  ⚠ MISSING from index (${missing.length}):`)
    for (const f of missing) console.log(`    + ${f}`)
  }

  if (stale.length > 0) {
    console.log(`  ⚠ STALE entries (${stale.length}):`)
    for (const f of stale) console.log(`    - ${f}`)
  }

  if (fix) {
    console.log(`  → regenerating index...`)

    // Keep existing entries for files that still exist
    const kept = indexEntries.filter((e) => diskFiles.has(e.file))
    // Create stub entries for new files
    const added = missing.map((f) => {
      const fullPath = join(def.dirPath, f)
      const stat = statSync(fullPath)
      const date = stat.mtime.toISOString().split("T")[0]
      return {
        file: f,
        date,
        status: "active",
        summary: "(auto-generated — add description)",
        meta: {},
      }
    })

    const merged = [...kept, ...added].sort((a, b) => a.file.localeCompare(b.file))
    const lines = merged.map((e) => JSON.stringify(e)).join("\n")
    writeFileSync(def.indexPath, `${lines}\n`)
    console.log(`  ✓ regenerated: ${merged.length} entries`)
  }

  return false
}

function main() {
  const args = Bun.argv.slice(2)
  const fix = args.includes("--fix")
  const all = args.includes("--all")
  const targets = args.filter((a) => !a.startsWith("--"))

  if (all) {
    let ok = true
    for (const [name, def] of Object.entries(REGISTRIES)) {
      if (!checkRegistry(name, def, fix)) ok = false
    }
    if (!ok && !fix) {
      console.log("\nRun with --fix to regenerate indexes.")
      process.exit(1)
    }
    return
  }

  if (targets.length === 0) {
    console.error("Usage: bun scripts/reg-sync.ts <registry|--all> [--fix]")
    console.error(`Registries: ${Object.keys(REGISTRIES).join(", ")}`)
    process.exit(1)
  }

  let ok = true
  for (const target of targets) {
    const def = REGISTRIES[target]
    if (!def) {
      console.error(`Unknown registry: ${target}`)
      continue
    }
    if (!checkRegistry(target, def, fix)) ok = false
  }

  if (!ok && !fix) {
    console.log("\nRun with --fix to regenerate indexes.")
    process.exit(1)
  }
}

main()
