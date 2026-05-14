#!/usr/bin/env bun

/**
 * Unified registry management CLI.
 *
 * Usage:
 *   bun scripts/reg.ts list <registry>    # list entries (briefs, debriefs, decisions, playbooks, docs, code, lexicon)
 *   bun scripts/reg.ts sync [--fix]       # sync all indexes from disk
 *   bun scripts/reg.ts check              # check for stale entries
 *   bun scripts/reg.ts enrich [--apply]   # enrich code index with JSDoc summaries
 *
 * Individual scripts are kept for specialized operations:
 *   reg-mine.ts    # extract info from documents
 *   reg-import.ts  # import entries
 *   reg-promote.ts # promote playbooks
 *   reg-state.ts   # show registry state
 */

import { spawn } from "node:child_process"
import { existsSync } from "node:fs"
import { join } from "node:path"

const SCRIPTS_DIR = join(import.meta.dir)

// Map subcommand → [script, ...args]
type SubcommandHandler = (args: string[]) => Promise<number> | number

// ── Handlers ─────────────────────────────────────────────────────────────────

async function runScript(script: string, extraArgs: string[]): Promise<number> {
  const scriptPath = join(SCRIPTS_DIR, script)
  if (!existsSync(scriptPath)) {
    console.error(`Script not found: ${scriptPath}`)
    return 1
  }

  return new Promise((resolve) => {
    const child = spawn("bun", [scriptPath, ...extraArgs], {
      cwd: process.cwd(),
      stdout: "inherit",
      stderr: "inherit",
      stdin: "inherit",
    })
    child.on("close", (code) => resolve(code ?? 1))
    child.on("error", () => resolve(1))
  })
}

const handlers: Record<string, SubcommandHandler> = {
  // List entries from a registry index
  list: async (args) => {
    return runScript("reg-list.ts", args)
  },

  // Sync indexes from disk
  sync: async (args) => {
    return runScript("reg-sync.ts", ["--all", ...args])
  },

  // Check for stale entries
  check: async (_args) => {
    return runScript("reg-check.ts", [])
  },

  // Enrich code index with JSDoc summaries
  enrich: async (args) => {
    return runScript("reg-enrich.ts", args)
  },

  // Mine: extract info from documents (specialized, keep as-is)
  mine: async (args) => {
    return runScript("reg-mine.ts", args)
  },

  // Import entries from a file
  import: async (args) => {
    return runScript("reg-import.ts", args)
  },

  // Promote a playbook (see what would be stripped)
  promote: async (args) => {
    return runScript("reg-promote.ts", args)
  },

  // Show registry state
  state: async (_args) => {
    return runScript("reg-state.ts", [])
  },

  // Sync scripts index (separate from main sync)
  scripts: async (args) => {
    return runScript("reg-sync-scripts.ts", args)
  },
}

// ── Main ─────────────────────────────────────────────────────────────────────

const subcommand = Bun.argv[2]
const extraArgs = Bun.argv.slice(3)

if (!subcommand) {
  console.error(`Usage: bun scripts/reg.ts <subcommand> [args]`)
  console.error("")
  console.error("Subcommands:")
  for (const name of Object.keys(handlers).sort()) {
    console.error(`  ${name.padEnd(10)} — see --help for details`)
  }
  console.error("")
  console.error("Individual scripts (not consolidated):")
  console.error("  reg-mine.ts, reg-import.ts, reg-promote.ts, reg-state.ts, reg-sync-scripts.ts")
  process.exit(1)
}

const handler = handlers[subcommand]
if (!handler) {
  console.error(`Unknown subcommand: ${subcommand}`)
  console.error(`Known: ${Object.keys(handlers).sort().join(", ")}`)
  process.exit(1)
}

const code = await handler(extraArgs)
process.exit(code)
