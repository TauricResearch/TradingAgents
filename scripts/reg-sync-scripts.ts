#!/usr/bin/env bun
/**
 * reg-sync-scripts.ts — Sync script index with portability classification.
 *
 * Detects scripts on disk and checks against scripts/INDEX.jsonl.
 * Reports MISSING / STALE. With --fix regenerates index.
 *
 * Portability levels:
 *   portable   — No project deps (reg-check.ts, lib/gum.ts)
 *   adaptable  — Minor project deps, easy to generalise (barnacle-scan.ts)
 *   project    — TradingAgents-specific (seed_database.ts, get_price.ts)
 *
 * Usage:
 *   bun scripts/reg-sync-scripts.ts           # check
 *   bun scripts/reg-sync-scripts.ts --fix     # regenerate
 */

import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"

interface ScriptEntry {
  file: string
  status: string
  summary: string
  meta: {
    portability: string
    lang: string
    path?: string
  }
}

const INDEX_PATH = "scripts/INDEX.jsonl"
const SCRIPTS_DIR = "scripts"

const EXT_TO_LANG: Record<string, string> = {
  ".ts": "ts",
  ".sh": "sh",
  ".py": "py",
}

function portableHeuristic(filename: string): string {
  // Known portable patterns
  const portable = [
    "reg-check.ts",
    "reg-list.ts",
    "reg-sync.ts",
    "reg-migrate.ts",
    "reg-state.ts",
    "reg-mine.ts",
    "reg-import.ts",
    "reg-promote.ts",
    "reg-sync-scripts.ts",
  ]
  const adaptable = [
    "barnacle-scan.ts",
    "check-database-usage.ts",
    "check-view-scripts.ts",
    "db-backup.ts",
    "just-group-menu.ts",
    "refactor-playbook.ts",
    "extract_mermaid.ts",
    "render_diagrams.ts",
    "install-pre-push-hook.sh",
  ]
  const project = [
    "seed_database.ts",
    "seed-initial-portfolio.ts",
    "seed_real_portfolio.ts",
    "get_price.ts",
    "sync-prices.ts",
    "trade-calculator.ts",
    "portfolio-intel.ts",
    "summarize_analyses.ts",
    "server-lifecycle.ts",
    "lexicon-migrate.ts",
    "ctx-lexicon-convert.ts",
    "gitnexus-batch.ts",
    "gitnexus-to-dot.ts",
    "pr-fetch-all.sh",
    "pr-summarize.ts",
    "push-with-diagrams.ts",
    "init-test-db.sh",
    "copy-test-to-dev.sh",
    "reset-portfolio.sh",
    "seed_test_journal.sh",
    "gen-info-md.py",
  ]
  // lab/ scripts are ephemeral experiments — project-scoped
  if (filename.startsWith("lab/")) return "project"
  // py/ scripts are project-specific bridges
  if (filename.startsWith("py/")) return "project"
  // color-tools/ is project-specific tooling
  if (filename.startsWith("color-tools/")) return "adaptable"

  if (portable.includes(filename)) return "portable"
  if (adaptable.includes(filename)) return "adaptable"
  if (project.includes(filename)) return "project"
  // Files in lib/ are portable helpers (no project deps)
  if (filename.startsWith("lib/")) return "portable"

  return "unknown"
}

function extractSummaryFromFile(filepath: string): string {
  try {
    const content = readFileSync(filepath, "utf-8")
    // Match JSDoc comment: extract first line after /**
    const lines = content.split("\n")
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].trim().startsWith("/**")) {
        const next = lines[i + 1]?.trim()
        if (next?.startsWith("* ")) {
          return next
            .replace(/^\*\s*/, "")
            .replace(/\\"/g, '"')
            .trim()
        }
      }
    }
    // Python docstring: extract first line of triple-quoted string
    const pyMatch = content.match(/"""([\s\S]*?)"""/)
    if (pyMatch) {
      const firstLine = pyMatch[1].split("\n")[0].replace(/\\"/g, '"').trim()
      if (firstLine) return firstLine
    }

    // Shell script: look for first substantial comment line (skip decoration)
    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith("# ") && trimmed.length > 10) {
        const content = trimmed.slice(2) // strip '# ' prefix
        // Skip lines that are mostly border/separator characters
        const borderChars = (content.match(/[-─═─┌┐└┘├┤┬┴┼┃━] */g) || [])
          .join("")
          .replace(/ /g, "").length
        const alphaNum = content.replace(/[-─═─┌┐└┘├┤┬┴┼┃━s]/g, "").length
        if (borderChars > alphaNum * 2) continue // skip decoration
        const summary = content.trim()
        // Skip bare filenames (e.g. '# copy-test-to-dev.sh')
        if (/^[a-z][a-z0-9_-]+(.[a-z]+)?$/i.test(summary)) continue
        return summary.replace(/\\"/g, '"')
      }
    }
  } catch {
    // ignore
  }
  return "(auto-generated — add description)"
}

function listScriptFiles(): string[] {
  const results: string[] = []

  function walk(dir: string, prefix: string) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const fullPath = join(dir, entry.name)
      const relPath = prefix ? `${prefix}/${entry.name}` : entry.name
      if (entry.isDirectory()) {
        walk(fullPath, relPath)
      } else if (entry.isFile()) {
        const ext = entry.name.slice(entry.name.lastIndexOf("."))
        if (EXT_TO_LANG[ext]) {
          results.push(relPath)
        }
      }
    }
  }

  walk(SCRIPTS_DIR, "")
  return results.sort()
}

function loadIndex(): ScriptEntry[] {
  if (!existsSync(INDEX_PATH)) return []
  const content = readFileSync(INDEX_PATH, "utf-8").trim()
  if (!content) return []
  return content.split("\n").map((line) => JSON.parse(line))
}

function check(fix: boolean): boolean {
  const entries = loadIndex()
  const indexedFiles = new Set(entries.map((e) => e.file))
  const diskFiles = listScriptFiles()
  const diskSet = new Set(diskFiles)

  const missing = diskFiles.filter((f) => !indexedFiles.has(f))
  const stale = [...indexedFiles].filter((f) => !diskSet.has(f))

  console.log(`\n── SCRIPTS ──`)
  console.log(`  index: ${INDEX_PATH} (${indexedFiles.size} entries)`)
  console.log(`  files: ${SCRIPTS_DIR} (${diskFiles.length} files)`)

  // Always re-extract when --fix is set (picks up doc improvements)
  if (fix) {
    const allFiles = diskFiles.map((f) => {
      const fullPath = join(SCRIPTS_DIR, f)
      const ext = f.slice(f.lastIndexOf("."))
      const portability = portableHeuristic(f)
      return {
        file: f,
        status: portability,
        summary: extractSummaryFromFile(fullPath),
        meta: { portability, lang: EXT_TO_LANG[ext] || "unknown", path: f },
      }
    })
    const newLines = allFiles.map((e) => JSON.stringify(e)).join("\n")
    writeFileSync(INDEX_PATH, `${newLines}\n`)
  }

  if (missing.length === 0 && stale.length === 0) {
    console.log(fix ? `  ✓ re-enriched: ${diskFiles.length} entries` : `  ✓ up to date`)
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

  return false
}

function main() {
  const args = Bun.argv.slice(2)
  const fix = args.includes("--fix")

  if (!check(fix) && !fix) {
    console.log("\nRun with --fix to regenerate index.")
    process.exit(1)
  }
}

main()
