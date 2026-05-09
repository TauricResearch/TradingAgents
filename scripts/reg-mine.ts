#!/usr/bin/env bun
/**
 * reg-mine.ts — Extract canonical playbook from project-specific playbook.
 *
 * Strips project-specific content and produces a clean, portable version
 * suitable for canonicals/. By default prints to stdout (dry run).
 * With --apply, writes to canonicals/playbooks/ and updates last_mined.
 *
 * Usage:
 *   bun scripts/reg-mine.ts lab-first-playbook.md            # dry run → stdout
 *   bun scripts/reg-mine.ts lab-first-playbook.md --apply    # write to canonicals/
 *   bun scripts/reg-mine.ts conventions-playbook.md --apply  # mine another
 *
 * Options:
 *   --source-dir DIR    Source playbooks directory (default: playbooks)
 *   --target-dir DIR    Target canonicals directory (default: canonicals/playbooks)
 *   --apply             Write output to target directory
 *
 * What gets stripped:
 *   - Project name references (TradingAgents)
 *   - Project-specific paths (src/server/, tradingagents/)
 *   - Ticker symbols (AAPL → <TICKER>)
 *   - Session IDs (ses_xxx → <SESSION-ID>)
 *   - Project env vars (TA_DASHBOARD_PORT → <SERVICE>_PORT)
 *   - Project-specific file names, ports, dates
 *
 * Design: Mining is stripping, not rewriting. The output preserves the
 * pattern/heuristic while removing the bindings to a specific project.
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs"
import { basename, join } from "node:path"

// ── Project-specific token replacements (ordered: most specific first) ──
const REPLACEMENTS: Array<{ pattern: RegExp; replacement: string }> = [
  // Session IDs
  { pattern: /\bses_[0-9a-f]{6,}\b/g, replacement: "<SESSION-ID>" },
  // Project CLI commands: tradingagents <cmd> → <CLI> <cmd>
  {
    pattern:
      /\btradingagents (analyze|plan|portfolio|watchlist|signals|config|sync|backup|summarize|ig)\b/g,
    replacement: "<CLI> $1",
  },
  // Project package directory
  { pattern: /\btradingagents\//g, replacement: "<PACKAGE>/" },
  // Project name
  { pattern: /\bTradingAgents\b/g, replacement: "<PROJECT>" },
  // Source directory hierarchy
  { pattern: /\bsrc\/server\//g, replacement: "<SRC-SERVER>/" },
  { pattern: /\bsrc\/cli\//g, replacement: "<SRC-CLI>/" },
  { pattern: /\bsrc\/lib\//g, replacement: "<SRC-LIB>/" },
  { pattern: /\bsrc\//g, replacement: "<SRC>/" },
  // Project-specific scripts (named ones only)
  { pattern: /\bscripts\/server-lifecycle\.ts\b/g, replacement: "scripts/<SERVICE>.ts" },
  { pattern: /\bscripts\/seed_database\.ts\b/g, replacement: "scripts/<SEED>.ts" },
  { pattern: /\bscripts\/get_price\.ts\b/g, replacement: "scripts/<PRICE>.ts" },
  { pattern: /\bscripts\/trade-calculator\.ts\b/g, replacement: "scripts/<CALC>.ts" },
  { pattern: /\bscripts\/barnacle-scan\.ts\b/g, replacement: "scripts/<SCAN>.ts" },
  // Project-specific env vars
  { pattern: /\bTA_DASHBOARD_PORT\b/g, replacement: "<SERVICE>_PORT" },
  { pattern: /\bTA_([A-Z_]+)\b/g, replacement: "<PREFIX>_$1" },
  // Project data dirs
  { pattern: /\b~\/\.tradingagents\//g, replacement: "~/.<PROJECT>/" },
  // Specific port references (port 3000 is the dashboard port)
  { pattern: /\bport 3000\b/g, replacement: "port <PORT>" },
  // Ticker symbols
  {
    pattern: /\b(AAPL|MSFT|GOOGL|AMZN|TSLA|META|NVDA|BRK\.B|IBM|INTC)\b/g,
    replacement: "<TICKER>",
  },
  // Ticker with exchange suffix
  { pattern: /\b[A-Z]{2,6}\.[A-Z]{1,4}\b/g, replacement: "<TICKER.EXCHANGE>" },
  // Specific dates (YYYY-MM-DD format, 2026 only)
  { pattern: /\b2026-[0-9]{2}-[0-9]{2}\b/g, replacement: "<DATE>" },
  // Ephemeral commit/PR references specific to this project
  { pattern: /\b(td|TD)-[0-9a-f]{6}\b/g, replacement: "<TASK-ID>" },
]

function sanitize(content: string): string {
  let cleaned = content
  for (const { pattern, replacement } of REPLACEMENTS) {
    cleaned = cleaned.replace(pattern, replacement)
  }
  return cleaned
}

function updateRegistryLastMined(playbookFile: string): void {
  const regPath = join(process.cwd(), "playbooks/REGISTRY.jsonl")
  if (!existsSync(regPath)) {
    console.warn("  ⚠ playbooks/REGISTRY.jsonl not found, skipping last_mined update")
    return
  }

  const today = new Date().toISOString().split("T")[0]
  const lines = readFileSync(regPath, "utf-8").trim().split("\n")
  let found = false

  const updated = lines.map((line) => {
    try {
      const obj = JSON.parse(line)
      if (obj.file === playbookFile) {
        found = true
        obj.meta = obj.meta || {}
        obj.meta.last_mined = today
        return JSON.stringify(obj)
      }
      return line
    } catch {
      return line
    }
  })

  if (!found) {
    console.warn(`  ⚠ ${playbookFile} not found in playbooks/REGISTRY.jsonl`)
    return
  }

  writeFileSync(regPath, `${updated.join("\n")}\n`)
  console.log(`  → updated last_mined: ${today}`)
}

function runRegSyncCanonicals(): void {
  console.log("  → syncing canonicals index...")
  const proc = Bun.spawnSync({
    cmd: ["bun", "scripts/reg-sync.ts", "canonicals", "--fix"],
    stdout: "pipe",
    stderr: "pipe",
  })
  const out = new TextDecoder().decode(proc.stdout).trim()
  const err = new TextDecoder().decode(proc.stderr).trim()
  if (out)
    console.log(
      out
        .split("\n")
        .map((l) => `    ${l}`)
        .join("\n"),
    )
  if (err)
    console.error(
      err
        .split("\n")
        .map((l) => `    ${l}`)
        .join("\n"),
    )
}

function main(): void {
  const args = Bun.argv.slice(2)
  const apply = args.includes("--apply")
  const sourceDirFlag = args.indexOf("--source-dir")
  const targetDirFlag = args.indexOf("--target-dir")

  const sourceDir = sourceDirFlag >= 0 ? args[sourceDirFlag + 1] || "playbooks" : "playbooks"
  const targetDir =
    targetDirFlag >= 0 ? args[targetDirFlag + 1] || "canonicals/playbooks" : "canonicals/playbooks"

  const fileArg = args.find((a) => !a.startsWith("--"))
  if (!fileArg) {
    console.error(
      "Usage: bun scripts/reg-mine.ts <playbook-file> [--apply] [--source-dir DIR] [--target-dir DIR]",
    )
    console.error("")
    console.error(
      "  playbook-file    Name of playbook in --source-dir (e.g. lab-first-playbook.md)",
    )
    console.error("  --apply          Write cleaned output to --target-dir (default: stdout)")
    console.error("  --source-dir     Source directory (default: playbooks)")
    console.error("  --target-dir     Target directory (default: canonicals/playbooks)")
    process.exit(1)
  }

  const sourcePath = join(process.cwd(), sourceDir, fileArg)
  if (!existsSync(sourcePath)) {
    console.error(`  ✗ source not found: ${sourcePath}`)
    process.exit(1)
  }

  const raw = readFileSync(sourcePath, "utf-8")
  const cleaned = sanitize(raw)

  if (!apply) {
    // Dry run — print to stdout
    console.log(cleaned)
    return
  }

  // Apply — write to target
  const targetPath = join(process.cwd(), targetDir, basename(fileArg))
  if (existsSync(targetPath)) {
    console.error(`  ✗ target already exists: ${targetPath}`)
    console.error("    Remove it first, or use dry-run to review.")
    process.exit(1)
  }

  writeFileSync(targetPath, cleaned)
  console.log(`  ✓ wrote: ${targetPath}`)

  // Update indexes
  updateRegistryLastMined(fileArg)
  runRegSyncCanonicals()
}

main()
