#!/usr/bin/env bun
/**
 * Human-readable registry lister.
 *
 * Reads a JSONL registry and prints formatted entries.
 * Wraps summaries to terminal width (or 80 columns default).
 *
 * Usage:
 *   bun scripts/reg-list.ts briefs
 *   bun scripts/reg-list.ts debriefs
 *   bun scripts/reg-list.ts decisions
 *   bun scripts/reg-list.ts playbooks
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"

const REGISTRY_DIR = ""
const MAX_SUMMARY_WIDTH = 72

function getTerminalWidth(): number {
  try {
    const cols = Bun.env.COLUMNS
    if (cols) return parseInt(cols, 10)
    // Try tput
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

function formatEntry(entry: Record<string, unknown>, width: number): string {
  const file = String(entry.file ?? "?")
  const date = String(entry.date ?? "?")
  const indent = "      "
  const textWidth = width - indent.length

  const lines: string[] = []

  // Debriefs have 'decision' as main text, optional epic/adr/session
  if (entry.decision != null) {
    lines.push(`${date}  ${file}`)
    lines.push(...wrap(String(entry.decision), textWidth).map((l) => `${indent}${l}`))
    if (entry.epic) lines.push(`${indent}epic: ${entry.epic}`)
    if (entry.adr) lines.push(`${indent}adr:  ${entry.adr}`)
    if (entry.session) lines.push(`${indent}ses:  ${entry.session}`)
  }
  // Playbooks have 'covers' and 'canonical'
  else if (entry.covers != null) {
    const canonical = entry.canonical === true ? "canonical" : "project"
    lines.push(`${canonical.toUpperCase().padEnd(10)}  ${file}`)
    lines.push(...wrap(String(entry.covers), textWidth).map((l) => `${indent}${l}`))
  }
  // Briefs and decisions have 'status' and 'summary'
  else {
    const status = String(entry.status ?? "?")
    const summary = String(entry.summary ?? "")
    lines.push(`${date}  ${status.toUpperCase().padEnd(10)}  ${file}`)
    if (summary) {
      lines.push(...wrap(summary, textWidth).map((l) => `${indent}${l}`))
    }
  }

  lines.push("")
  return lines.join("\n")
}

function main() {
  const registry = Bun.argv[2]
  if (!registry) {
    console.error("Usage: bun scripts/reg-list.ts <briefs|debriefs|decisions|playbooks>")
    process.exit(1)
  }

  const fileMap: Record<string, string> = {
    briefs: "briefs/INDEX.jsonl",
    debriefs: "debriefs/INDEX.jsonl",
    decisions: "decisions/INDEX.jsonl",
    playbooks: "playbooks/REGISTRY.jsonl",
  }

  const path = fileMap[registry]
  if (!path) {
    console.error(`Unknown registry: ${registry}`)
    console.error(`Known: ${Object.keys(fileMap).join(", ")}`)
    process.exit(1)
  }

  const width = Math.min(getTerminalWidth(), MAX_SUMMARY_WIDTH + 10)
  const fullPath = join(process.cwd(), path)

  try {
    const content = readFileSync(fullPath, "utf-8").trim()
    if (!content) {
      console.log(`(empty: ${path})`)
      return
    }

    const lines = content.split("\n")
    console.log(`── ${registry.toUpperCase()} (${lines.length} entries) ──\n`)

    for (const line of lines) {
      if (!line.trim()) continue
      const entry = JSON.parse(line)
      console.log(formatEntry(entry, width))
    }
  } catch (e) {
    console.error(`Error reading ${path}: ${e instanceof Error ? e.message : String(e)}`)
    process.exit(1)
  }
}

main()
