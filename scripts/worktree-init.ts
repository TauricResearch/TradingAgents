#!/usr/bin/env bun
/**
 * worktree-init — Create a git worktree with td-aware .td-root file.
 *
 * Usage:
 *   bun scripts/worktree-init.ts <name> [--base <branch>] [--task <td-id>] [--delete]
 *
 * Examples:
 *   bun scripts/worktree-init.ts alerts-phase2
 *   bun scripts/worktree-init.ts barnacle-scrubber --base main
 *   bun scripts/worktree-init.ts alerts-phase2 --task td-abc123
 *   bun scripts/worktree-init.ts alerts-phase2 --delete
 *
 * What it does:
 *   1. Creates git worktree at ../TradingAgents-<name> (sibling to repo root)
 *   2. Writes .td-root in the worktree pointing to this repo's root
 *   3. Optionally links a TD task via .sidecar-task file
 *   4. Prints the worktree path for cd'ing into
 */

import { execSync } from "node:child_process"
import { existsSync, readFileSync, writeFileSync } from "node:fs"
import { basename, dirname, join } from "node:path"

const args = Bun.argv.slice(2)

if (args.length === 0 || args.includes("--help") || args.includes("-h")) {
  console.log(`
worktree-init — Create a git worktree with td-aware .td-root

Usage:
  bun scripts/worktree-init.ts <name> [options]

Options:
  --base <branch>   Base branch to create from (default: current branch)
  --task <td-id>    Link a TD task ID (writes .sidecar-task file)
  --delete          Delete the worktree instead of creating
  --list            List existing worktrees

Example:
  bun scripts/worktree-init.ts alerts-phase2 --base main --task td-abc123
`)
  process.exit(0)
}

// ── Parse args ─────────────────────────────────────────────────────────

const name = args.find((a) => !a.startsWith("--"))
const baseBranch = args[args.indexOf("--base") + 1] || null
const taskId = args[args.indexOf("--task") + 1] || null
const doDelete = args.includes("--delete")
const doList = args.includes("--list")

if (!name && !doList) {
  console.error("Error: <name> required (or --list)")
  process.exit(1)
}

// ── Helpers ────────────────────────────────────────────────────────────

function sh(cmd: string, cwd?: string, trim_ = true): string {
  try {
    const result = execSync(cmd, { encoding: "utf8", timeout: 15000, cwd })
    return trim_ ? result.trim() : result
  } catch (e: unknown) {
    return (e as Error).message
  }
}

function green(msg: string) {
  console.log(`\x1b[32m✓\x1b[0m ${msg}`)
}
function red(msg: string) {
  console.error(`\x1b[31m✗\x1b[0m ${msg}`)
}
function yellow(msg: string) {
  console.log(`\x1b[33m→\x1b[0m ${msg}`)
}

// ── Detect repo root ───────────────────────────────────────────────────

function findRepoRoot(cwd: string): string | null {
  // Walk up looking for .git directory
  let dir = cwd
  for (let i = 0; i < 20; i++) {
    if (existsSync(join(dir, ".git"))) return dir
    const parent = dirname(dir)
    if (parent === dir) break // reached filesystem root
    dir = parent
  }
  return null
}

// ── List existing worktrees ─────────────────────────────────────────────

function listWorktrees(repoRoot: string): void {
  const output = sh(`git worktree list --porcelain`, repoRoot, false)
  // Don't trim here — trailing newlines are meaningful for parsing
  const rawLines = output.split("\n")

  console.log("")
  console.log("\x1b[36mGit worktrees:\x1b[0m")
  console.log("")

  // Parse --porcelain format into records
  const worktrees: { worktree: string; branch: string }[] = []
  let curWorktree = ""
  let curBranch = ""

  for (const rawLine of rawLines) {
    const line = rawLine.trimEnd()
    // Skip blank lines (double-newline separator in git porcelain format)
    if (!line) {
      // Only push when we already have a record (avoid double-blank at start)
      if (curWorktree) {
        worktrees.push({ worktree: curWorktree, branch: curBranch })
        curWorktree = ""
        curBranch = ""
      }
    } else if (line.startsWith("worktree ")) {
      curWorktree = line.slice(9)
    } else if (line.startsWith("branch ")) {
      curBranch = line.slice(7)
    }
  }
  // Push final record (after last blank-line terminator)
  if (curWorktree) {
    worktrees.push({ worktree: curWorktree, branch: curBranch })
  }

  for (const wt of worktrees) {
    const isMain = wt.worktree === repoRoot
    const mark = isMain ? "\x1b[33m[main]\x1b[0m" : "       "
    const cleanBranch = wt.branch.replace("refs/heads/", "")
    console.log(`  ${mark}  ${wt.worktree}`)
    if (cleanBranch) {
      console.log(`           Branch: ${cleanBranch}`)
    }
    console.log("")
  }

  // Check sibling worktrees (same parent dir as repo root)
  const parentDir = dirname(repoRoot)

  console.log("")
  console.log("\x1b[36mSibling worktrees with .td-root:\x1b[0m")
  console.log("")

  const siblings = sh(`ls -d "${parentDir}/TradingAgents-"* 2>/dev/null || true`, repoRoot, false)
    .split("\n")
    .map((s) => s.trimEnd())
    .filter(Boolean)

  let found = false
  for (const sibling of siblings) {
    const tdRootPath = join(sibling, ".td-root")
    if (existsSync(tdRootPath)) {
      const target = readFileSync(tdRootPath, "utf8").trim()
      const status =
        target === repoRoot
          ? "\x1b[32m(linked to this repo)\x1b[0m"
          : `\x1b[33m(points to: ${target})\x1b[0m`
      console.log(`  \x1b[32m✓\x1b[0m  ${basename(sibling)}  ${status}`)
      found = true
    }
  }

  if (!found) {
    console.log("  (none)")
  }

  console.log("")
  console.log(`\x1b[33m→\x1b[0m Create one: \`bun scripts/worktree-init.ts <name>\``)
  console.log("")
}

// ── Main ────────────────────────────────────────────────────────────────

const cwd = process.cwd()
const repoRoot = findRepoRoot(cwd)

if (!repoRoot) {
  red("Not inside a git repository. Run from within the project.")
  process.exit(1)
}

if (doList) {
  listWorktrees(repoRoot)
  process.exit(0)
}

const safeName = name?.replace(/[^a-zA-Z0-9_-]/g, "-").toLowerCase()
const worktreeName = `TradingAgents-${safeName}`
const worktreePath = join(dirname(repoRoot), worktreeName)
const _relativePath = `../${worktreeName}`

// ── Delete path ─────────────────────────────────────────────────────────

if (doDelete) {
  if (!existsSync(worktreePath)) {
    red(`Worktree not found: ${worktreePath}`)
    process.exit(1)
  }

  yellow(`Deleting worktree: ${worktreePath}`)
  const result = sh(`git worktree remove "${worktreePath}" --force`, repoRoot)

  if (result.includes("fatal") || result.includes("error")) {
    // Try removing just the directory if git fails
    console.log("  (git remove failed, trying directory removal)")
    try {
      execSync(`rm -rf "${worktreePath}"`, { encoding: "utf8", timeout: 5000 })
      green(`Removed: ${worktreePath}`)
    } catch {
      red(`Failed to remove: ${worktreePath}`)
      process.exit(1)
    }
  } else {
    green(`Removed worktree: ${worktreePath}`)
  }

  console.log("")
  green("Done. To create a new worktree:")
  console.log(`  bun scripts/worktree-init.ts ${safeName}`)
  console.log("")
  process.exit(0)
}

// ── Create path ─────────────────────────────────────────────────────────

// Check if worktree already exists
if (existsSync(worktreePath)) {
  const tdRootPath = join(worktreePath, ".td-root")
  if (existsSync(tdRootPath)) {
    const target = readFileSync(tdRootPath, "utf8").trim()
    if (target === repoRoot) {
      yellow(`Worktree already exists and is linked: ${worktreePath}`)
      console.log("")
      console.log(`  cd ${worktreePath}`)
      console.log(`  td usage --new-session`)
      console.log("")
      process.exit(0)
    } else {
      red(`Worktree exists but points to wrong repo: ${target}`)
      process.exit(1)
    }
  } else {
    red(`Worktree exists but has no .td-root: ${worktreePath}`)
    console.log(`  Run with --delete to remove, then recreate.`)
    process.exit(1)
  }
}

// Check max worktrees (limit: 3 extra + main = 4 total)
const worktrees = sh(`git worktree list --porcelain`, repoRoot)
const count = (worktrees.match(/worktree /g) || []).length
const maxWorktrees = parseInt(process.env.TD_MAX_WORKTREES || "3", 10)
if (count > maxWorktrees) {
  red(`Max worktrees reached (${maxWorktrees}). Delete one first:`)
  console.log("")
  console.log(`  bun scripts/worktree-init.ts ${safeName} --delete`)
  console.log("")
  process.exit(1)
}

// Determine base branch
const base = baseBranch || sh(`git branch --show-current`, repoRoot) || "main"
const branchName = safeName

console.log("")
yellow(`Creating worktree: ${worktreeName}`)
console.log(`  Base branch: ${base}`)
console.log(`  Worktree path: ${worktreePath}`)
console.log("")

// Create the worktree (git worktree add <path> -b <branch>)
const createResult = sh(`git worktree add "${worktreePath}" -b ${branchName}`, repoRoot)

if (createResult.includes("fatal") || createResult.includes("error")) {
  red(`Failed to create worktree: ${createResult}`)
  process.exit(1)
}

green(`Created worktree: ${worktreePath}`)
green(`Branch: ${branchName}`)

// Write .td-root pointing to repo root
const tdRootPath = join(worktreePath, ".td-root")
writeFileSync(tdRootPath, `${repoRoot}\n`)
green(`Written: .td-root → ${repoRoot}`)

// Link TD task if provided
if (taskId) {
  const sidecarTaskPath = join(worktreePath, ".sidecar-task")
  writeFileSync(sidecarTaskPath, `${taskId}\n`)

  // Start the task (if not already started)
  const _startResult = sh(`td start ${taskId} 2>/dev/null || true`, repoRoot)
  green(`Linked task: ${taskId}`)

  // Also write a summary comment
  sh(`td comment ${taskId} "Worktree created: ${worktreeName}" 2>/dev/null || true`, repoRoot)
}

// Also write .git to mark this as a worktree (for other tools)
const gitMarkerPath = join(worktreePath, ".is-worktree")
writeFileSync(gitMarkerPath, `${new Date().toISOString()}\n`)

// Verify td can resolve the shared database
console.log("")
yellow("Verifying td resolution...")

const _verifyResult = sh(`td -w "${repoRoot}" whoami 2>/dev/null || td whoami`, worktreePath)

// Show result
console.log("")
console.log("\x1b[36m═══════════════════════════════════════════\x1b[0m")
console.log("\x1b[36m  WORKTREE CREATED\x1b[0m")
console.log("\x1b[36m═══════════════════════════════════════════\x1b[0m")
console.log("")
console.log(`  Path:     ${worktreePath}`)
console.log(`  Branch:   ${branchName}`)
console.log(`  TD root:  ${repoRoot}`)
if (taskId) console.log(`  Task:     ${taskId}`)
console.log("")
console.log(`  \x1b[32m✓\x1b[0m  Shared .todos/ database at: ${repoRoot}/.todos/`)
console.log("")
console.log("\x1b[33mNext steps:\x1b[0m")
console.log("")
console.log(`  cd ${worktreePath}`)
console.log(`  td usage --new-session`)
console.log("")
console.log(`  # Or use the shortcut in Justfile:`)
console.log(`  # just agent-orient  (already configured)`)
console.log("")
console.log(`  # To delete later:`)
console.log(`  bun scripts/worktree-init.ts ${safeName} --delete`)
console.log("")
console.log("\x1b[36m═══════════════════════════════════════════\x1b[0m")
