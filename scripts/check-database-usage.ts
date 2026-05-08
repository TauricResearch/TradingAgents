#!/usr/bin/env bun
/**
 * Gate: Only src/lib/db.ts may create SQLite Database instances.
 *
 * All code must use DatabaseFactory.connect() / DatabaseFactory.get().
 * See: playbooks/sqlite-playbook.md
 */

import { readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"

const EXCLUDED_DIRS = ["node_modules", ".git", "debriefs", "briefs"]
const ALLOWED_FILE = join("src", "lib", "db.ts")

function walk(dir: string, files: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (!EXCLUDED_DIRS.includes(entry.name)) walk(path, files)
    } else if (
      entry.name.endsWith(".ts") ||
      entry.name.endsWith(".tsx") ||
      entry.name.endsWith(".js")
    ) {
      files.push(path)
    }
  }
  return files
}

const root = join(import.meta.dir, "..")
const allFiles = walk(root)
let errors = 0

for (const file of allFiles) {
  const rel = file.replace(`${root}/`, "")
  if (rel === ALLOWED_FILE) continue

  const content = readFileSync(file, "utf-8")
  const lines = content.split("\n")

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    // Strip end-of-line comments
    const code = line.replace(/\/\/.*$/, "")
    const match = /\bnew\s+Database\s*\(/.exec(code)
    if (!match) continue
    const idx = match.index

    // Check if the match is inside a string literal by counting quotes before it
    const before = code.slice(0, idx)
    const doubleQuotes = (before.match(/"/g) ?? []).length
    const singleQuotes = (before.match(/'/g) ?? []).length
    const backticks = (before.match(/`/g) ?? []).length
    // Odd count = inside a string literal → skip
    if (doubleQuotes % 2 !== 0 || singleQuotes % 2 !== 0 || backticks % 2 !== 0) continue

    console.error(`\u274c BANNED: ${rel}:${i + 1} creates raw Database instance`)
    console.error(`   ${line.trim()}`)
    errors++
  }
}

if (errors > 0) {
  console.error(`\n${errors} violation(s) found.`)
  console.error("Fix: use DatabaseFactory.connect(path) or DatabaseFactory.get()")
  console.error("See: playbooks/sqlite-playbook.md -> 'Database — DatabaseFactory only'")
  process.exit(1)
}

console.log(`\u2705 All ${allFiles.length} files clean. No raw Database() instances found.`)
process.exit(0)
