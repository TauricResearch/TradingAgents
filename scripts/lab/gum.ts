#!/usr/bin/env bun
/**
 * Lab: Gum-style CLI output
 *
 * Safe playground for testing Charm Gum formatting.
 * Uses scripts/lib/gum.ts (shared helper, not inline).
 *
 * Run: bun scripts/lab/gum.ts
 */

import { gum } from "../lib/gum.ts"

// ── Experiment 1: header ─────────────────────────────────────────
console.log(
  await gum("TradingAgents", [
    "--bold",
    "--foreground",
    "212",
    "--width",
    "56",
    "--align",
    "center",
  ]),
)

// ── Experiment 2: multi-line bordered table ──────────────────────
const table = [
  "Service            Status     PID     Port  Details",
  "───────────────────────────────────────────────────",
  "Dashboard Server   ● running   49039  3000  bun run src/server/index.tsx",
  "SQLite (LIVE)      ● running       —     —  Database: ./portfolio.db",
  "GitNexus Index     ● running       —     —  Indexed: TradingAgents",
].join("\n")

console.log(await gum(table, ["--border", "rounded", "--padding", "1 2", "--width", "56"]))

// ── Experiment 3: status footer ──────────────────────────────────
console.log(await gum("  ✓ Dashboard responding on http://localhost:3000", ["--foreground", "2"]))
console.log("")
