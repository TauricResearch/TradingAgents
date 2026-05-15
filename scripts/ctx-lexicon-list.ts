#!/usr/bin/env bun
/**
 * List CTX conceptual lexicon entries in a readable table.
 *
 * Usage:
 *   bun scripts/ctx-lexicon-list.ts [--json] [--type TYPE] [--status STATUS]
 *   bun scripts/ctx-lexicon-list.ts                    # human-readable table
 *   bun scripts/ctx-lexicon-list.ts --json            # raw JSONL entries
 *   bun scripts/ctx-lexicon-list.ts --type term       # filter by type
 *   bun scripts/ctx-lexicon-list.ts --status draft   # filter by status
 *   bun scripts/ctx-lexicon-list.ts --search humility # full-text search in summary/heuristic
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"

const LEXICON_JSONL = join(process.cwd(), "debriefs/lexicon-ctx.jsonl")
const HEURISTIC_WIDTH = 50

interface LexiconEntry {
  file: string
  id: string
  date: string
  status: string
  type: string
  summary: string
  title?: string
  meta: {
    category?: string
    heuristic?: string
    usage?: string
    tags?: string[]
    coined_by?: string
  }
}

function loadEntries(): LexiconEntry[] {
  try {
    const content = readFileSync(LEXICON_JSONL, "utf-8")
    return content
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as LexiconEntry)
  } catch {
    console.error(`Lexicon not found at ${LEXICON_JSONL}`)
    console.error("Run: bun scripts/ctx-lexicon-convert.ts first")
    process.exit(1)
  }
}

function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s
}

function printTable(entries: LexiconEntry[]): void {
  const cols = [14, 36, 22, HEURISTIC_WIDTH] as const
  const sep = cols.map((w) => "─".repeat(w)).join("─┼─")
  const header = [
    truncate("ID", cols[0]),
    truncate("TITLE", cols[1]),
    truncate("TYPE", cols[2]),
    truncate("HEURISTIC", cols[3]),
  ].join(" │ ")

  console.log(header)
  console.log(sep)

  for (const e of entries) {
    const typeColor =
      e.type === "term" ? "\x1b[36m" : e.type === "operational-heuristic" ? "\x1b[33m" : "\x1b[35m"
    const reset = "\x1b[0m"
    const id = truncate(e.id, cols[0])
    const title = truncate(e.title ?? e.file, cols[1])
    const type = truncate(e.type, cols[2])
    const heuristic = truncate(e.meta?.heuristic ?? "—", cols[3])

    console.log(
      `${typeColor}${id.padEnd(cols[0])}${reset} │ ${title.padEnd(cols[1])} │ ${type.padEnd(cols[2])} │ ${heuristic}`,
    )
  }

  console.log(`\n${entries.length} entries`)
}

function printJson(entries: LexiconEntry[]): void {
  for (const e of entries) {
    console.log(JSON.stringify(e))
  }
}

function printStats(entries: LexiconEntry[]): void {
  const byType: Record<string, number> = {}
  const byStatus: Record<string, number> = {}
  const byCategory: Record<string, number> = {}

  for (const e of entries) {
    byType[e.type] = (byType[e.type] ?? 0) + 1
    byStatus[e.status] = (byStatus[e.status] ?? 0) + 1
    const cat = e.meta?.category ?? "unknown"
    byCategory[cat] = (byCategory[cat] ?? 0) + 1
  }

  console.log("\n── Distribution ──")
  console.log("By type:")
  for (const [k, v] of Object.entries(byType).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${v.toString().padStart(4)}  ${k}`)
  }
  console.log("By status:")
  for (const [k, v] of Object.entries(byStatus).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${v.toString().padStart(4)}  ${k}`)
  }
  console.log("By category:")
  for (const [k, v] of Object.entries(byCategory).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${v.toString().padStart(4)}  ${k}`)
  }
}

// CLI — robust flag extraction: handle both "--flag value" and "--flag=value" formats
const args = process.argv.slice(2)

function getFlagValue(flag: string): string | null {
  const raw = args.find((a) => a.startsWith(`--${flag}=`))?.slice(`--${flag}=`.length) ?? null
  if (!raw) return null
  // just prepends the param name: "--flag=param=value" → strip first "word=" prefix
  // e.g. "--type=type=term" → "type=term" → "term"
  // e.g. "--search=query=humility" → "query=humility" → "humility"
  const eq = raw.indexOf("=")
  return eq > 0 ? raw.slice(eq + 1) : raw
}

const search = getFlagValue("--search")?.toLowerCase() ?? null
const typeFilter = getFlagValue("--type")
const statusFilter = getFlagValue("--status")

let entries = loadEntries()
if (typeFilter) entries = entries.filter((e) => e.type === typeFilter)
if (statusFilter) entries = entries.filter((e) => e.status === statusFilter)
if (search) {
  entries = entries.filter(
    (e) =>
      (e.summary ?? "").toLowerCase().includes(search) ||
      (e.meta?.heuristic ?? "").toLowerCase().includes(search) ||
      (e.title ?? e.file).toLowerCase().includes(search),
  )
}

if (args.includes("--json")) {
  printJson(entries)
} else if (args.includes("--stats")) {
  printStats(entries)
} else {
  printTable(entries)
  if (!search && !typeFilter && !statusFilter) printStats(entries)
}
