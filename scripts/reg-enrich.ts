#!/usr/bin/env bun
/**
 * Enrich code index with meaningful summaries extracted from source files.
 *
 * Reads code/INDEX.jsonl, extracts JSDoc comments from each source file,
 * and updates the summary + meta.description fields.
 *
 * Usage:
 *   bun scripts/reg-enrich.ts          # dry run: show what would change
 *   bun scripts/reg-enrich.ts --apply  # apply changes to code/INDEX.jsonl
 */

import { readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"

interface IndexEntry {
  file: string
  date: string
  status: string
  summary: string
  meta: Record<string, unknown>
}

interface EnrichedEntry extends IndexEntry {
  meta: Record<string, unknown> & { description?: string }
}

/**
 * Strip structural prefixes from a TypeScript file so the first meaningful
 * declaration is at the top. Returns the residual content.
 *
 * Handles:
 *   - shebang (#! line)
 *   - @jsxImportSource pragma
 *   - import / import type statements (single and multi-line)
 *   - leading whitespace / empty lines
 */
function stripPrefix(content: string): string {
  let lines = content.split("\n")
  let pos = 0
  const drop = new Set<number>()

  // 1. Shebang
  if (lines[pos]?.startsWith("#!")) {
    drop.add(pos)
    lines = lines.slice(pos + 1)
    pos = 0
  }

  // 2. @jsxImportSource pragma block — always starts with `/** @jsxImportSource ... */`
  if (lines[pos]?.startsWith("/**") && lines[pos].includes("@jsxImportSource")) {
    while (pos < lines.length && !lines[pos].trim().includes("*/")) {
      drop.add(pos)
      pos++
    }
    // +1: skip the closing */ line; slice from current array position
    lines = lines.slice(pos + 1)
    pos = 0
  }

  // 3. Strip import/export lines (including multi-line with { })
  let inBlock = false

  for (let i = 0; i < lines.length; i++) {
    const l = lines[i].trim()

    if (inBlock) {
      drop.add(i)
      if (l.includes("}") || l.includes(";")) inBlock = false
      continue
    }

    if (l.startsWith("import ") || l.startsWith("export ")) {
      drop.add(i)
      if (l.includes("{") && !l.includes("}")) inBlock = true
      continue
    }

    // First non-import line — stop
    break
  }

  const residual = lines
    .filter((_, i) => !drop.has(i))
    .join("\n")
    .trimStart()

  return residual
}

/** Extract the first JSDoc comment from pre-processed content. */
function extractDocComment(residual: string): string | null {
  const match = residual.match(/^\/\*\*([\s\S]*?)\*\//)
  if (!match) return null

  const raw = match[1]
  const cleaned = raw
    .split("\n")
    .map((l) => l.replace(/^\s*\*\s?/, ""))
    .join(" ")
    .trim()
    .replace(/\s+/g, " ")

  return cleaned || null
}

/**
 * Extract description from citty defineCommand({ meta: { description } }).
 */
function extractCittyMeta(content: string): string | null {
  const match = content.match(/meta:\s*\{\s*name:[^}]*description:\s*"([^"]+)"/)
  return match ? match[1] : null
}

/** Truncate to maxLen at a word boundary. */
function truncate(doc: string, maxLen: number): string {
  if (doc.length <= maxLen) return doc
  const end = doc.slice(0, maxLen)
  const space = end.lastIndexOf(" ")
  return `${space > maxLen * 0.5 ? end.slice(0, space) : doc.slice(0, maxLen - 1)}…`
}

function main() {
  const apply = Bun.argv.includes("--apply")

  const indexPath = join(process.cwd(), "code/INDEX.jsonl")
  const raw = readFileSync(indexPath, "utf8").trim()
  if (!raw) {
    console.error("code/INDEX.jsonl is empty")
    process.exit(1)
  }

  const entries: EnrichedEntry[] = raw.split("\n").map((l) => JSON.parse(l))
  let changed = 0
  const updated: EnrichedEntry[] = []

  for (const entry of entries) {
    const srcPath = join(process.cwd(), "src", entry.file)
    let doc: string | null = null

    try {
      const content = readFileSync(srcPath, "utf8")
      const residual = stripPrefix(content)
      doc = extractDocComment(residual) ?? extractCittyMeta(content)
    } catch {
      // file not readable — skip
    }

    const summary = doc ? truncate(doc, 120) : entry.summary
    const enriched: EnrichedEntry = {
      ...entry,
      summary,
      meta: {
        ...entry.meta,
        ...(doc ? { description: doc } : {}),
      },
    }

    if (summary !== entry.summary || doc !== entry.meta?.description) {
      changed++
      if (!apply) {
        console.log(`M ${entry.file}`)
        console.log(`  OLD: ${entry.summary}`)
        console.log(`  NEW: ${summary}`)
        console.log("")
      }
    }

    updated.push(enriched)
  }

  if (!apply) {
    console.log(`── DRY RUN: ${changed}/${entries.length} entries would change ──`)
    console.log(`  Run with --apply to write changes.\n`)
  } else {
    const out = `${updated.map((e) => JSON.stringify(e)).join("\n")}\n`
    writeFileSync(indexPath, out)
    console.log(`✓ Enriched ${changed}/${entries.length} entries → code/INDEX.jsonl`)
  }
}

main()
