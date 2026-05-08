#!/usr/bin/env bun
/**
 * Validate JSONL indexes against unified schema.
 *
 * Unified schema: { file, date, status, summary, meta? }
 *
 * Usage:
 *   bun scripts/reg-check.ts          # validate all registries
 *   bun scripts/reg-check.ts briefs   # validate single registry
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"

const REQUIRED = ["file", "date", "status", "summary"]
const LEXICON_REQUIRED = ["file", "id", "date", "status", "type", "summary"]

const REGISTRIES: Record<string, string> = {
  briefs: "briefs/INDEX.jsonl",
  debriefs: "debriefs/INDEX.jsonl",
  decisions: "decisions/INDEX.jsonl",
  playbooks: "playbooks/REGISTRY.jsonl",
  docs: "docs/INDEX.jsonl",
  lexicon: "silo-conceptual-lexicon.jsonl",
}

function checkRegistry(name: string, path: string): boolean {
  const fullPath = join(process.cwd(), path)
  let ok = true

  try {
    const content = readFileSync(fullPath, "utf-8").trim()
    if (!content) {
      console.error(`  ✗ ${name} — empty`)
      return false
    }

    const lines = content.split("\n")
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim()
      if (!line) continue

      let obj: Record<string, unknown>
      try {
        obj = JSON.parse(line)
      } catch {
        console.error(`  ✗ ${name}:${i + 1} — invalid JSON`)
        ok = false
        continue
      }

      const requiredFields = name === "lexicon" ? LEXICON_REQUIRED : REQUIRED
      for (const field of requiredFields) {
        if (obj[field] == null) {
          console.error(`  ✗ ${name}:${i + 1} — missing "${field}"`)
          ok = false
        }
      }
    }

    if (ok) {
      console.log(`  ✓ ${name} (${lines.length} entries)`)
    }
  } catch (e) {
    console.error(`  ✗ ${name} — ${e instanceof Error ? e.message : String(e)}`)
    ok = false
  }

  return ok
}

function main() {
  const target = Bun.argv[2]
  let allOk = true

  if (target) {
    const path = REGISTRIES[target]
    if (!path) {
      console.error(`Unknown registry: ${target}`)
      console.error(`Known: ${Object.keys(REGISTRIES).join(", ")}`)
      process.exit(1)
    }
    console.log(`Validating ${target}...`)
    if (!checkRegistry(target, path)) allOk = false
  } else {
    console.log("Validating registries...")
    for (const [name, path] of Object.entries(REGISTRIES)) {
      if (!checkRegistry(name, path)) allOk = false
    }
  }

  if (!allOk) process.exit(1)
}

main()
