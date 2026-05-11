#!/usr/bin/env bun
/**
 * Pretty-print a just recipe group menu.
 *
 * Usage: bun scripts/just-group-menu.ts <group-name>
 *
 * Parses `just --list --group <name>` and reprints with:
 *   - Group header
 *   - Recipes with descriptions
 *   - Optional: color-coded by common vs advanced usage
 */

const group = Bun.argv[2]

if (!group) {
  console.error("Usage: bun scripts/just-group-menu.ts <group-name>")
  process.exit(1)
}

// ── Group metadata ────────────────────────────────────────────────────────

const GROUPS: Record<string, { title: string; description: string; common: string[] }> = {
  bun: {
    title: "Bun — TypeScript Server Tooling",
    description: "Code quality, formatting, type-checking, server lifecycle, tests",
    common: ["check", "format", "lint", "serve", "test-cli"],
  },
  python: {
    title: "Python — TradingAgents Package",
    description: "LLM analysis, smoke tests, dependency install",
    common: ["analyze", "run", "test-smoke", "test-quick"],
  },
  db: {
    title: "Database — SQLite Backup & Maintenance",
    description: "LIVE and TEST database operations, backups, stats",
    common: ["db-stats", "backup", "db-active"],
  },
  diagrams: {
    title: "Diagrams — Graphviz & Mermaid",
    description: "Render .dot and .mmd source files to .svg",
    common: ["diagrams", "regen-diagrams"],
  },
  gn: {
    title: "GitNexus — Code Intelligence",
    description: "Index, query, visualize codebase relationships",
    common: ["gn-status", "gn-analyze", "gn-impact"],
  },
  hooks: {
    title: "Hooks — Git Workflow Automation",
    description: "Pre-push hooks, diagram regeneration",
    common: ["install-hooks", "push"],
  },
  hledger: {
    title: "hLedger — Plain-Text Accounting",
    description: "Cash balances, holdings, allocation, prices, backups",
    common: ["hl", "hl-cash", "hl-holdings", "hl-backup"],
  },
  meta: {
    title: "Meta — Project Orientation",
    description: "Help, info, state, navigation",
    common: ["help", "info"],
  },
  nav: {
    title: "Navigation — Group Shortcuts",
    description: "just <letter> to jump to any recipe group",
    common: ["b", "p", "db", "h", "r"],
  },
  pr: {
    title: "PR — GitHub Pull Request Helpers",
    description: "Fetch, summarize, list pull requests",
    common: ["pr-fetch", "pr-summarize", "prs"],
  },
  reg: {
    title: "Registry — Project Knowledge Base",
    description: "Briefs, debriefs, playbooks, decisions, lexicon",
    common: ["reg-state", "reg-sync", "reg-check"],
  },
  run: {
    title: "Run — Business Operations",
    description: "Analyze, portfolio, sync, trade planning",
    common: ["analyze", "portfolio-intel", "sync-prices", "trading"],
  },
  seed: {
    title: "Seed — Database Seeding",
    description: "Populate DEV and TEST databases",
    common: ["seed-db", "seed-db-positions", "seed-db-prices"],
  },
  srv: {
    title: "Server — Dashboard Lifecycle",
    description: "Start, stop, restart, logs, status",
    common: ["start", "stop", "restart", "status"],
  },
  td: {
    title: "td — Task Management",
    description: "Track issues, epics, work sessions",
    common: ["td-new", "td-next", "td-status"],
  },
  agent: {
    title: "Agent — Multi-Agent Coordination",
    description: "Session startup, task claiming, progress logging, handoffs",
    common: ["agent-orient", "agent-claim", "agent-sync", "agent-handoff"],
  },
  test: {
    title: "Test — Development Tools",
    description: "Test DB, seeding, reset, copy",
    common: ["test-init", "test-reset", "test-seed"],
  },
}

// ── Parse just --list output ──────────────────────────────────────────────

const proc = Bun.spawn({
  cmd: ["just", "--list", "--group", group],
  stdout: "pipe",
  stderr: "pipe",
})

let stdout = ""
for await (const chunk of proc.stdout) {
  stdout += new TextDecoder().decode(chunk)
}

const exitCode = await proc.exited
if (exitCode !== 0) {
  console.error(`Group "${group}" not found or just failed`)
  process.exit(1)
}

// ── Format output ─────────────────────────────────────────────────────────

const meta = GROUPS[group]

console.log("")
console.log(`╔${"═".repeat(60)}╗`)
console.log(`║ ${meta?.title ?? group}${" ".repeat(58 - (meta?.title ?? group).length)}║`)
console.log(`╚${"═".repeat(60)}╝`)

if (meta?.description) {
  console.log(`  ${meta.description}`)
}

console.log("")

// Parse recipes from just --list output
const lines = stdout.trim().split("\n")
let inGroup = false

for (const line of lines) {
  const trimmed = line.trim()

  // Skip group header in just output
  if (trimmed.startsWith("[") && trimmed.includes("]")) {
    inGroup = true
    continue
  }

  // Skip blank lines and non-recipe lines
  if (!trimmed || trimmed.startsWith("Available") || !inGroup) continue

  // Parse recipe line: "    recipe-name    # description"
  const match =
    trimmed.match(/^(\S+)\s*(?:\[.*\])?\s*#\s*(.*)$/) ||
    trimmed.match(/^(\S+)\s*(?:\[.*\])?\s+(.*)/)

  if (match) {
    const [, name, desc] = match
    const isCommon = meta?.common.includes(name)
    const marker = isCommon ? "●" : "○"
    console.log(`  ${marker} ${name.padEnd(28)} ${desc ?? ""}`)
  }
}

if (meta?.common.length) {
  console.log("")
  console.log(`  ● = commonly used    ○ = advanced / occasional`)
}

console.log("")
