#!/usr/bin/env bun
/**
 * reg-import.ts — Import a canonical playbook into the current project.
 *
 * By default prints what would be imported (dry run).
 * With --apply, copies the file and updates the registry.
 *
 * Usage:
 *   bun scripts/reg-import.ts gum-playbook.md              # dry run
 *   bun scripts/reg-import.ts gum-playbook.md --apply      # import
 *   bun scripts/reg-import.ts briefs-playbook.md --apply   # import another
 *
 * Options:
 *   --source-dir DIR    Source canonicals directory (default: canonicals/playbooks)
 *   --target-dir DIR    Target project directory (default: playbooks)
 *   --apply             Copy and register the playbook
 */

import { copyFileSync, existsSync, readFileSync, writeFileSync } from "node:fs"
import { basename, join } from "node:path"

function addToPlaybookRegistry(filename: string, summary: string, source: string): void {
  const regPath = join(process.cwd(), "playbooks/REGISTRY.jsonl")

  const lines: string[] = []
  if (existsSync(regPath)) {
    const content = readFileSync(regPath, "utf-8").trim()
    if (content) lines.push(...content.split("\n"))
  }

  // Check for existing file
  const exists = lines.some((line) => {
    try {
      return JSON.parse(line).file === filename
    } catch {
      return false
    }
  })

  if (exists) {
    console.warn(`  ⚠ ${filename} already in playbooks/REGISTRY.jsonl`)
    return
  }

  const date = new Date().toISOString().split("T")[0]
  const entry = {
    file: filename,
    date,
    status: "canonical",
    summary,
    meta: { source, mining_candidate: false, mining_note: null, last_mined: null },
  }

  lines.push(JSON.stringify(entry))
  writeFileSync(regPath, `${lines.join("\n")}\n`)
  console.log(`  → registered in playbooks/REGISTRY.jsonl`)
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
      "Usage: bun scripts/reg-import.ts <playbook-file> [--apply] [--source-dir DIR] [--target-dir DIR]",
    )
    console.error("")
    console.error("  playbook-file    Name of playbook in --source-dir (e.g. gum-playbook.md)")
    console.error("  --apply          Copy to --target-dir and register")
    console.error("  --source-dir     Source directory (default: playbooks)")
    console.error("  --target-dir     Target directory (default: playbooks)")
    process.exit(1)
  }

  const sourcePath = join(process.cwd(), sourceDir, fileArg)
  if (!existsSync(sourcePath)) {
    console.error(`  ✗ canonical playbook not found: ${sourcePath}`)
    process.exit(1)
  }

  const targetPath = join(process.cwd(), targetDir, basename(fileArg))
  if (existsSync(targetPath)) {
    console.error(`  ✗ already exists in project: ${targetPath}`)
    console.error("    Remove it first to re-import.")
    process.exit(1)
  }

  const content = readFileSync(sourcePath, "utf-8")
  // Extract summary from H1 heading if available
  const titleMatch = content.match(/^#\s+(.+)/m)
  const title = titleMatch?.[1]?.trim() || basename(fileArg, ".md")
  const summary = title.length > 80 ? `${title.slice(0, 77)}...` : title

  if (!apply) {
    // Dry run — show info
    console.log(`── Dry run ──`)
    console.log(`  source:   ${sourcePath}`)
    console.log(`  target:   ${targetPath}`)
    console.log(`  title:    ${title}`)
    const hasPlaceholders = content.includes("<")
    if (hasPlaceholders) {
      const placeholders = [...content.matchAll(/<([A-Z-]+)>/g)]
        .map((m) => m[1])
        .filter((p) => /^[A-Z-]+$/.test(p))
      const unique = [...new Set(placeholders)]
      console.log(`  placeholders found: ${unique.join(", ")}`)
    }
    console.log(`\n  Run with --apply to import.`)
    return
  }

  // Apply — copy and register
  copyFileSync(sourcePath, targetPath)
  console.log(`  ✓ copied: ${targetPath}`)
  addToPlaybookRegistry(basename(fileArg), summary, "canonical")
}

main()
