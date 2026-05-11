#!/usr/bin/env bun
/**
 * Convert CTX conceptual-lexicon-example.json to JSONL.
 *
 * Input:  docs/conceptual-lexicon-example.json (JSON array, 161 entries)
 * Output: debriefs/lexicon-ctx.jsonl (JSONL, one entry per line)
 *
 * Transformation:
 *   title  → file  (slugified)
 *   description → summary
 *   source → meta.origin (cleaned)
 *   + date (from today), status (active/draft), id (preserved), type (preserved)
 *   + meta.heuristic (empty), meta.usage (empty), meta.coined_by (inferred from source)
 *   + tags (preserved)
 *
 * Usage:
 *   bun scripts/ctx-lexicon-convert.ts
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"

const INPUT_JSON = join(process.cwd(), "docs/conceptual-lexicon-example.json")
const OUTPUT_JSONL = join(process.cwd(), "debriefs/lexicon-ctx.jsonl")
const MIGRATION_DATE = "2026-05-08"

interface CtxEntry {
  id: string
  title: string
  description: string
  type: string
  category: string
  tags: string[]
  source: string
}

function slugify(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
}

function inferCoinedBy(source: string): string {
  // "cl" = collaborative (human-agent dialogue), "agent" = agent-authored, "manual" = human
  if (source === "cl") return "human" // collaborative
  if (source === "agent") return "agent"
  if (source === "manual") return "human"
  return "human" // default
}

function inferOrigin(source: string): string {
  const map: Record<string, string> = {
    cl: "AGENTS.md (Edinburgh Protocol, collaborative)",
    agent: "LLM agent session",
    manual: "Manual documentation",
  }
  return map[source] ?? `Source: ${source}`
}

function inferStatus(entry: CtxEntry): string {
  // Entries with "draft" in title or type, or known draft IDs
  if (entry.type.toLowerCase().includes("draft")) return "draft"
  return "active"
}

// Normalize type (fix case inconsistencies)
function normalizeType(t: string): string {
  const map: Record<string, string> = {
    "Operational Heuristic": "operational-heuristic",
    "operational-heuristic": "operational-heuristic",
    "operational heuristic": "operational-heuristic",
    term: "term",
    pattern: "pattern",
  }
  return map[t] ?? t
}

function convert(entry: CtxEntry) {
  const status = inferStatus(entry)
  return {
    file: slugify(entry.title),
    id: entry.id,
    date: MIGRATION_DATE,
    status,
    type: normalizeType(entry.type),
    summary: entry.description,
    meta: {
      category: entry.category,
      origin: inferOrigin(entry.source),
      heuristic: "",
      usage: "",
      tags: entry.tags,
      coined_by: inferCoinedBy(entry.source),
    },
  }
}

function main() {
  const raw = readFileSync(INPUT_JSON, "utf-8")
  const data = JSON.parse(raw) as CtxEntry[]

  const lines = data.map((entry) => JSON.stringify(convert(entry)))
  const output = `${lines.join("\n")}\n`

  mkdirSync(dirname(OUTPUT_JSONL), { recursive: true })
  writeFileSync(OUTPUT_JSONL, output, "utf-8")

  console.log(`✓ Converted ${data.length} entries`)
  console.log(`  → ${OUTPUT_JSONL}`)

  // Stats
  const byType: Record<string, number> = {}
  const byStatus: Record<string, number> = {}
  const byCategory: Record<string, number> = {}

  for (const e of data) {
    const t = normalizeType(e.type)
    byType[t] = (byType[t] ?? 0) + 1
    const s = inferStatus(e)
    byStatus[s] = (byStatus[s] ?? 0) + 1
    byCategory[e.category] = (byCategory[e.category] ?? 0) + 1
  }

  console.log("\n── Type distribution ──")
  for (const [k, v] of Object.entries(byType).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${v.toString().padStart(4)}  ${k}`)
  }
  console.log("\n── Status distribution ──")
  for (const [k, v] of Object.entries(byStatus).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${v.toString().padStart(4)}  ${k}`)
  }
  console.log("\n── Category distribution ──")
  for (const [k, v] of Object.entries(byCategory).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${v.toString().padStart(4)}  ${k}`)
  }
}

main()
