#!/usr/bin/env bun
/**
 * reg-promote.ts — Show what would be stripped to make a playbook canonical.
 *
 * Given a project playbook, displays project-specific content that would be
 * removed by reg-mine.ts. Does not write to the registry by default.
 *
 * Modes:
 *   default      Summary of changes (counts, excerpts, placeholders)
 *   --diff       Line-by-line diff between original and sanitized
 *   --apply      Write to playbooks/ (delegates to reg-mine logic)
 *
 * Usage:
 *   bun scripts/reg-promote.ts lab-first-playbook.md
 *   bun scripts/reg-promote.ts conventions-playbook.md --diff
 *   bun scripts/reg-promote.ts conventions-playbook.md --apply
 *
 * Options:
 *   --source-dir DIR    Source directory (default: playbooks)
 *   --target-dir DIR    Target directory (default: playbooks)
 */

import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { REPLACEMENTS, sanitize } from "./lib/mine.ts"

function buildDiff(originalLines: string[], sanitizedLines: string[]): string[] {
  const out: string[] = []
  let i = 0
  let j = 0

  while (i < originalLines.length || j < sanitizedLines.length) {
    const orig = originalLines[i]
    const clean = sanitizedLines[j]

    if (orig === clean) {
      out.push(`  ${orig}`)
      i++
      j++
    } else if (orig !== undefined && clean !== undefined) {
      out.push(`- ${orig}`)
      out.push(`+ ${clean}`)
      i++
      j++
    } else if (orig !== undefined) {
      out.push(`- ${orig}`)
      i++
    } else {
      out.push(`+ ${clean}`)
      j++
    }
  }

  return out
}

function summarizeChanges(original: string, sanitized: string, filename: string): string[] {
  const out: string[] = []
  out.push(`── ${filename} ──`)
  out.push("")

  // Per-replacement counts
  let total = 0
  const lines: string[] = []
  for (const { pattern, replacement } of REPLACEMENTS) {
    const matches = original.match(pattern)
    if (matches && matches.length > 0) {
      total += matches.length
      const name = replacement.replace(/[<>]/g, "")
      lines.push(
        `  ${matches.length.toString().padStart(3)}  ${name.padEnd(20)}  (${pattern.source.slice(0, 42)})`,
      )
    }
  }

  if (total === 0) {
    out.push("  ✓ No project-specific tokens found — already clean")
    return out
  }

  out.push(`  Total replacements: ${total}`)
  out.push("")
  out.push("  Breakdown:")
  for (const l of lines) out.push(l)

  // Show first few excerpt lines that changed
  const origLines = original.split("\n")
  const cleanLines = sanitized.split("\n")
  const changed: string[] = []
  for (let k = 0; k < origLines.length && changed.length < 6; k++) {
    if (origLines[k] !== cleanLines[k]) {
      changed.push(`    ${origLines[k].slice(0, 80)}`)
    }
  }

  if (changed.length > 0) {
    out.push("")
    out.push("  Excerpts (first 6 changed lines):")
    for (const l of changed) out.push(l)
  }

  return out
}

function main(): void {
  const args = Bun.argv.slice(2)
  const diff = args.includes("--diff")
  const apply = args.includes("--apply")
  const sourceDirFlag = args.indexOf("--source-dir")
  const targetDirFlag = args.indexOf("--target-dir")

  const sourceDir = sourceDirFlag >= 0 ? args[sourceDirFlag + 1] || "playbooks" : "playbooks"
  const _targetDir = targetDirFlag >= 0 ? args[targetDirFlag + 1] || "playbooks" : "playbooks"

  const fileArg = args.find((a) => !a.startsWith("--"))
  if (!fileArg) {
    console.error(
      "Usage: bun scripts/reg-promote.ts <playbook-file> [--diff] [--apply] [--source-dir DIR] [--target-dir DIR]",
    )
    console.error("")
    console.error(
      "  playbook-file    Name of playbook in --source-dir (e.g. lab-first-playbook.md)",
    )
    console.error("  --diff           Show line-by-line diff")
    console.error("  --apply          Write to playbooks/ (same as reg-mine --apply)")
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

  if (apply) {
    // Delegate to reg-mine.ts --apply
    const proc = Bun.spawnSync({
      cmd: ["bun", "scripts/reg-mine.ts", fileArg, "--apply"],
      stdout: "pipe",
      stderr: "pipe",
    })
    console.log(new TextDecoder().decode(proc.stdout).trim())
    const err = new TextDecoder().decode(proc.stderr).trim()
    if (err) console.error(err)
    return
  }

  if (diff) {
    const origLines = raw.split("\n")
    const cleanLines = cleaned.split("\n")
    const diffLines = buildDiff(origLines, cleanLines)
    console.log(diffLines.join("\n"))
    return
  }

  // Default: summary
  const summary = summarizeChanges(raw, cleaned, fileArg)
  console.log(summary.join("\n"))
}

main()
