#!/usr/bin/env bun
/**
 * Barnacle Alert Daemon.
 *
 * Scans the silo for barnacles: conventions without justification that
 * misdirect agents. Combines mechanical checks with LLM semantic analysis.
 *
 * A barnacle is a document fragment, script comment, or supposed "convention"
 * that:
 *   1. Misdirects — tells an agent to do the wrong thing
 *   2. Perpetuates bad practice — the more it is followed, the worse things get
 *   3. Has no living justification — nobody can explain why it exists
 *
 * Usage:
 *   bun scripts/barnacle-scan.ts              # full scan
 *   bun scripts/barnacle-scan.ts --mechanical # local checks only (no LLM)
 *   bun scripts/barnacle-scan.ts --quiet      # exit 1 if barnacles found
 */

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs"
import { join } from "node:path"

// Try to import llm.ts; fail gracefully if not available
let llm:
  | ((messages: Array<{ role: "system" | "user"; content: string }>) => Promise<string>)
  | null = null
try {
  const mod = await import("./lib/llm.ts")
  llm = mod.llm
} catch {
  // llm.ts not available — mechanical scan only
}

interface Barnacle {
  severity: "critical" | "warning" | "info"
  location: string
  description: string
  fix: string
  source: "mechanical" | "llm"
}

const findings: Barnacle[] = []

// ── Mechanical Checks ──

function checkCapitalizedJustfile() {
  if (existsSync(join(process.cwd(), "Justfile"))) {
    findings.push({
      severity: "warning",
      location: "Justfile (capitalized)",
      description:
        "Capitalized Justfile exists alongside justfile. On case-insensitive filesystems this creates a barnacle: agents manually rename after formatting.",
      fix: "rm Justfile; the tool default is lowercase justfile",
      source: "mechanical",
    })
  }
}

function checkStalePathReferences() {
  const agentsMd = readFileSync(join(process.cwd(), "AGENTS.md"), "utf-8")
  // Match paths that start with server/ or cli/ (not src/server/ or src/cli/)
  const stalePatterns = [
    {
      pattern: /(?<!src\/)server\/(lib|views|routes)/,
      desc: "References old 'server/' path instead of 'src/server/'",
    },
    {
      pattern: /(?<!src\/)cli\/(commands|lib)/,
      desc: "References old 'cli/' path instead of 'src/cli/'",
    },
  ]
  for (const { pattern, desc } of stalePatterns) {
    if (pattern.test(agentsMd)) {
      findings.push({
        severity: "critical",
        location: "AGENTS.md",
        description: desc,
        fix: "Update path references to use src/ prefix",
        source: "mechanical",
      })
    }
  }
}

function checkUnusedJustfileRecipes() {
  const justfile = readFileSync(join(process.cwd(), "justfile"), "utf-8")
  const recipePattern = /^([a-z][a-z0-9-]*)\s*[:=]/gm
  const recipes: string[] = []
  let m: RegExpExecArray | null = recipePattern.exec(justfile)
  while (m !== null) {
    recipes.push(m[1])
    m = recipePattern.exec(justfile)
  }

  // Exclude built-ins and nav shortcuts
  const exclude = new Set([
    "default",
    "b",
    "d",
    "db",
    "gn",
    "h",
    "hk",
    "lab",
    "m",
    "p",
    "pr",
    "r",
    "s",
    "srv",
    "t",
    "x",
  ])

  for (const recipe of recipes) {
    if (exclude.has(recipe)) continue
    // Check if recipe is referenced in docs or scripts
    const usedInJustfile =
      justfile.includes(`just ${recipe}`) ||
      justfile.includes(`:= ${recipe}`) ||
      justfile.includes(`alias ${recipe}`)
    if (!usedInJustfile) {
      // Quick grep in docs and scripts
      try {
        const docsResult = Bun.spawnSync({
          cmd: ["grep", "-r", recipe, "docs/", "playbooks/", "briefs/", "debriefs/"],
        })
        const scriptsResult = Bun.spawnSync({
          cmd: ["grep", "-r", recipe, "scripts/"],
        })
        const docsEmpty = new TextDecoder().decode(docsResult.stdout).trim() === ""
        const scriptsEmpty = new TextDecoder().decode(scriptsResult.stdout).trim() === ""

        if (docsEmpty && scriptsEmpty) {
          findings.push({
            severity: "info",
            location: `justfile recipe: ${recipe}`,
            description: `Recipe '${recipe}' is not referenced in docs, playbooks, or scripts. May be unused.`,
            fix: "Verify usage; remove if truly unused or document its purpose",
            source: "mechanical",
          })
        }
      } catch {
        // skip if grep fails
      }
    }
  }
}

function checkStalePlaybooks() {
  const pbDir = join(process.cwd(), "playbooks")
  for (const entry of readdirSync(pbDir, { withFileTypes: true })) {
    if (!entry.name.endsWith(".md")) continue
    const stat = statSync(join(pbDir, entry.name))
    const ageDays = (Date.now() - stat.mtimeMs) / (1000 * 60 * 60 * 24)
    if (ageDays > 30) {
      findings.push({
        severity: "info",
        location: `playbooks/${entry.name}`,
        description: `Playbook not modified in ${Math.round(ageDays)} days. May be stale.`,
        fix: "Review for accuracy against current practice",
        source: "mechanical",
      })
    }
  }
}

function checkDocsPathDrift() {
  const docsDir = join(process.cwd(), "docs")
  const docs = readdirSync(docsDir, { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith(".md"))
    .map((e) => e.name)

  // Check if docs/INDEX.jsonl mentions all docs
  const index = readFileSync(join(docsDir, "INDEX.jsonl"), "utf-8")
  for (const doc of docs) {
    if (!index.includes(doc)) {
      findings.push({
        severity: "warning",
        location: `docs/${doc}`,
        description: "Document exists on disk but is not in docs/INDEX.jsonl",
        fix: "Run: bun scripts/reg-sync.ts docs --fix",
        source: "mechanical",
      })
    }
  }
}

// ── LLM Phase ──

async function llmScan(): Promise<Barnacle[]> {
  if (!llm) {
    console.log("  (LLM scan skipped: scripts/lib/llm.ts not available)")
    return []
  }

  const conventions = readFileSync(
    join(process.cwd(), "playbooks/conventions-playbook.md"),
    "utf-8",
  )
  const agents = readFileSync(join(process.cwd(), "AGENTS.md"), "utf-8")
  const justfile = readFileSync(join(process.cwd(), "justfile"), "utf-8")

  // Select a subset of playbooks for context (too many tokens otherwise)
  const playbookFiles = [
    "cli-design-playbook.md",
    "just-playbook.md",
    "services-playbook.md",
    "unified-registry-playbook.md",
  ]
  const playbooks = playbookFiles
    .map((f) => {
      try {
        return readFileSync(join(process.cwd(), "playbooks", f), "utf-8")
      } catch {
        return ""
      }
    })
    .join("\n\n---\n\n")

  const prompt = `You are a barnacle hunter. A barnacle is a convention, rule, or documented practice that:
1. MISDIRECTS — tells someone to do the wrong thing
2. PERPETUATES BAD PRACTICE — following it makes things worse
3. HAS NO LIVING JUSTIFICATION — nobody can explain why it exists

Read these project documents and identify barnacles. Focus on:
- Rules that contradict actual practice (doc says X, code does Y)
- Conventions that fight tool defaults (e.g., capitalizing a filename the tool writes lowercase)
- "Always" or "never" statements with obvious exceptions
- Duplicate or conflicting guidance across documents
- Rules justified by problems that no longer exist

Return ONLY a JSON array. No markdown, no explanation. Format:
[
  {"severity": "critical|warning|info", "location": "file or area", "description": "what the barnacle is", "fix": "what to do about it"}
]

If no barnacles found, return [].

---
CONVENTIONS PLAYBOOK (defines what a barnacle is):
${conventions.slice(0, 3000)}

---
AGENTS.MD (project rules for agents):
${agents.slice(0, 3000)}

---
JUSTFILE (task runner facade):
${justfile.slice(0, 2000)}

---
SELECTED PLAYBOOKS:
${playbooks.slice(0, 3000)}
`

  try {
    const llmClient = llm
    if (!llmClient) return []
    const response = await llmClient([
      {
        role: "system",
        content: "You identify barnacles in project documentation. Return ONLY JSON.",
      },
      { role: "user", content: prompt },
    ])

    // Extract JSON from response (may be wrapped in markdown)
    const jsonMatch = response.match(/\[[\s\S]*\]/)
    if (!jsonMatch) return []

    const parsed = JSON.parse(jsonMatch[0])
    return parsed.map((b: Record<string, string>) => ({
      severity: b.severity as "critical" | "warning" | "info",
      location: b.location,
      description: b.description,
      fix: b.fix,
      source: "llm" as const,
    }))
  } catch (e) {
    console.log(`  (LLM scan failed: ${e instanceof Error ? e.message : String(e)})`)
    return []
  }
}

// ── Report ──

function printReport(barnacles: Barnacle[]) {
  const critical = barnacles.filter((b) => b.severity === "critical")
  const warning = barnacles.filter((b) => b.severity === "warning")
  const info = barnacles.filter((b) => b.severity === "info")

  console.log(`\n=== BARNACLE SCAN REPORT ===\n`)
  console.log(
    `Found: ${critical.length} critical | ${warning.length} warning | ${info.length} info\n`,
  )

  for (const b of critical) printBarnacle(b)
  for (const b of warning) printBarnacle(b)
  for (const b of info) printBarnacle(b)

  if (barnacles.length === 0) {
    console.log("No barnacles detected. Silo is clean.")
  }
}

function printBarnacle(b: Barnacle) {
  const icon = b.severity === "critical" ? "🔴" : b.severity === "warning" ? "🟡" : "🔵"
  const src = b.source === "mechanical" ? "[mech]" : "[llm]"
  console.log(`${icon} [${b.severity.toUpperCase()}] ${src} ${b.location}`)
  console.log(`   ${b.description}`)
  console.log(`   Fix: ${b.fix}\n`)
}

// ── Main ──

async function main() {
  const mechanicalOnly = Bun.argv.includes("--mechanical")
  const quiet = Bun.argv.includes("--quiet")

  console.log("Scanning for barnacles...\n")

  console.log("── Mechanical checks ──")
  checkCapitalizedJustfile()
  checkStalePathReferences()
  checkUnusedJustfileRecipes()
  checkStalePlaybooks()
  checkDocsPathDrift()
  console.log(`  ${findings.length} mechanical finding(s)\n`)

  if (!mechanicalOnly && llm) {
    console.log("── LLM semantic analysis ──")
    const llmFindings = await llmScan()
    findings.push(...llmFindings)
    console.log(`  ${llmFindings.length} LLM finding(s)\n`)
  }

  printReport(findings)

  if (quiet && findings.some((b) => b.severity === "critical" || b.severity === "warning")) {
    process.exit(1)
  }
}

main()
