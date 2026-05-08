#!/usr/bin/env bun
/**
 * Convert CTX conceptual lexicon (JSON array) to merged schema (JSONL).
 *
 * CTX format:
 *   { id, title, description, type, category, tags[], source }
 *
 * Merged format:
 *   { file, id, date, status, type, summary, meta: { category, origin, heuristic?, usage?, tags, related, coined_by } }
 *
 * Usage:
 *   bun scripts/ctx-lexicon-convert.ts --dry-run
 *   bun scripts/ctx-lexicon-convert.ts --apply
 */

import { readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"

interface CtxEntry {
  id: string
  title: string
  description: string
  type: string
  category: string
  tags: string[]
  source: string
}

function convertEntry(entry: CtxEntry): Record<string, unknown> {
  // Infer status from tags
  let status = "active"
  const statusTag = entry.tags.find((t) => t.includes("Status:"))
  if (statusTag) {
    if (statusTag.includes("proposed")) status = "draft"
    if (statusTag.includes("deprecated")) status = "superseded"
  }

  // Normalize tags: keep bracket notation, add origin
  const tags = [...entry.tags]
  if (entry.source && entry.source !== "cl") {
    tags.push(`[Origin: ${entry.source}]`)
  }

  return {
    file: entry.title
      .toLowerCase()
      .replace(/\s+/g, "-")
      .replace(/[^a-z0-9-]/g, ""),
    id: entry.id,
    date: "2026-05-08",
    status,
    type: entry.type.toLowerCase().replace(/\s+/g, "-"),
    summary: entry.description,
    meta: {
      category: entry.category,
      origin: entry.source === "cl" ? "CTX conceptual lexicon" : entry.source,
      heuristic: "",
      usage: "",
      tags,
      related: [],
      coined_by: "agent",
    },
  }
}

function main() {
  const dryRun = Bun.argv.includes("--dry-run")
  const apply = Bun.argv.includes("--apply")

  if (!dryRun && !apply) {
    console.error("Usage: bun scripts/ctx-lexicon-convert.ts --dry-run | --apply")
    process.exit(1)
  }

  const inputPath = join(process.cwd(), "docs/conceptual-lexicon-example.json")
  const outputPath = join(process.cwd(), "debriefs/lexicon-ctx.jsonl")

  const raw: CtxEntry[] = JSON.parse(readFileSync(inputPath, "utf-8"))
  const converted = raw.map(convertEntry)

  console.log(`── CTX LEXICON CONVERSION ──`)
  console.log(`  input: ${raw.length} entries`)

  // Stats
  const typeCounts = new Map<string, number>()
  const statusCounts = new Map<string, number>()
  for (const e of converted) {
    typeCounts.set(e.type as string, (typeCounts.get(e.type as string) ?? 0) + 1)
    statusCounts.set(e.status as string, (statusCounts.get(e.status as string) ?? 0) + 1)
  }

  console.log(`\n  Type distribution:`)
  for (const [t, n] of typeCounts) {
    console.log(`    ${t}: ${n}`)
  }

  console.log(`\n  Status distribution:`)
  for (const [s, n] of statusCounts) {
    console.log(`    ${s}: ${n}`)
  }

  console.log(`\n  Sample (first):`)
  console.log(JSON.stringify(converted[0], null, 2))
  console.log(`\n  Sample (last):`)
  console.log(JSON.stringify(converted[converted.length - 1], null, 2))

  if (apply) {
    const lines = converted.map((e) => JSON.stringify(e)).join("\n")
    writeFileSync(outputPath, `${lines}\n`)
    console.log(`\n  → written: ${outputPath}`)
  } else {
    console.log(`\n  Run with --apply to write ${outputPath}`)
  }
}

main()
