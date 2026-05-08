#!/usr/bin/env bun

/**
 * Database backup utility.
 *
 * Creates a timestamped copy of the SQLite database file.
 * Uses SQLite's online backup API for consistency (reads while app writes).
 *
 * Usage:
 *   bun scripts/db-backup.ts              # backup portfolio.db
 *   bun scripts/db-backup.ts --test     # backup test_portfolio.db
 *   bun scripts/db-backup.ts --list     # list existing backups
 *   bun scripts/db-backup.ts --prune 7  # keep only last 7 days
 */

import { existsSync, mkdirSync, readdirSync, statSync, unlinkSync } from "node:fs"
import { join } from "node:path"
import { DatabaseFactory } from "../src/lib/db.ts"

const BACKUP_DIR = join(process.cwd(), "backups")

function resolveDbPath(isTest: boolean): string {
  if (isTest) {
    return process.env.TEST_PORTFOLIO_DB ?? "./test_portfolio.db"
  }
  return process.env.PORTFOLIO_DB ?? "./portfolio.db"
}

function ensureBackupDir(): void {
  if (!existsSync(BACKUP_DIR)) {
    mkdirSync(BACKUP_DIR, { recursive: true })
  }
}

function backupFileName(dbPath: string): string {
  const base = dbPath.replace(/^\.\//, "").replace(/\.db$/, "")
  const ts = new Date().toISOString().replace(/[:T]/g, "-").slice(0, 19)
  return `${base}-${ts}.db`
}

function backup(dbPath: string): string {
  ensureBackupDir()
  const outPath = join(BACKUP_DIR, backupFileName(dbPath))

  // Use DatabaseFactory for consistent connection params, then VACUUM INTO
  const source = DatabaseFactory.connect(dbPath)
  try {
    const safePath = outPath.replace(/'/g, "''")
    source.run(`VACUUM INTO '${safePath}'`)
  } finally {
    DatabaseFactory.close()
  }

  const size = statSync(outPath).size
  console.log(`✅ Backed up: ${dbPath} → ${outPath} (${(size / 1024 / 1024).toFixed(2)} MB)`)
  return outPath
}

function listBackups(): void {
  if (!existsSync(BACKUP_DIR)) {
    console.log("No backups found.")
    return
  }

  const files = readdirSync(BACKUP_DIR)
    .filter((f) => f.endsWith(".db"))
    .sort()

  if (files.length === 0) {
    console.log("No backups found.")
    return
  }

  console.log("Available backups:")
  for (const file of files) {
    const path = join(BACKUP_DIR, file)
    const stat = statSync(path)
    const sizeMB = (stat.size / 1024 / 1024).toFixed(2)
    const date = stat.mtime.toISOString().slice(0, 19)
    console.log(`  ${file} (${sizeMB} MB) — ${date}`)
  }
}

function prune(days: number): void {
  if (!existsSync(BACKUP_DIR)) return

  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000
  let removed = 0

  for (const file of readdirSync(BACKUP_DIR)) {
    if (!file.endsWith(".db")) continue
    const path = join(BACKUP_DIR, file)
    const mtime = statSync(path).mtime.getTime()
    if (mtime < cutoff) {
      unlinkSync(path)
      removed++
    }
  }

  console.log(`🗑️  Pruned ${removed} backup(s) older than ${days} days`)
}

// ── Main ────────────────────────────────────────────────────────────────────

const args = Bun.argv.slice(2)
const isTest = args.includes("--test")
const isList = args.includes("--list")
const pruneIdx = args.indexOf("--prune")

if (isList) {
  listBackups()
} else if (pruneIdx !== -1 && args[pruneIdx + 1]) {
  const days = parseInt(args[pruneIdx + 1], 10)
  if (!Number.isFinite(days) || days < 0) {
    console.error(`❌ Invalid --prune value: ${args[pruneIdx + 1]} (expected non-negative integer)`)
    process.exit(1)
  }
  prune(days)
} else {
  const dbPath = resolveDbPath(isTest)
  if (!existsSync(dbPath)) {
    console.error(`❌ Database not found: ${dbPath}`)
    process.exit(1)
  }
  backup(dbPath)
}
