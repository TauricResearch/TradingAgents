#!/usr/bin/env bun

/**
 * Agent Coordination — Orientation.
 *
 * Full session startup: git state + td session + what's in flight.
 * Run this at the start of every new agent session.
 *
 * Usage:
 *   bun scripts/agent-orient.ts            # full report
 *   bun scripts/agent-orient.ts --compact  # one-line summary
 *   bun scripts/agent-orient.ts --next      # what to work on next
 */

import { execSync } from "node:child_process"
import { mkdirSync } from "node:fs"
import { join } from "node:path"

const mode = Bun.argv.includes("--compact")
  ? "compact"
  : Bun.argv.includes("--next")
    ? "next"
    : "full"

function sh(cmd: string): string {
  try {
    return execSync(cmd, { encoding: "utf8", timeout: 5000 }).trim()
  } catch {
    return "(unavailable)"
  }
}

function section(label: string, content: string, color = "CYAN") {
  const fmt: Record<string, string> = {
    CYAN: "\x1b[36m",
    GREEN: "\x1b[32m",
    YELLOW: "\x1b[33m",
    RED: "\x1b[31m",
    RESET: "\x1b[0m",
  }
  return `${fmt[color]}${label}${fmt.RESET}\n${content}`
}

// ── Git state ───────────────────────────────────────────────────────────

function gitState() {
  const branch = sh("git branch -v 2>/dev/null | grep '^\\*'").replace(/^\* /, "").trim()
  const status = sh("git status --short 2>/dev/null")
  const behind = parseInt(sh("git rev-list --count HEAD..origin/main 2>/dev/null") || "0", 10)

  if (mode === "compact") {
    return `${branch} | behind main: ${behind} | changes: ${status ? "YES" : "none"}`
  }

  return [
    `  Branch:    ${branch}`,
    `  Behind:    ${behind} commits`,
    `  Changes:   ${status || "(none)"}`,
  ].join("\n")
}

// ── TD session state ──────────────────────────────────────────────────────

function tdState() {
  if (mode === "compact") {
    const session = sh("td whoami 2>/dev/null | grep session | awk '{print $NF}'").trim()
    const ws = sh("td ws current 2>/dev/null").split("\n")[0] || "(no workspace)"
    const mine =
      sh("td list --status in_progress 2>/dev/null | grep -c 'in_progress'").trim() || "0"
    return `session: ${session || "?"} | workspace: ${ws} | my tasks: ${mine}`
  }

  const usage = sh("td usage 2>/dev/null").split("\n").slice(0, 25).join("\n")
  const ws = sh("td ws current 2>/dev/null")
  return [usage, "", ws].join("\n")
}

// ── What's in flight ──────────────────────────────────────────────────────

function tdInFlight() {
  const list = sh("td list 2>/dev/null")
  const reviewable = sh("td reviewable 2>/dev/null").split("\n").slice(0, 10).join("\n")

  if (mode === "compact") {
    const inProg = (list.match(/in_progress/g) || []).length
    const inReview = (list.match(/in_review/g) || []).length
    return `in_progress: ${inProg} | in_review: ${inReview} | reviewable: ${reviewable ? "YES" : "none"}`
  }

  return [list, "", reviewable ? `Reviewable:\n${reviewable}` : ""].join("\n")
}

// ── Recommended next action ───────────────────────────────────────────────

function tdNext() {
  const next = sh("td next 2>/dev/null").split("\n").slice(0, 15).join("\n")
  const ready = sh("td ready 2>/dev/null").split("\n").slice(0, 10).join("\n")
  return `Next:\n${next}\n\nReady:\n${ready}`
}

// ── File collisions ───────────────────────────────────────────────────────

function fileCollisions() {
  // Find all in_progress tasks and check for file conflicts
  const list = sh("td list --status in_progress 2>/dev/null")
  const taskIds = [...list.matchAll(/td-([a-f0-9]+)/g)].map((m) => m[0])

  if (taskIds.length === 0) return "  No in-progress tasks."

  const claimedFiles = new Map<string, string[]>()
  for (const id of taskIds) {
    const files = sh(`td files ${id} 2>/dev/null`)
      .split("\n")
      .filter((f) => f.trim() && !f.includes("No files"))
    if (files.length > 0) {
      for (const f of files) {
        if (!claimedFiles.has(f)) claimedFiles.set(f, [])
        claimedFiles.get(f)?.push(id)
      }
    }
  }

  const collisions = [...claimedFiles.entries()].filter(([, ids]) => ids.length > 1)
  if (collisions.length === 0) return "  No file collisions detected."

  return collisions.map(([file, ids]) => `  ⚠ ${file}: claimed by ${ids.join(", ")}`).join("\n")
}

// ── Open PRs ─────────────────────────────────────────────────────────────

const REVIEWS_DIR = join(process.cwd(), "debriefs", "reviews")

/** Write a note file to debriefs/reviews/ — used when we can't determine state. */
function writeReviewNote(filename: string, message: string) {
  try {
    mkdirSync(REVIEWS_DIR, { recursive: true })
    const notePath = join(REVIEWS_DIR, filename)
    const ts = new Date().toISOString().replace(/T/, " ").slice(0, 19)
    execSync(
      `cat > "${notePath}" << 'NOTE'
# ${filename.replace(/\.md$/, "")}

**Fetched:** ${ts}
**State:** UNKNOWN — ${message}

NOTE`,
      { shell: "/bin/bash", timeout: 5000 },
    )
  } catch {}
}

function openPRs() {
  if (mode === "compact") {
    const raw = sh("gh pr list --state open --json number,title --jq .[] 2>/dev/null")
    if (!raw) return "PRs: none"
    try {
      const prs = JSON.parse(raw || "[]") as { number: number; title: string }[]
      return prs.length ? `PRs: ${prs.map((p) => `#${p.number}`).join(", ")}` : "PRs: none"
    } catch {
      return "PRs: gh parse error"
    }
  }

  // Try to get open PRs from GitHub
  const raw = sh("gh pr list --state open --json number,title,url --jq .[] 2>/dev/null")
  if (!raw) {
    writeReviewNote(
      "pr-state-unknown.md",
      "gh pr list returned no output (unauthenticated or network error).",
    )
    return "  PR state unknown (gh unavailable). Note written to debriefs/reviews/pr-state-unknown.md"
  }

  let prs: { number: number; title: string; url: string }[]
  try {
    prs = JSON.parse(raw)
  } catch {
    writeReviewNote("pr-state-unknown.md", "gh pr list output could not be parsed as JSON.")
    return "  PR state unknown (parse error). Note written to debriefs/reviews/pr-state-unknown.md"
  }

  if (prs.length === 0) return "  No open PRs."

  // Ensure directory exists
  try {
    mkdirSync(REVIEWS_DIR, { recursive: true })
  } catch {}

  // Clean up stale PR docs — PRs that are no longer open
  const openNumbers = new Set(prs.map((p) => p.number))
  try {
    const existing = execSync(`ls "${REVIEWS_DIR}"/pr-*.md 2>/dev/null`, {
      encoding: "utf8",
      shell: "/bin/bash",
    })
      .split("\n")
      .filter((f) => f.trim() && !f.includes("pr-state-unknown"))
    let cleaned = 0
    for (const f of existing) {
      const base = f.replace(/^.*\//, "")
      const numMatch = base.match(/^pr-(\d+)-/)
      if (numMatch && !openNumbers.has(parseInt(numMatch[1], 10))) {
        execSync(`rm "${REVIEWS_DIR}/${base}" 2>/dev/null`, { timeout: 5000 })
        cleaned++
      }
    }
    if (cleaned > 0) console.log(`  (cleaned ${cleaned} stale PR doc(s))\n`)
  } catch {}

  // Fetch each open PR
  let fetched = 0
  for (const pr of prs) {
    const slug = pr.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60)
    const dest = join(REVIEWS_DIR, `pr-${pr.number}-${slug}.md`)
    try {
      execSync(`defuddle parse -o "${dest}" --md "${pr.url}" 2>/dev/null`, {
        timeout: 30_000,
      })
      fetched++
    } catch {
      // defuddle failed — fall back to gh for basic metadata
      try {
        const ghData = sh(
          `gh pr view ${pr.number} --json title,body,state,author,createdAt,url --jq . 2>/dev/null`,
        )
        if (ghData) {
          const gh = JSON.parse(ghData)
          const md = `# PR #${gh.number}: ${gh.title}\n\n**State:** ${gh.state}\n**Author:** ${gh.author?.login ?? "unknown"}\n**Created:** ${gh.createdAt}\n\n${gh.body ?? ""}`
          execSync(`cat > "${dest}" << 'GHMD'\n${md}\nGHMD`, { shell: "/bin/bash" })
          fetched++
        }
      } catch {}
    }
  }

  return [
    `  ${prs.length} open PR(s):`,
    ...prs.map((p) => `    #${p.number}: ${p.title}`),
    "",
    `  Reviews cached to debriefs/reviews/pr-{num}.md (${fetched}/${prs.length} fetched)`,
  ].join("\n")
}

// ── Main branch gate ───────────────────────────────────────────────────

/**
 * Gate: abort if on main with active work or uncommitted changes.
 * This prevents accidental work on main — always branch first.
 */
function checkMainGate() {
  const branch = sh("git branch -v 2>/dev/null | grep '^\\*' | awk '{print $2}'")
  if (branch !== "main") return // only gate on main

  const status = sh("git status --short 2>/dev/null")
  const hasChanges = status.trim().length > 0

  const wsRaw = sh("td ws current 2>/dev/null")
  const hasWorkspace = wsRaw.includes("Work Session:") && !wsRaw.includes("no active work session")

  if (!hasChanges && !hasWorkspace) return // clean on main — no gate needed

  console.error("\n\x1b[31m✗ BLOCKED: on main with active work\x1b[0m\n")
  console.error("  Reason(s):")
  if (hasChanges) console.error(`  - uncommitted changes:\n${status.replace(/^/gm, "    ")}`)
  if (hasWorkspace) {
    const lines = wsRaw.split("\n").slice(0, 3).join("\n")
    console.error(`  - active work session:\n${lines.replace(/^/gm, "    ")}`)
  }
  console.error("\n  → Create a branch first:  git checkout -b feat/<name>\n")
  process.exit(1)
}

// ── Output ────────────────────────────────────────────────────────────────

checkMainGate()

console.log("")
console.log("\x1b[36m═══════════════════════════════════\x1b[0m")
console.log("\x1b[36m  AGENT ORIENTATION\x1b[0m")
console.log("\x1b═══════════════════════════════════\x1b[0m")
console.log("")

console.log(section("Git:", gitState()))
console.log("")
console.log(section("Open PRs:", openPRs()))
console.log("")
console.log(section("Session:", tdState()))
console.log("")

if (mode === "next") {
  console.log(section("Recommended next:", tdNext()))
} else {
  console.log(section("In flight:", tdInFlight()))
  console.log("")
  console.log(section("File collisions:", fileCollisions()))
  console.log("")
  console.log(
    "\x1b[33mHint:\x1b[0m Run `bun scripts/agent-orient.ts --next` to see recommended tasks.",
  )
}

console.log("")
