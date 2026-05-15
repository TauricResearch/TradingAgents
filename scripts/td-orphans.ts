#!/usr/bin/env bun
/**
 * Agent Coordination — Orphan Detection & Realignment.
 *
 * Finds in_progress tasks whose implementer session is no longer active,
 * then optionally realigns them to the current session.
 *
 * Usage:
 *   bun scripts/td-orphans.ts            # read-only report
 *   bun scripts/td-orphans.ts --realign  # absorb and log
 *   bun scripts/td-orphans.ts --realign --dry-run  # preview only
 */

import { execSync } from "node:child_process"

interface TdIssue {
  id: string
  title: string
  status: string
  type: string
  priority: string
  parent_id: string | null
  implementer_session: string
  creator_session: string
  created_at: string
  updated_at: string
  labels: string[]
  defer_count: number
}

interface CurrentSession {
  id: string
  name: string
}

interface Orphan {
  issue: TdIssue
  reason: string
  action: "absorb" | "reset" | "skip"
}

// ── Argument parsing ───────────────────────────────────────────────────────

const args = Bun.argv.slice(2)
const mode = args.includes("--realign") ? "realign" : "report"
const dryRun = args.includes("--dry-run")

if (args.includes("--help") || args.includes("-h") || (mode === "report" && args.length === 0)) {
  console.log(
    "Usage:\n  bun scripts/td-orphans.ts            # read-only report\n  bun scripts/td-orphans.ts --realign  # absorb and log\n  bun scripts/td-orphans.ts --realign --dry-run  # preview only",
  )
}

// ── Shell helpers ─────────────────────────────────────────────────────────

function sh(cmd: string): string {
  try {
    return execSync(cmd, { encoding: "utf8", timeout: 15000 }).trim()
  } catch {
    return ""
  }
}

function shJson<T>(cmd: string): T[] {
  try {
    const out = execSync(cmd, { encoding: "utf8", timeout: 15000 }).trim()
    if (!out || out === "null" || out === "[]") return []
    return JSON.parse(out) as T[]
  } catch {
    return []
  }
}

// ── Current session ────────────────────────────────────────────────────────

function getCurrentSession(): CurrentSession {
  const out = sh("td whoami 2>/dev/null")
  // Note: session IDs may be "xxxxxx-xxxxxx" or "ses_b7b8a1" (no dash)
  const sessionMatch =
    out.match(/SESSION:\s*([a-z_0-9]{4,12})/i) ||
    out.match(/^([a-z_0-9]{4,12})/i) ||
    out.match(/([a-z_0-9]{8,12})/i)
  const id = sessionMatch ? sessionMatch[1] : "unknown"
  const nameMatch = out.match(/name:\s*(.+)/i)
  const name = nameMatch ? nameMatch[1].trim() : "unknown"
  return { id, name }
}

// ── Active sessions (from td session list) ───────────────────────────────

const ACTIVE_THRESHOLD_HOURS = 1

function parseAgeFromLine(line: string): number | null {
  const match = line.match(/^(?:(\d+)h)?(?:(\d+)m)?(\d+)s$/)
  if (!match) {
    const tsMatch = line.match(/(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})/)
    if (tsMatch) {
      const dt = new Date(tsMatch[1])
      return (Date.now() - dt.getTime()) / (1000 * 60 * 60)
    }
    return null
  }
  const hours = parseInt(match[1], 10) || 0
  const minutes = parseInt(match[2], 10) || 0
  return hours + minutes / 60
}

function getActiveSessions(): string[] {
  const out = sh("td session list 2>/dev/null")
  if (!out) return []

  const activeIds: string[] = []
  const lines = out.split("\n")

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith("BRANCH") || trimmed.startsWith("--")) continue
    if (trimmed.includes("AGENT") || trimmed.includes("SESSION")) continue

    const sessionMatch = trimmed.match(/(\w+-\w{6})/)
    if (!sessionMatch) continue

    const ageHours = parseAgeFromLine(trimmed)
    if (ageHours !== null && ageHours <= ACTIVE_THRESHOLD_HOURS) {
      activeIds.push(sessionMatch[1])
    }
  }

  return activeIds
}

// ── Age helpers ────────────────────────────────────────────────────────────

function ageHours(isoDate: string): number {
  const created = new Date(isoDate)
  const now = new Date()
  return (now.getTime() - created.getTime()) / (1000 * 60 * 60)
}

function ageLabel(isoDate: string): string {
  const h = ageHours(isoDate)
  if (h < 1) return "just now"
  if (h < 24) return `${Math.floor(h)}h ago`
  const d = Math.floor(h / 24)
  if (d === 1) return "1d ago"
  return `${d}d ago`
}

// ── Parent epic resolution ─────────────────────────────────────────────────

function getEpicStatus(epicId: string): string | null {
  const out = sh(`td show ${epicId} 2>/dev/null`)
  const statusMatch = out.match(/Status:\s*(\w+)/)
  return statusMatch ? statusMatch[1] : null
}

// ── Main ───────────────────────────────────────────────────────────────────

const currentSession = getCurrentSession()
const activeSessions = getActiveSessions()

console.log(`\x1b[36m━━ Orphan Check ━━\x1b[0m`)
console.log(`  Current session:  ${currentSession.id} (${currentSession.name})`)
console.log(
  `  Active sessions:  ${activeSessions.length > 0 ? activeSessions.join(", ") : "none detected"}`,
)
console.log("")

const allIssues = shJson<TdIssue>("td list --json --all 2>/dev/null")

const orphans: Orphan[] = []

for (const issue of allIssues) {
  if (issue.status !== "in_progress") continue
  if (issue.implementer_session === currentSession.id) continue

  const isActive = activeSessions.includes(issue.implementer_session)
  const age = ageHours(issue.updated_at)

  let reason = ""
  let action: "absorb" | "reset" | "skip" = "skip"

  if (isActive) {
    reason = `owner session still active`
    action = "skip"
  } else if (age < 1) {
    reason = `age < 1h — still warm`
    action = "skip"
  } else if (issue.parent_id) {
    const epicStatus = getEpicStatus(issue.parent_id)
    if (epicStatus === "closed") {
      reason = `parent epic (${issue.parent_id}) is closed`
      action = "reset"
    } else {
      reason = `owner session inactive, parent epic ${epicStatus ?? "unknown"}`
      action = "absorb"
    }
  } else if (age > 24) {
    reason = `age > 24h, no parent epic`
    action = "reset"
  } else {
    reason = `owner session inactive, no parent epic`
    action = "absorb"
  }

  if (action !== "skip") {
    orphans.push({ issue, reason, action })
  }
}

if (orphans.length === 0) {
  console.log("  \x1b[32m✓\x1b[0m No orphaned work found.")
  console.log("")
  process.exit(0)
}

if (mode === "report") {
  console.log(`\x1b[33m⚠ Found ${orphans.length} orphaned task(s):\x1b[0m`)
  console.log("")
  for (const { issue, reason, action } of orphans) {
    const badge = action === "reset" ? `\x1b[31m[reset]\x1b[0m` : `\x1b[33m[absorb]\x1b[0m`
    const parent = issue.parent_id ? ` ← ${issue.parent_id}` : ""
    const age = ageLabel(issue.updated_at)
    const type = issue.type === "epic" ? "📁" : "  "
    console.log(`  ${type} \x1b[1m${issue.id}\x1b[0m  ${badge}`)
    console.log(`       ${issue.title}`)
    console.log(`       ${reason} · ${age} · impl: ${issue.implementer_session}${parent}`)
    console.log("")
  }
  console.log(
    `Run with \x1b[36m--realign\x1b[0m to absorb them, or \x1b[36m--realign --dry-run\x1b[0m to preview.`,
  )
  console.log("")
  process.exit(0)
}

if (mode === "realign") {
  if (dryRun) {
    console.log(`\x1b[33m⚠ Dry run — would take these actions:\x1b[0m\n`)
    for (const { issue, reason, action } of orphans) {
      const badge = action === "reset" ? `[reset → open]` : `[absorb → current session]`
      console.log(`  ${issue.id} ${badge} — ${reason}`)
    }
    console.log("")
    process.exit(0)
  }

  console.log(`\x1b[36mRealigning ${orphans.length} orphan(s)...\x1b[0m\n`)

  const owner = currentSession.name !== "unknown" ? currentSession.name : undefined

  let absorbed = 0
  let reset = 0

  for (const { issue, reason, action } of orphans) {
    const oldOwner = issue.implementer_session

    if (action === "reset") {
      sh(
        `td edit ${issue.id} --status open -m "Realigned: owner session (${oldOwner}) inactive and parent epic is closed. Reset to open for fresh assessment."`,
      )
      console.log(`  \x1b[31m↺\x1b[0m Reset: ${issue.id} → open (${reason})`)
      reset++
    } else {
      sh(
        `td edit ${issue.id} -m "Realigned from ${oldOwner} → ${currentSession.id} (${currentSession.name}). Reason: ${reason}. Absorbed by current session."`,
      )
      sh(`td log ${issue.id} "🔄 Realigned by ${currentSession.id}: ${reason}"`)

      const labels = issue.labels.filter((l) => !l.startsWith("claimed-by:"))
      labels.push(`claimed-by:${currentSession.id}`)
      sh(`td edit ${issue.id} --labels ${labels.join(",")}`)

      if (owner) {
        sh(`td edit ${issue.id} --labels ${[...labels, `owner:${owner}`].join(",")}`)
      }

      console.log(`  \x1b[32m✓\x1b[0m Absorbed: ${issue.id} (was: ${oldOwner})`)
      absorbed++
    }
  }

  console.log(`\x1b[32m✓\x1b[0m Realignment complete: ${absorbed} absorbed, ${reset} reset.`)
  console.log("")
  process.exit(0)
}
