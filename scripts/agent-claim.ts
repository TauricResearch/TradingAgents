#!/usr/bin/env bun
/**
 * Agent Coordination — Task Claim.
 *
 * Claim a task before touching any files.
 * - Verifies it's not already claimed by another session
 * - Runs td start
 * - Labels with session ID
 * - Links git files
 *
 * Usage:
 *   bun scripts/agent-claim.ts td-abc123
 *   bun scripts/agent-claim.ts td-abc123 --force   # bypass claim check
 */

const taskId = Bun.argv[2]
if (!taskId) {
  console.error("Usage: bun scripts/agent-claim.ts <task-id> [--force]")
  process.exit(1)
}

const force = Bun.argv.includes("--force")

function sh(cmd: string): { ok: boolean; out: string } {
  try {
    return { ok: true, out: execSync(cmd, { encoding: "utf8", timeout: 10000 }).trim() }
  } catch (e: unknown) {
    return { ok: false, out: (e as Error).message }
  }
}

function green(msg: string) {
  console.log(`\x1b[32m✓\x1b[0m ${msg}`)
}
function red(msg: string) {
  console.error(`\x1b[31m✗\x1b[0m ${msg}`)
}
function yellow(msg: string) {
  console.log(`\x1b[33m⚠\x1b[0m ${msg}`)
}

// ── Get current session ID ───────────────────────────────────────────────

const whoami = sh("td whoami 2>/dev/null")
const sessionLine = whoami.out.split("\n").find((l) => l.includes("session")) || ""
const sessionId =
  sessionLine.match(/(\w+-\w{6})/)?.[1] || whoami.out.match(/(\w+-\w{6})/)?.[1] || "unknown"

// ── Check existing claims ─────────────────────────────────────────────────

if (!force) {
  const show = sh(`td show ${taskId} 2>/dev/null`)
  const claimedBy = show.out.match(/claimed-by:(\S+)/)?.[1]
  const otherClaimed = show.out.match(/claimed-by:(\S+)/g)?.filter((m) => !m.includes(sessionId))

  if (claimedBy && claimedBy !== sessionId && otherClaimed && otherClaimed.length > 0) {
    red(`Task ${taskId} already claimed by: ${claimedBy}`)
    console.error("")
    console.error("  To request handover, run:")
    console.error(`    td comment ${taskId} "@${claimedBy}: requesting handover for ${taskId}"`)
    console.error("")
    console.error("  Or use --force to claim anyway:")
    console.error(`    bun scripts/agent-claim.ts ${taskId} --force`)
    process.exit(1)
  }
}

// ── Perform claim ─────────────────────────────────────────────────────────

console.log(`\x1b[36mClaiming ${taskId} (session: ${sessionId})...\x1b[0m`)

// td start
const start = sh(`td start ${taskId}`)
if (!start.ok) {
  yellow(`td start failed (task may already be in_progress): ${start.out}`)
} else {
  green(`Started: ${taskId}`)
}

// Add claimed-by label
const label = sh(`td update ${taskId} --labels "claimed-by:${sessionId}"`)
if (label.ok) {
  green(`Labeled: claimed-by:${sessionId}`)
} else {
  yellow(`Label update: ${label.out}`)
}

// Link git files
const link = sh(`td link ${taskId} --git 2>/dev/null`)
if (link.ok && link.out.trim()) {
  green(`Linked files:\n  ${link.out.split("\n").join("\n  ")}`)
} else {
  yellow(`No files linked (run manually: td link ${taskId} --git)`)
}

// Show what to do next
console.log("")
console.log(`\x1b[36m✓ Claimed ${taskId}\x1b[0m`)
console.log("")
console.log("  Next: check files you own")
console.log(`    bun scripts/agent-files.ts ${taskId}`)
console.log("")
console.log("  Log progress")
console.log(`    bun scripts/agent-log.ts ${taskId} "started work"`)
console.log("")
