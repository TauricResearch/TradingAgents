#!/usr/bin/env bun
/**
 * Human-readable registry lister.
 *
 * Reads a JSONL index and prints formatted entries.
 * Expects unified schema: { file, date, status, summary, meta? }
 *
 * Usage:
 *   bun scripts/reg-list.ts briefs
 *   bun scripts/reg-list.ts debriefs
 *   bun scripts/reg-list.ts decisions
 *   bun scripts/reg-list.ts playbooks
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"

const MAX_SUMMARY_WIDTH = 72

interface UnifiedEntry {
  file: string
  date: string
  status: string
  summary: string
  meta?: Record<string, unknown>
}

function getTerminalWidth(): number {
  try {
    const cols = Bun.env.COLUMNS
    if (cols) return parseInt(cols, 10)
    const output = new TextDecoder().decode(Bun.spawnSync({ cmd: ["tput", "cols"] }).stdout).trim()
    const w = parseInt(output, 10)
    return w > 40 ? w : 80
  } catch {
    return 80
  }
}

function wrap(text: string, width: number): string[] {
  const words = text.split(/\s+/)
  const lines: string[] = []
  let current = ""
  for (const word of words) {
    if (current.length + word.length + 1 > width) {
      lines.push(current)
      current = word
    } else {
      current = current ? `${current} ${word}` : word
    }
  }
  if (current) lines.push(current)
  return lines.length ? lines : [""]
}

function formatMeta(meta: Record<string, unknown> | undefined): string[] {
  if (!meta) return []
  const lines: string[] = []
  for (const [key, value] of Object.entries(meta)) {
    if (value == null) continue
    lines.push(`${key}: ${value}`)
  }
  return lines
}

function formatTags(tags: unknown): string {
  if (!Array.isArray(tags)) return ""
  const filtered = tags.filter((t) => typeof t === "string" && !t.startsWith("[#"))
  return filtered.join(" ")
}

function formatEntry(entry: UnifiedEntry, width: number, isLexicon = false): string {
  const indent = "      "
  const textWidth = width - indent.length

  if (isLexicon) {
    // Lexicon v2: show id, type, status, date, summary, tags
    const id = (entry as Record<string, unknown>).id ?? entry.file
    const type = (entry as Record<string, unknown>).type ?? "term"
    const header = `${String(id).padEnd(12)}  ${String(type).padEnd(24)}  ${entry.status.toUpperCase().padEnd(8)}  ${entry.date}`
    const summaryLines = wrap(entry.summary, textWidth)
    const tagStr = formatTags(entry.meta?.tags)
    const metaLines = [
      ...(entry.meta?.heuristic ? [`heuristic: ${entry.meta.heuristic}`] : []),
      ...(tagStr ? [`tags: ${tagStr}`] : []),
    ]

    return [
      header,
      ...summaryLines.map((l) => `${indent}${l}`),
      ...metaLines.map((l) => `${indent}${l}`),
      "",
    ].join("\n")
  }

  // Standard registry entry
  const header = `${entry.date}  ${entry.status.toUpperCase().padEnd(10)}  ${entry.file}`
  const summaryLines = wrap(entry.summary, textWidth)
  const metaLines = formatMeta(entry.meta)

  return [
    header,
    ...summaryLines.map((l) => `${indent}${l}`),
    ...metaLines.map((l) => `${indent}${l}`),
    "",
  ].join("\n")
}

function loadJsonl(path: string): UnifiedEntry[] {
  const content = readFileSync(path, "utf-8").trim()
  if (!content) return []
  return content.split("\n").map((line) => JSON.parse(line))
}

const FILE_MAP: Record<string, string> = {
  briefs: "briefs/INDEX.jsonl",
  debriefs: "debriefs/INDEX.jsonl",
  decisions: "decisions/INDEX.jsonl",
  playbooks: "playbooks/REGISTRY.jsonl",
  docs: "docs/INDEX.jsonl",
  lexicon: "silo-conceptual-lexicon.jsonl",
  "lexicon-ctx": "debriefs/lexicon-ctx.jsonl",
}

function main() {
  const registry = Bun.argv[2]
  if (!registry) {
    console.error(
      "Usage: bun scripts/reg-list.ts <briefs|debriefs|decisions|playbooks|docs|lexicon>",
    )
    process.exit(1)
  }

  const path = FILE_MAP[registry]
  if (!path) {
    console.error(`Unknown registry: ${registry}`)
    console.error(`Known: ${Object.keys(FILE_MAP).join(", ")}`)
    process.exit(1)
  }

  const width = Math.min(getTerminalWidth(), MAX_SUMMARY_WIDTH + 10)
  const fullPath = join(process.cwd(), path)
  const entries = loadJsonl(fullPath)

  console.log(`── ${registry.toUpperCase()} (${entries.length} entries) ──\n`)
  for (const entry of entries) {
    console.log(formatEntry(entry, width, registry === "lexicon"))
  }
}

main()
