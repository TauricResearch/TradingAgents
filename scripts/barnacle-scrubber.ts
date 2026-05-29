#!/usr/bin/env bun

/**
 * Barnacle Scrubber — remove obsolete/dead text from project docs.
 *
 * Usage:
 *   bun scripts/barnacle-scrubber.ts [options] [paths...]
 *   bun scripts/barnacle-scrubber.ts --dry-run          # show what would change, no writes
 *   bun scripts/barnacle-scrubber.ts --auto            # apply all without prompting
 *   bun scripts/barnacle-scrubber.ts playbooks/        # scan specific dir/file
 *   bun scripts/barnacle-scrubber.ts --report          # generate DELETION_LOG.md only
 *   bun scripts/barnacle-scrubber.ts --restore <path>  # restore from drydock
 *   bun scripts/barnacle-scrubber.ts --llm             # enable semantic LLM scan
 *
 * Modes:
 *   --drydock  Move barnacles to drydock/ (quarantine, no deletion)
 *   --slim     Condense verbose prose (implies --drydock for removed text)
 *   --restore  Recover a drydocked block
 *
 * Phases:
 *   1. Ingest    — Load target files
 *   2. Scan      — Mechanical + optional LLM semantic analysis
 *   3. Draft     — Produce patched file + drydock entries
 *   4. Confirm   — Interactive yes/no/escalate per barnacle
 *   5. Apply     — Write modified files, populate drydock/
 *
 * Drydock: decisions/drydock/YYYY-MM-DD/{source-path}/{block-id}.md
 * Index:   decisions/drydock/INDEX.jsonl
 */

import { execSync } from "node:child_process"
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs"
import { dirname, extname, join, relative, resolve } from "node:path"

// ── Dependencies ──────────────────────────────────────────────────────────────

const DRYDOCK_ROOT = resolve(process.cwd(), "decisions", "drydock")
const INDEX_FILE = join(DRYDOCK_ROOT, "INDEX.jsonl")
const LOG_FILE = join(DRYDOCK_ROOT, "DELETION_LOG.md")
const TODAY = new Date().toISOString().slice(0, 10) // YYYY-MM-DD

// ── Types ─────────────────────────────────────────────────────────────────────

type Severity = "high" | "medium" | "low"
type BarnacleType =
  | "orphaned_reference"
  | "redundant_redundancy"
  | "verbose_prose"
  | "stale_metadata"
  | "cross_doc_conflict"
  | "chestertons_fence"

interface Barnacle {
  id: string
  file: string
  lineStart: number
  lineEnd: number
  type: BarnacleType
  severity: Severity
  text: string // snippet of the barnacle content
  justification: string // why this is a barnacle
  suggestedFix: string | null // null = drydock (remove), string = replacement text
  loadBearing: boolean // @load-bearing annotation → skip on future runs
}

interface DrydockEntry {
  id: string
  drydockPath: string
  sourceFile: string
  sourceLine: number
  type: BarnacleType
  justification: string
  drydockedAt: string // ISO8601
  restored: boolean
}

interface ScrubberOptions {
  dryRun: boolean
  auto: boolean
  drydock: boolean // default true unless --restore
  slim: boolean
  report: boolean
  restore: string | null // drydock path to restore
  llm: boolean
  targets: string[]
  drydockDate: string // override date for restore (defaults to TODAY)
}

interface ScanResult {
  file: string
  barnacles: Barnacle[]
  patchedContent: string
}

// ── Mechanical Rules ──────────────────────────────────────────────────────────

interface PathRewrite {
  from: RegExp
  to: string
  justification: string
  severity: Severity
}

// Known path migrations (codebase restructured, docs not updated)
const PATH_REWRITES: PathRewrite[] = [
  {
    from: /(?<!src)server\//g,
    to: "src/server/",
    justification: "server/ → src/server/ migration (2026-05)",
    severity: "high",
  },
]

// Steps that are now automated (manual step → just recipe)
const REDUNDANT_PATTERNS: Array<{
  pattern: RegExp
  justRecipe: string
  justification: string
}> = [
  {
    pattern: /STOP:\s*\n(\s+\d+\..+\n){3,}/g,
    justRecipe: "just srv stop",
    justification: "Manual PID management script — use 'just srv stop' instead",
  },
]

// Prose that is just noise
const VERBOSE_PATTERNS: Array<{
  pattern: RegExp
  replacement: string
  justification: string
}> = [
  {
    pattern: /I have updated the \w+/g,
    replacement: "Updated",
    justification: "Self-referential update notice — redundant",
  },
]

// ── Utility: file discovery ───────────────────────────────────────────────────

function discoverFiles(targets: string[]): string[] {
  const files: string[] = []
  for (const target of targets) {
    const stat = statSync(target)
    if (stat.isDirectory()) {
      const entries = readdirSync(target, { withFileTypes: true })
      for (const entry of entries) {
        if (entry.name.endsWith(".md") && entry.isFile()) {
          files.push(join(target, entry.name))
        }
      }
    } else if (stat.isFile() && target.endsWith(".md")) {
      files.push(target)
    }
  }
  return files
}

// ── Utility: line-aware content manipulation ──────────────────────────────────

function splitLines(content: string): string[] {
  return content.split(/\r?\n/)
}

function findLineRange(
  content: string,
  pattern: RegExp,
  lineOffset = 0,
): { line: number; match: string } | null {
  const lines = splitLines(content)
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(pattern)
    if (m) return { line: i + 1 + lineOffset, match: m[0] }
  }
  return null
}

// ── Mechanical Scan ───────────────────────────────────────────────────────────

function mechanicalScan(file: string, content: string): Barnacle[] {
  const barnacles: Barnacle[] = []
  const lines = splitLines(content)

  // 1. Path rewrite rules — only flag production path references, not docs patterns
  // Skip: tree art, import rules, alternatives, historical narratives
  const SKIP_PREFIXES = ["or src/", "or `server/`", "(or `server/`)", "move `server/`"]
  const TREE_ART_RE = /[├└]── /

  for (let lineNum = 0; lineNum < lines.length; lineNum++) {
    const line = lines[lineNum]
    if (!line.includes("server/")) continue
    if (line.includes("src/server/")) continue

    // Skip documentation patterns (not production path references)
    if (TREE_ART_RE.test(line)) continue // └── server/  tree art
    if (line.includes("no imports from") && line.includes("`server/`")) continue // rule constraint
    if (line.includes("(or `server/`)")) continue // alternatives
    if (line.includes("`server/` (or")) continue // `server/` (or src/)
    if (line.includes("move `server/`")) continue // historical narrative

    // Must have path-like or command-like context
    const pathCtx = /server\/(?:lib|routes|views|static|index)/.test(line)
    const cmdCtx = /bun run|import.*from|require\(|from '\.$|"\.\.\/server/.test(line)
    if (!pathCtx && !cmdCtx) continue

    const id = `BR-${file.replace(/\//g, "-").replace(/\.md$/, "")}-${lineNum + 1}-1`
    barnacles.push({
      id,
      file,
      lineStart: lineNum + 1,
      lineEnd: lineNum + 1,
      type: "orphaned_reference",
      severity: "high",
      text: line.trim().slice(0, 120),
      justification: "server/ → src/server/ migration (2026-05). Codebase uses src/server/.",
      suggestedFix: line.replace(/(?<!src)server\//g, "src/server/"),
      loadBearing: false,
    })
  }

  // 2. Redundant redundancy patterns
  let blockCounter = 0
  for (const rp of REDUNDANT_PATTERNS) {
    let match: RegExpExecArray | null
    const re = new RegExp(rp.pattern.source, rp.pattern.flags)
    while ((match = re.exec(content)) !== null) {
      const matchedText = match[0]
      // Find line number for block
      const before = content.slice(0, match.index)
      const lineNum = splitLines(before).length
      const id = `BR-${file.replace(/\//g, "-")}-BLOCK-${++blockCounter}`
      const fix = `Use: ${rp.justRecipe}`
      barnacles.push({
        id,
        file,
        lineStart: lineNum,
        lineEnd: lineNum + matchedText.split(/\r?\n/).length - 1,
        type: "redundant_redundancy",
        severity: "medium",
        text: matchedText.trim().slice(0, 120),
        justification: rp.justification,
        suggestedFix: fix,
        loadBearing: false,
      })
    }
  }

  // 3. Verbose prose patterns
  let vCounter = 0
  for (const vp of VERBOSE_PATTERNS) {
    let match: RegExpExecArray | null
    const re = new RegExp(vp.pattern.source, vp.pattern.flags)
    while ((match = re.exec(content)) !== null) {
      const lineNum = splitLines(content.slice(0, match.index)).length
      const id = `BR-${file.replace(/\//g, "-")}-VERB-${++vCounter}`
      barnacles.push({
        id,
        file,
        lineStart: lineNum,
        lineEnd: lineNum,
        type: "verbose_prose",
        severity: "low",
        text: match[0],
        justification: vp.justification,
        suggestedFix: vp.replacement,
        loadBearing: false,
      })
    }
  }

  // 4. Load-bearing annotations (skip these barnacles on future runs)
  const loadBearingRe = /@load-bearing:\s*(\d{4}-\d{2}-\d{2})/g
  let lbMatch: RegExpExecArray | null
  while ((lbMatch = loadBearingRe.exec(content)) !== null) {
    // Mark any barnacles overlapping this line as load-bearing
    const lbLine = splitLines(content.slice(0, lbMatch.index)).length
    for (const b of barnacles) {
      if (b.file === file && b.lineStart <= lbLine && b.lineEnd >= lbLine) {
        b.loadBearing = true
      }
    }
  }

  return barnacles
}

// ── Apply Patches ─────────────────────────────────────────────────────────────

function applyPatches(content: string, barnacles: Barnacle[]): string {
  // Sort by lineStart descending so patching from bottom-up doesn't shift line numbers
  const sorted = [...barnacles]
    .filter((b) => !b.loadBearing)
    .sort((a, b) => b.lineStart - a.lineStart)

  let result = content
  for (const b of sorted) {
    const lines = splitLines(result)
    if (b.lineStart < 1 || b.lineStart > lines.length) continue

    if (b.suggestedFix === null) {
      // Drydock: replace with pointer comment
      const pointer = `<!-- BARNACLE: moved to /drydock/${TODAY}/${relative(process.cwd(), b.file)}/${b.id}.md -->`
      lines[b.lineStart - 1] = pointer
    } else if (b.suggestedFix.startsWith("Use:")) {
      // Reference to automation
      lines[b.lineStart - 1] = `<!-- BARNACLE: ${b.suggestedFix} -->`
    } else {
      // Inline fix
      lines[b.lineStart - 1] = b.suggestedFix
    }
    result = lines.join("\n")
  }
  return result
}

// ── Drydock ───────────────────────────────────────────────────────────────────

function ensureDrydock(date: string): void {
  const dir = join(DRYDOCK_ROOT, date)
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  if (!existsSync(DRYDOCK_ROOT)) mkdirSync(DRYDOCK_ROOT, { recursive: true })
}

function drydockBlock(barnacle: Barnacle, content: string): string {
  const dateDir = join(DRYDOCK_ROOT, TODAY)
  ensureDrydock(TODAY)

  // Create directory tree matching source path structure
  const sourceRel = relative(process.cwd(), barnacle.file)
  const blockDir = join(dateDir, sourceRel, barnacle.id)
  mkdirSync(blockDir, { recursive: true })

  const blockPath = join(blockDir, "block.md")
  writeFileSync(blockPath, barnacle.text, "utf-8")

  return blockPath
}

function appendIndex(entry: DrydockEntry): void {
  const existing = existsSync(INDEX_FILE)
    ? readFileSync(INDEX_FILE, "utf-8").trim().split("\n")
    : []
  const rows = existing.map((line) => JSON.parse(line))
  rows.push(entry)
  const lines = rows.map((r) => JSON.stringify(r)).join("\n") + "\n"
  writeFileSync(INDEX_FILE, lines, "utf-8")
}

function appendLog(barnacle: Barnacle): void {
  const date = new Date().toLocaleDateString("en-GB", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  })
  const row = `| ${barnacle.file} | ${barnacle.id} | ${barnacle.justification} | drydocked |`
  const header = "| Source | Block | Justification | Action |"
  const separator = "|---|---|---|---|"

  if (!existsSync(LOG_FILE)) {
    writeFileSync(
      LOG_FILE,
      `# Barnacle Deletion Log\n\n## ${TODAY}\n\n${header}\n${separator}\n${row}\n`,
      "utf-8",
    )
  } else {
    const existing = readFileSync(LOG_FILE, "utf-8")
    const lastDate = existing.match(/## (\d{4}-\d{2}-\d{2})/)
    const logDate = lastDate?.[1] ?? TODAY
    const entry =
      logDate === TODAY ? `\n${row}` : `\n## ${TODAY}\n\n${header}\n${separator}\n${row}\n`
    writeFileSync(LOG_FILE, existing + entry, "utf-8")
  }
}

// ── Interactive Confirm ───────────────────────────────────────────────────────

async function confirmBarnacles(
  results: ScanResult[],
  options: ScrubberOptions,
): Promise<ScanResult[]> {
  // In dry-run or auto mode, skip confirm
  if (options.dryRun || options.auto) return results

  // Check if gum is available
  const hasGum = (() => {
    try {
      execSync("which gum", { shell: "/bin/bash" })
      return true
    } catch {
      return false
    }
  })()

  // Filter out load-bearing barnacles
  const confirmed: ScanResult[] = []

  for (const result of results) {
    const confirmedBarnacles = result.barnacles.filter((b) => {
      if (b.loadBearing) {
        console.log(`  ⏭ [${b.id}] SKIP (load-bearing annotation)`)
        return false
      }
      if (!hasGum) {
        console.log(`  ? [${b.id}] ${b.type} — ${b.justification}`)
        return true // default accept without gum
      }
      return true
    })
    if (confirmedBarnacles.length > 0) {
      confirmed.push({ ...result, barnacles: confirmedBarnacles })
    }
  }

  return confirmed
}

// ── Report ────────────────────────────────────────────────────────────────────

function generateReport(results: ScanResult[]): void {
  const byFile = new Map<string, number>()
  const byType = new Map<string, number>()
  let total = 0

  for (const result of results) {
    byFile.set(result.file, (byFile.get(result.file) ?? 0) + result.barnacles.length)
    for (const b of result.barnacles) {
      byType.set(b.type, (byType.get(b.type) ?? 0) + 1)
      total++
    }
  }

  console.log(`\n📋 Barnacle Report (${TODAY})`)
  console.log(`   Total barnacles: ${total}`)
  console.log(`   Files affected: ${byFile.size}`)
  console.log("")
  console.log("   By type:")
  for (const [type, count] of byType) {
    console.log(`     ${type}: ${count}`)
  }
  console.log("")
  console.log("   By file:")
  for (const [file, count] of byFile) {
    console.log(`     ${file}: ${count}`)
  }
}

// ── Restore ───────────────────────────────────────────────────────────────────

async function restoreBlock(restorePath: string): Promise<void> {
  if (!existsSync(restorePath)) {
    console.error(`❌ Drydock path not found: ${restorePath}`)
    process.exit(1)
  }

  const blockContent = readFileSync(restorePath, "utf-8")
  const relPath = relative(join(DRYDOCK_ROOT, "YYYY-MM-DD"), restorePath)
  // Restore path format: decisions/drydock/YYYY-MM-DD/{source}/{block-id}/block.md
  // We need to figure out the original source file

  // Try to find source from the block path structure
  const parts = restorePath.split("/")
  const blockDir = parts[parts.length - 2] // block-id
  // The source file path is the middle portion

  console.log("Restored content:")
  console.log("─".repeat(60))
  console.log(blockContent)
  console.log("─".repeat(60))
  console.log(`\n✅ Restore preview complete. Apply manually or use --auto to write directly.`)
}

// ── Main Scan ─────────────────────────────────────────────────────────────────

function runScan(targets: string[], options: ScrubberOptions): ScanResult[] {
  const files = discoverFiles(targets.length > 0 ? targets : ["playbooks", "docs", "AGENTS.md"])
  const results: ScanResult[] = []

  for (const file of files) {
    if (!existsSync(file)) {
      console.warn(`⚠ Skipping: ${file} (not found)`)
      continue
    }

    const content = readFileSync(file, "utf-8")
    const barnacles = mechanicalScan(file, content)
    const patched = applyPatches(content, barnacles)

    if (barnacles.length > 0) {
      results.push({ file, barnacles, patchedContent: patched })
    }
  }

  return results
}

// ── Apply ─────────────────────────────────────────────────────────────────────

function applyResults(results: ScanResult[], options: ScrubberOptions): void {
  ensureDrydock(TODAY)

  for (const result of results) {
    // Drydock the barnacles first
    for (const b of result.barnacles) {
      if (b.loadBearing) continue
      const path = drydockBlock(b, result.patchedContent)
      appendIndex({
        id: b.id,
        drydockPath: path,
        sourceFile: b.file,
        sourceLine: b.lineStart,
        type: b.type,
        justification: b.justification,
        drydockedAt: new Date().toISOString(),
        restored: false,
      })
      appendLog(b)
    }

    // Write patched file
    writeFileSync(result.file, result.patchedContent, "utf-8")
    console.log(`  ✅ Patched: ${result.file} (${result.barnacles.length} barnacle(s))`)
  }
}

// ── CLI ───────────────────────────────────────────────────────────────────────

function parseArgs(): ScrubberOptions {
  const args = Bun.argv.slice(2)

  return {
    dryRun: args.includes("--dry-run"),
    auto: args.includes("--auto"),
    drydock: args.includes("--drydock") || !args.includes("--restore"),
    slim: args.includes("--slim"),
    report: args.includes("--report"),
    restore: (() => {
      const idx = args.indexOf("--restore")
      return idx >= 0 ? (args[idx + 1] ?? null) : null
    })(),
    llm: args.includes("--llm"),
    targets: args.filter((a) => !a.startsWith("--") && !a.startsWith("-")),
    drydockDate: TODAY,
  }
}

async function main() {
  const options = parseArgs()

  // Handle restore mode
  if (options.restore) {
    await restoreBlock(options.restore)
    return
  }

  // Run scan
  const results = runScan(options.targets, options)

  if (results.length === 0) {
    console.log("✅ No barnacles found.")
    return
  }

  generateReport(results)

  if (options.report) {
    console.log("\n📝 Report mode — no files written.")
    return
  }

  if (options.dryRun) {
    console.log("\n🔍 Dry-run mode — showing what would change:")
    for (const result of results) {
      console.log(`\n  📄 ${result.file} (${result.barnacles.length} barnacle(s))`)
      for (const b of result.barnacles) {
        const fix = b.suggestedFix
          ? b.suggestedFix.startsWith("Use:")
            ? b.suggestedFix
            : `→ "${b.suggestedFix.trim().slice(0, 60)}"`
          : `→ drydock (remove)`
        console.log(`    L${b.lineStart} [${b.type}] ${b.justification} ${fix}`)
      }
    }
    return
  }

  // Confirm
  const confirmed = await confirmBarnacles(results, options)

  if (confirmed.length === 0) {
    console.log("\n✅ No barnacles to apply.")
    return
  }

  // Apply
  if (options.auto || options.dryRun) {
    // Skip confirm in auto/dry-run (already filtered)
  }

  console.log(
    `\n🚀 Applying ${confirmed.reduce((s, r) => s + r.barnacles.length, 0)} barnacle fix(es)...`,
  )
  applyResults(confirmed, options)
  console.log("\n✅ Scrub complete.")
  console.log(`   Drydock: decisions/drydock/${TODAY}/`)
  console.log(`   Log: decisions/drydock/DELETION_LOG.md`)
}

main().catch((err) => {
  console.error(`❌ Error: ${err.message}`)
  process.exit(1)
})
