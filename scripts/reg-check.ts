#!/usr/bin/env bun
/**
 * Validate all JSONL registries.
 *
 * Checks required fields are present in each registry.
 * Replaces inline jq validation in justfile.
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"

interface Registry {
  file: string
  required: string[]
}

const REGISTRIES: Registry[] = [
  {
    file: "briefs/INDEX.jsonl",
    required: ["file", "status", "date", "summary"],
  },
  {
    file: "debriefs/INDEX.jsonl",
    required: ["file", "date", "decision"],
  },
  {
    file: "decisions/INDEX.jsonl",
    required: ["file", "date", "status", "summary"],
  },
  {
    file: "playbooks/REGISTRY.jsonl",
    required: ["file", "canonical", "covers"],
  },
]

function checkRegistry(registry: Registry): boolean {
  const path = join(process.cwd(), registry.file)
  let ok = true

  try {
    const content = readFileSync(path, "utf-8").trim()
    if (!content) {
      console.error(`  ✗ ${registry.file} — empty`)
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
        console.error(`  ✗ ${registry.file}:${i + 1} — invalid JSON`)
        ok = false
        continue
      }

      for (const field of registry.required) {
        if (obj[field] == null) {
          console.error(`  ✗ ${registry.file}:${i + 1} — missing "${field}"`)
          ok = false
        }
      }
    }

    if (ok) {
      console.log(`  ✓ ${registry.file} (${lines.length} entries)`)
    }
  } catch (e) {
    console.error(`  ✗ ${registry.file} — ${e instanceof Error ? e.message : String(e)}`)
    ok = false
  }

  return ok
}

function main() {
  console.log("Validating registries...")
  let allOk = true
  for (const registry of REGISTRIES) {
    if (!checkRegistry(registry)) allOk = false
  }
  if (!allOk) process.exit(1)
}

main()
