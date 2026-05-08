#!/usr/bin/env bun

/**
 * Lab: PID file + log capture lifecycle
 *
 * Tests the robust service management pattern:
 * - PID file tracking (no ps | grep fragility)
 * - Log capture to file
 * - Stale PID cleanup
 * - Port conflict detection
 *
 * Run: bun scripts/lab/pid-file.ts
 */

import { spawn } from "node:child_process"
import { existsSync } from "node:fs"
import { readFile, unlink, writeFile } from "node:fs/promises"

const PID_FILE = "/tmp/lab-server.pid"
const LOG_FILE = "/tmp/lab-server.log"
const PORT = 3999 // test port, not 3000

// ── Helpers ──────────────────────────────────────────────────────

async function isPortFree(port: number): Promise<boolean> {
  try {
    const proc = Bun.spawn({
      cmd: ["lsof", "-i", `:${port}`],
      stdout: "pipe",
      stderr: "pipe",
    })
    const out = await new Response(proc.stdout).text()
    return out.trim().length === 0
  } catch {
    return true
  }
}

async function readPid(): Promise<number | null> {
  try {
    const text = await readFile(PID_FILE, "utf-8")
    const pid = parseInt(text.trim(), 10)
    return isNaN(pid) ? null : pid
  } catch {
    return null
  }
}

async function isProcessAlive(pid: number): Promise<boolean> {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

async function cleanupStalePid(): Promise<void> {
  const pid = await readPid()
  if (pid && !(await isProcessAlive(pid))) {
    console.log(`  Stale PID ${pid} found, cleaning up...`)
    await unlink(PID_FILE).catch(() => {})
  }
}

// ── Experiment 1: port check ─────────────────────────────────────
console.log("Experiment 1: Port check")
const free = await isPortFree(PORT)
console.log(`  Port ${PORT} free: ${free}`)

// ── Experiment 2: start a dummy server, write PID ───────────────
console.log("\nExperiment 2: Start dummy server")
await cleanupStalePid()

if (!(await isPortFree(PORT))) {
  console.log("  Port occupied, skipping start")
} else {
  const child = spawn("python3", ["-m", "http.server", String(PORT)], {
    detached: true,
    stdio: ["ignore", "pipe", "pipe"],
  })

  // Write PID file
  await writeFile(PID_FILE, String(child.pid))
  console.log(`  Started dummy server (PID ${child.pid})`)
  console.log(`  PID written to ${PID_FILE}`)

  // Redirect stdout/stderr to log
  if (child.stdout) {
    const log = Bun.file(LOG_FILE).writer()
    child.stdout.on("data", (d: Buffer) => log.write(d))
    child.stderr?.on("data", (d: Buffer) => log.write(d))
  }

  // Wait for server to be ready
  await new Promise((r) => setTimeout(r, 1000))

  // ── Experiment 3: verify PID file works ────────────────────────
  console.log("\nExperiment 3: Read back PID")
  const savedPid = await readPid()
  console.log(`  Saved PID: ${savedPid}`)
  console.log(`  Process alive: ${savedPid ? await isProcessAlive(savedPid) : false}`)

  // ── Experiment 4: status check ────────────────────────────────
  console.log("\nExperiment 4: Status check")
  const portFree = await isPortFree(PORT)
  console.log(`  Port ${PORT} free: ${portFree} (expect false)`)

  // ── Experiment 5: stop via PID file ───────────────────────────
  console.log("\nExperiment 5: Stop via PID file")
  if (savedPid && (await isProcessAlive(savedPid))) {
    process.kill(savedPid, "SIGTERM")
    console.log(`  Sent SIGTERM to ${savedPid}`)

    // Wait for stop
    for (let i = 0; i < 10; i++) {
      await new Promise((r) => setTimeout(r, 500))
      if (!(await isProcessAlive(savedPid))) {
        console.log("  Process stopped")
        break
      }
    }

    if (await isProcessAlive(savedPid)) {
      console.log("  Forcing SIGKILL...")
      process.kill(savedPid, "SIGKILL")
    }
  }

  // Remove PID file
  await unlink(PID_FILE).catch(() => {})
  console.log("  PID file removed")
}

// ── Experiment 6: verify cleanup ─────────────────────────────────
console.log("\nExperiment 6: Verify cleanup")
console.log(`  Port ${PORT} free: ${await isPortFree(PORT)} (expect true)`)
console.log(`  PID file exists: ${existsSync(PID_FILE)} (expect false)`)

console.log("\n✓ All experiments complete")
