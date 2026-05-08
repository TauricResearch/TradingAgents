#!/usr/bin/env bun
/**
 * Lab: Improved status table layout
 *
 * Rename "Details" → "Action" with short verbs.
 * Wider box to prevent wrapping.
 *
 * Run: bun scripts/lab/status-layout.ts
 */

import { gum } from "../lib/gum.ts"

interface ServiceRow {
  name: string
  status: "running" | "stopped" | "unknown"
  pid: string
  port: string
  action: string
}

const rows: ServiceRow[] = [
  { name: "Dashboard Server", status: "running", pid: "49039", port: "3000", action: "serve" },
  { name: "SQLite (LIVE)", status: "running", pid: "—", port: "—", action: "persist" },
  { name: "GitNexus Index", status: "running", pid: "—", port: "—", action: "index" },
]

// ── Experiment 1: compact table ──────────────────────────────────
const tableLines = [
  "Service            Status     PID     Port  Action",
  "───────────────────────────────────────────────────",
  ...rows.map((r) => {
    const dot = r.status === "running" ? "●" : r.status === "stopped" ? "●" : "●"
    return `${r.name.padEnd(18)} ${dot} ${r.status.padEnd(8)} ${r.pid.padStart(6)} ${r.port.padStart(5)}  ${r.action}`
  }),
].join("\n")

console.log(
  await gum("TradingAgents", [
    "--bold",
    "--foreground",
    "212",
    "--width",
    "64",
    "--align",
    "center",
  ]),
)
console.log(await gum(tableLines, ["--border", "rounded", "--padding", "1 2", "--width", "64"]))

// ── Experiment 2: with colour-coded status dots ──────────────────
// (gum does not support inline colour, so we use separate calls)
console.log(await gum("  ✓ Dashboard responding on http://localhost:3000", ["--foreground", "2"]))
console.log("")
