#!/usr/bin/env bun
/**
 * Backup SQLite database.
 *
 * Delegates to scripts/db-backup.ts
 * Usage: trading backup [--test]
 */

import { defineCommand } from "citty"

export const backupCommand = defineCommand({
  meta: { name: "backup", description: "Backup SQLite database" },
  args: {
    test: {
      type: "boolean",
      description: "Backup test database (test_portfolio.db)",
      default: false,
    },
  },
  run: async ({ args }) => {
    const flags: string[] = []
    if (args.test) flags.push("--test")

    const proc = Bun.spawn(["bun", "scripts/db-backup.ts", ...flags], {
      stdout: "inherit",
      stderr: "inherit",
    })

    const exitCode = await proc.exited
    if (exitCode !== 0) {
      process.exit(exitCode)
    }
  },
})
