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

import { execSync, spawnSync } from "node:child_process"
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
import { llm } from "./lib/llm.ts"

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
  llmDetected?: boolean // detected by LLM scan (not mechanical)
  anomalyType?: AnomalyType // set if escalated for user decision
}

type AnomalyType =
  | "context_conflict"
  | "ambiguous_instruction"
  | "stale_metadata"
  | "logic_paradox"
  | "chestertons_fence"

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

interface LlmBarnacle {
  lineStart: number
  lineEnd: number
  type: BarnacleType
  severity: Severity
  justification: string
  snippet: string
  anomalyType?: AnomalyType
}

interface SlimResult {
  originalLines: string[]
  condensedLines: string[]
  removals: Array<{ lineStart: number; lineEnd: number; text: string }>
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

// ── LLM Semantic Scan ─────────────────────────────────────────────────────────

const LLM_SCAN_SYSTEM_PROMPT = `You are a Senior Systems Editor specializing in Operational Brevity.
Analyze the provided document for "semantic barnacles" — content that is not structurally wrong
but is semantically obsolete, contradictory, or load-bearing in non-obvious ways.

Return a JSON array of findings. Each finding must have:
- lineStart (number): approximate starting line number
- lineEnd (number): approximate ending line number
- type: "cross_doc_conflict" | "chestertons_fence" | "stale_metadata" | "verbose_prose"
- severity: "high" | "medium" | "low"
- justification: one-sentence explanation
- snippet: the problematic text (max 200 chars)
- anomalyType (optional): "context_conflict" | "ambiguous_instruction" | "stale_metadata" | "logic_paradox" | "chestertons_fence"

CHESTERTON'S FENCE: text that looks useless but likely has a hidden reason for existing.
Flag as chestertons_fence anomalyType if unsure.

Only return REAL problems. If the document is clean, return [].`

const LLM_SLIM_SYSTEM_PROMPT = `You are a Senior Systems Editor. Condense the provided text while preserving
ALL operational meaning, code references, file paths, and numbers.

Rules:
1. Remove filler: "I have updated", "Please note", "It is worth mentioning"
2. Merge redundant adjacent paragraphs
3. Convert passive explanations to active instructions
4. Keep all code blocks, table structure, and file paths intact
5. Remove meta-commentary about the document itself
6. Do NOT remove any @load-bearing annotations

Return the condensed text only. No explanations.`

async function llmScanFile(file: string, content: string): Promise<Barnacle[]> {
  const lines = splitLines(content)
  // Only scan files with enough content to matter
  if (lines.length < 20) return []

  // Chunk: scan in 300-line windows with 50-line overlap to avoid missing
  // barnacles at chunk boundaries. Long files get scanned in full.
  const CHUNK_SIZE = 300
  const OVERLAP = 50
  const allFindings: LlmBarnacle[] = []

  for (let start = 0; start < lines.length; start += CHUNK_SIZE - OVERLAP) {
    const end = Math.min(start + CHUNK_SIZE, lines.length)
    const chunk = lines.slice(start, end).join("\n")
    const lineOffset = start // add to the LLM's line numbers so they're global

    try {
      const response = await llm(
        [
          { role: "system", content: LLM_SCAN_SYSTEM_PROMPT },
          {
            role: "user",
            content: `File: ${file}\nLines ${start + 1}-${end} of ${lines.length}\n\n${chunk}`,
          },
        ],
        {
          temperature: 0.1,
          maxTokens: 2000,
          title: "barnacle-scrubber-llm-scan",
        },
      )

      // Parse JSON from response (may be wrapped in markdown code fences)
      const jsonMatch = response.match(/```(?:json)?\s*([\s\S]*?)```/) ?? [null, response]
      const findings: LlmBarnacle[] = JSON.parse(jsonMatch[1]?.trim() ?? "[]")

      if (Array.isArray(findings)) {
        for (const f of findings) {
          // Offset line numbers from chunk-relative to file-global
          allFindings.push({
            ...f,
            lineStart: (f.lineStart ?? 1) + lineOffset,
            lineEnd: (f.lineEnd ?? f.lineStart ?? 1) + lineOffset,
          })
        }
      }
    } catch (err) {
      console.warn(
        `  ⚠ LLM scan chunk ${start + 1}-${end} of ${file} failed: ${(err as Error).message?.slice(0, 80)}`,
      )
      // Continue with next chunk
    }

    if (end >= lines.length) break
  }

  if (allFindings.length === 0) return []

  // Deduplicate: findings within OVERLAP lines of each other are likely duplicates
  const deduped: LlmBarnacle[] = []
  for (const f of allFindings) {
    const isDup = deduped.some(
      (d) => Math.abs(d.lineStart - f.lineStart) <= OVERLAP && d.type === f.type,
    )
    if (!isDup) deduped.push(f)
  }

  return deduped.map((f, i) => ({
    id: `LLM-${file.replace(/\//g, "-").replace(/\.md$/, "")}-${i + 1}`,
    file,
    lineStart: f.lineStart ?? 1,
    lineEnd: f.lineEnd ?? f.lineStart ?? 1,
    type: ["cross_doc_conflict", "chestertons_fence", "stale_metadata", "verbose_prose"].includes(
      f.type,
    )
      ? (f.type as BarnacleType)
      : "chestertons_fence",
    severity: f.severity ?? "medium",
    text: f.snippet?.slice(0, 200) ?? "",
    justification: f.justification ?? "LLM-detected semantic barnacle",
    suggestedFix: null, // semantic barnacles default to drydock
    loadBearing: false, // LLM findings are NOT load-bearing — anomalyType drives escalation, not silent skip
    llmDetected: true,
    anomalyType: f.anomalyType,
  }))
}

// ── Slim Phase ────────────────────────────────────────────────────────────────

async function slimContent(file: string, content: string): Promise<SlimResult | null> {
  const lines = splitLines(content)
  if (lines.length < 30) return null // too short to slim

  try {
    const condensed = await llm(
      [
        { role: "system", content: LLM_SLIM_SYSTEM_PROMPT },
        { role: "user", content },
      ],
      {
        temperature: 0.1,
        maxTokens: Math.ceil(lines.length * 1.5), // allow expansion
        title: "barnacle-scrubber-slim",
      },
    )

    const slimLines = splitLines(condensed)

    // Detect what was removed (simple line-based diff)
    const removals: SlimResult["removals"] = []
    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim()
      if (trimmed.length > 20 && !slimLines.some((s) => s.trim() === trimmed)) {
        // Check if this line's content is preserved elsewhere
        const key = trimmed.slice(0, 30).toLowerCase()
        if (!slimLines.some((s) => s.toLowerCase().includes(key))) {
          removals.push({ lineStart: i + 1, lineEnd: i + 1, text: trimmed })
        }
      }
    }

    return { originalLines: lines, condensedLines: slimLines, removals }
  } catch (err) {
    console.warn(`  ⚠ Slim failed for ${file}: ${(err as Error).message?.slice(0, 80)}`)
    return null
  }
}

// ── Anomaly Escalation ────────────────────────────────────────────────────────

const ANOMALY_PROMPTS: Record<AnomalyType, string> = {
  context_conflict:
    "Found a reference to a potential decommissioned service or entity. It is not in the current manifest, but the text suggests it handles a critical edge case. Move to drydock or preserve?",
  ambiguous_instruction:
    "Manual step described that may be automated. An automated runbook exists but the text mentions a special-case override. Barnacle or valid manual exception?",
  stale_metadata:
    "Attribution or metadata references an entity/team no longer in the directory. Reassign or drydock?",
  logic_paradox:
    "Comment or description contradicts the actual logic. Slim to match code, or does the code need correction?",
  chestertons_fence:
    "This text appears useless but may be load-bearing — it might hold the ship together for reasons no longer understood. Move to drydock (auditable) or preserve in place?",
}

async function escalateAnomaly(barnacle: Barnacle): Promise<"drydock" | "preserve" | "skip"> {
  const anomalyType = barnacle.anomalyType ?? "chestertons_fence"
  const prompt = ANOMALY_PROMPTS[anomalyType]

  // Try gum for interactive prompt
  const hasGum = (() => {
    try {
      execSync("which gum", { shell: "/bin/bash" })
      return true
    } catch {
      return false
    }
  })()

  if (hasGum) {
    const proc = spawnSync(
      "gum",
      [
        "choose",
        "drydock",
        "preserve",
        "skip",
        "--header",
        `⚠ ANOMALY [${anomalyType}]: ${barnacle.id}`,
        "--header.foreground",
        "208",
        "--cursor",
        "> ",
      ],
      {
        input: `${prompt}\n\nFile: ${barnacle.file}:${barnacle.lineStart}\nText: ${barnacle.text.slice(0, 200)}`,
        encoding: "utf-8",
      },
    )
    if (proc.status !== 0) return "skip"
    const choice = proc.stdout.trim().toLowerCase()
    if (choice === "drydock" || choice === "preserve" || choice === "skip") {
      return choice
    }
  }

  // Fallback: console prompt (non-interactive — requires gum for real prompts)
  console.log(`\n⚠ ANOMALY [${anomalyType}]: ${barnacle.id}`)
  console.log(`   ${prompt}`)
  console.log(`   File: ${barnacle.file}:${barnacle.lineStart}`)
  console.log(`   Text: ${barnacle.text.slice(0, 200)}`)
  console.log(`   → Auto-skipping (gum not available — re-run with gum for interactive choice)`)

  return "skip" // default to skip without user input
}

// ── Restore ───────────────────────────────────────────────────────────────────

async function restoreBlock(restorePath: string, options: { auto: boolean }): Promise<void> {
  if (!existsSync(restorePath)) {
    console.error(`❌ Drydock path not found: ${restorePath}`)
    process.exit(1)
  }

  // Read the block
  const blockContent = readFileSync(restorePath, "utf-8")
  const blockDir = dirname(restorePath)
  const blockId = restorePath.split("/").slice(-2)[0] ?? "unknown"

  // Parse INDEX.jsonl to find source info
  let sourceFile = ""
  let sourceLine = 0

  if (existsSync(INDEX_FILE)) {
    const indexLines = readFileSync(INDEX_FILE, "utf-8").trim().split("\n")
    for (const line of indexLines) {
      try {
        const entry = JSON.parse(line)
        if (entry.drydockPath && entry.drydockPath.includes(blockId)) {
          sourceFile = entry.sourceFile ?? ""
          sourceLine = entry.sourceLine ?? 0
          break
        }
      } catch {
        // skip malformed index entries
      }
    }
  }

  if (!sourceFile) {
    console.error(`❌ Could not determine source file for block ${blockId}. Check INDEX.jsonl.`)
    process.exit(1)
  }

  if (!existsSync(sourceFile)) {
    console.error(`❌ Source file not found: ${sourceFile}`)
    process.exit(1)
  }

  const sourceContent = readFileSync(sourceFile, "utf-8")
  const sourceLines = splitLines(sourceContent)

  // Replace the pointer comment with the original content
  if (sourceLine > 0 && sourceLine <= sourceLines.length) {
    const pointerLine = sourceLines[sourceLine - 1]
    const isPointer =
      pointerLine.includes("<!-- BARNACLE:") || pointerLine.includes("<!-- BARNACLE")
    if (isPointer) {
      sourceLines[sourceLine - 1] = blockContent
    } else {
      // Insert at the line position
      sourceLines.splice(sourceLine - 1, 0, blockContent)
    }
  } else {
    // Append with annotation
    sourceLines.push("")
    sourceLines.push(`<!-- RESTORED from drydock/${blockId} -->`)
    sourceLines.push(blockContent)
  }

  const restoredContent = sourceLines.join("\n")

  console.log(`\n📄 Source: ${sourceFile}`)
  console.log(`   Block: ${blockId}`)
  console.log(`   Restored content:`)
  console.log("─".repeat(60))
  console.log(blockContent)
  console.log("─".repeat(60))

  if (options.auto) {
    writeFileSync(sourceFile, restoredContent, "utf-8")
    console.log(`✅ Restored ${blockId} to ${sourceFile}`)
  } else {
    console.log(`✅ Restore preview complete. Use --auto to apply, or apply manually.`)
  }
}

// ── Main Scan ─────────────────────────────────────────────────────────────────

async function runScan(targets: string[], options: ScrubberOptions): Promise<ScanResult[]> {
  const files = discoverFiles(targets.length > 0 ? targets : ["playbooks", "docs", "AGENTS.md"])
  const results: ScanResult[] = []

  for (const file of files) {
    if (!existsSync(file)) {
      console.warn(`⚠ Skipping: ${file} (not found)`)
      continue
    }

    const content = readFileSync(file, "utf-8")

    // Phase 1: Mechanical scan (always runs)
    const mechanical = mechanicalScan(file, content)
    let barnacles = [...mechanical]

    // Phase 2: LLM semantic scan (--llm flag)
    if (options.llm) {
      console.log(`  🔍 LLM scanning: ${file}`)
      const llmBarnacles = await llmScanFile(file, content)
      // Merge: deduplicate by approximate line overlap
      for (const lb of llmBarnacles) {
        const overlaps = barnacles.some(
          (b) => Math.abs(b.lineStart - lb.lineStart) <= 2 && b.type === lb.type,
        )
        if (!overlaps) barnacles.push(lb)
      }
    }

    // Phase 3: Slim (--slim flag, requires --llm for LLM access)
    if (options.slim && options.llm) {
      // Slim the original content so removal line numbers reference the real file.
      // The LLM produces condensed prose that naturally subsumes mechanical fixes.
      // Mechanical barnacles still appear in the dry-run report but are not separately
      // applied — the condensed output replaces the file wholesale.
      console.log(`  ✂ Slimming: ${file}`)
      const slimResult = await slimContent(file, content)
      if (slimResult && slimResult.removals.length > 0) {
        for (const r of slimResult.removals) {
          barnacles.push({
            id: `SLIM-${file.replace(/\//g, "-").replace(/\.md$/, "")}-L${r.lineStart}`,
            file,
            lineStart: r.lineStart,
            lineEnd: r.lineEnd,
            type: "verbose_prose",
            severity: "low",
            text: r.text.slice(0, 200),
            justification: "Verbose prose condensed via LLM slim",
            suggestedFix: null,
            loadBearing: false,
          })
        }

        // Replace content with condensed version (this is the final patched result)
        const patched = slimResult.condensedLines.join("\n")
        results.push({ file, barnacles, patchedContent: patched })
        continue
      }
    }

    const patched = applyPatches(content, barnacles)

    if (barnacles.length > 0) {
      results.push({ file, barnacles, patchedContent: patched })
    }
  }

  return results
}

// ── Apply ─────────────────────────────────────────────────────────────────────

async function applyResults(results: ScanResult[], options: ScrubberOptions): Promise<void> {
  ensureDrydock(TODAY)

  for (const result of results) {
    // Handle anomaly escalations first
    const appliedBarnacles: Barnacle[] = []
    for (const b of result.barnacles) {
      if (b.loadBearing) continue

      if (b.anomalyType) {
        const choice = await escalateAnomaly(b)
        if (choice === "preserve") continue
        if (choice === "skip") continue
        // choice === "drydock" — fall through
      }

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
      appliedBarnacles.push(b)
    }

    if (appliedBarnacles.length === 0) {
      console.log(`  ⏭ Skipped: ${result.file} (all barnacles load-bearing or preserved)`)
      continue
    }

    // Write patched file
    writeFileSync(result.file, result.patchedContent, "utf-8")
    console.log(`  ✅ Patched: ${result.file} (${appliedBarnacles.length} barnacle(s))`)
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
    await restoreBlock(options.restore, options)
    return
  }

  // Run scan
  console.log(
    `🔍 Scanning ${options.targets.length > 0 ? options.targets.join(", ") : "playbooks, docs, AGENTS.md"}...`,
  )
  const results = await runScan(options.targets, options)

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
        const llmTag = b.llmDetected ? " [LLM]" : ""
        const anomalyTag = b.anomalyType ? ` [anomaly:${b.anomalyType}]` : ""
        const fix = b.suggestedFix
          ? b.suggestedFix.startsWith("Use:")
            ? b.suggestedFix
            : `→ "${b.suggestedFix.trim().slice(0, 60)}"`
          : `→ drydock (remove)`
        console.log(
          `    L${b.lineStart} [${b.type}]${llmTag}${anomalyTag} ${b.justification} ${fix}`,
        )
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
  console.log(
    `\n🚀 Applying ${confirmed.reduce((s, r) => s + r.barnacles.length, 0)} barnacle fix(es)...`,
  )
  await applyResults(confirmed, options)
  console.log("\n✅ Scrub complete.")
  console.log(`   Drydock: decisions/drydock/${TODAY}/`)
  console.log(`   Log: decisions/drydock/DELETION_LOG.md`)
}

main().catch((err) => {
  console.error(`❌ Error: ${err.message}`)
  process.exit(1)
})
