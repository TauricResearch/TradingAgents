#!/usr/bin/env bun

/**
 * reg-mine.ts — Extract canonical playbook from project-specific playbook.
 *
 * Strips project-specific content and produces a clean, portable version
 * suitable for the registry. By default prints to stdout (dry run).
 * With --apply, writes to playbooks/ and updates last_mined.
 *
 * Usage:
 *   bun scripts/reg-mine.ts lab-first-playbook.md            # dry run → stdout
 *   bun scripts/reg-mine.ts lab-first-playbook.md --apply    # write to playbooks/
 *   bun scripts/reg-mine.ts conventions-playbook.md --apply  # mine another
 *
 * Options:
 *   --source-dir DIR    Source playbooks directory (default: playbooks)
 *   --target-dir DIR    Target directory (default: playbooks)
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
import { sanitize } from "./lib/mine.ts"

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
  console.log("  → syncing playbooks index...")
  const proc = Bun.spawnSync({
    cmd: ["bun", "scripts/reg-sync.ts", "playbooks", "--fix"],
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
  const targetDir = targetDirFlag >= 0 ? args[targetDirFlag + 1] || "playbooks" : "playbooks"

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
    console.error("  --target-dir     Target directory (default: playbooks)")
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
