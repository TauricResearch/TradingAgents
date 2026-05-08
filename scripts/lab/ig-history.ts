#!/usr/bin/env bun
/**
 * Lab: IG history API client extension + CLI display
 *
 * Structures the code pattern without requiring IG API credentials.
 * Uses mock data to validate display format.
 *
 * Run: bun scripts/lab/ig-history.ts
 */

import { gum } from "../lib/gum.ts"

// ── Mock IG API response types ───────────────────────────────────────────

interface IGActivity {
  date: string
  channel: string // "DEAL" | "SYSTEM" | etc
  type: string // "POSITION" | "WORKING_ORDER" | etc
  status: string // "ACCEPTED" | "REJECTED" | etc
  description: string
  details: {
    marketName: string
    period: string
    epic: string
    expiry: string
    dealReference: string
    direction: "BUY" | "SELL"
    size: string
    level: string
    currency: string
    stopLevel?: string
    limitLevel?: string
  }
}

interface IGTransaction {
  date: string
  type: string // "WITHDRAWAL" | "DEPOSIT" | "TRADE" etc
  amount: number
  balance: number
  reference: string
  description: string
}

// ── Mock data ──────────────────────────────────────────────────────────────

const mockActivities: IGActivity[] = [
  {
    date: "2026-05-07T14:32:15",
    channel: "DEAL",
    type: "POSITION",
    status: "ACCEPTED",
    description: "Position opened: TKA.DE",
    details: {
      marketName: "Thyssenkrupp AG",
      period: "DFB",
      epic: "UA.D.TKAG.DEUR.CALL.IP",
      expiry: "DFB",
      dealReference: "DIAAAABBBCCC",
      direction: "BUY",
      size: "115",
      level: "10.76",
      currency: "EUR",
    },
  },
  {
    date: "2026-05-06T09:15:00",
    channel: "DEAL",
    type: "POSITION",
    status: "ACCEPTED",
    description: "Position opened: TKMS.DE",
    details: {
      marketName: "Thyssenkrupp Marine",
      period: "DFB",
      epic: "UA.D.TKMS.DEUR.CALL.IP",
      expiry: "DFB",
      dealReference: "DIAAAABBBDDD",
      direction: "BUY",
      size: "5",
      level: "76.90",
      currency: "EUR",
    },
  },
  {
    date: "2026-05-05T11:00:00",
    channel: "DEAL",
    type: "WORKING_ORDER",
    status: "ACCEPTED",
    description: "Working order placed: AAPL",
    details: {
      marketName: "Apple Inc",
      period: "DFB",
      epic: "UA.D.AAPL.CASH.IP",
      expiry: "DFB",
      dealReference: "DIAAAABBBEEE",
      direction: "BUY",
      size: "50",
      level: "195.42",
      currency: "USD",
      stopLevel: "185.00",
      limitLevel: "210.00",
    },
  },
]

const mockTransactions: IGTransaction[] = [
  {
    date: "2026-05-07",
    type: "TRADE",
    amount: -994.07,
    balance: 8506.93,
    reference: "DIAAAABBBCCC",
    description: "Buy 115 TKA.DE @ 10.76 EUR",
  },
  {
    date: "2026-05-06",
    type: "TRADE",
    amount: -384.5,
    balance: 9501.43,
    reference: "DIAAAABBBDDD",
    description: "Buy 5 TKMS.DE @ 76.90 EUR",
  },
  {
    date: "2026-05-01",
    type: "DEPOSIT",
    amount: 10000.0,
    balance: 9885.93,
    reference: "DEP-001",
    description: "Initial deposit",
  },
]

// ── Display helpers ────────────────────────────────────────────────────────

function fmtGBP(n: number): string {
  const sign = n < 0 ? "-" : ""
  return `${sign}£${Math.abs(n).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtDate(iso: string): string {
  const d = new Date(iso)
  return d.toISOString().slice(0, 10)
}

// ── Experiment 1: Activity table ───────────────────────────────────────────

async function activityTable(activities: IGActivity[]) {
  const maxName = Math.max(10, ...activities.map((a) => a.details.marketName.length))

  const lines = [
    `${"Date".padEnd(12)} ${"Type".padEnd(12)} ${"Dir".padEnd(4)} ${"Size".padStart(6)} ${"Level".padStart(10)} ${"Market".padEnd(maxName + 2)} ${"Status".padEnd(10)}`,
    "─".repeat(12 + 12 + 4 + 6 + 10 + maxName + 2 + 10 + 6),
  ]

  for (const a of activities) {
    const d = fmtDate(a.date)
    const statusColour = a.status === "ACCEPTED" ? "\x1b[32m" : "\x1b[31m"
    const reset = "\x1b[0m"
    lines.push(
      `${d.padEnd(12)} ${a.type.padEnd(12)} ${a.details.direction.padEnd(4)} ${String(a.details.size).padStart(6)} ${a.details.level.padStart(10)} ${a.details.marketName.padEnd(maxName + 2)} ${statusColour}${a.status.padEnd(10)}${reset}`,
    )
  }

  const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
  const title = await gum("IG Activity History", ["--bold", "--foreground", "212"])

  console.log("")
  console.log(`  ${title}`)
  console.log(box)
  console.log("")
}

// ── Experiment 2: Transaction table ────────────────────────────────────────

async function transactionTable(transactions: IGTransaction[]) {
  const lines = [
    `${"Date".padEnd(12)} ${"Type".padEnd(12)} ${"Amount".padStart(14)} ${"Balance".padStart(14)} ${"Reference".padEnd(16)}`,
    "─".repeat(12 + 12 + 14 + 14 + 16 + 4),
  ]

  for (const t of transactions) {
    const amountColour = t.amount >= 0 ? "\x1b[32m" : "\x1b[31m"
    const reset = "\x1b[0m"
    lines.push(
      `${t.date.padEnd(12)} ${t.type.padEnd(12)} ${amountColour}${fmtGBP(t.amount).padStart(14)}${reset} ${fmtGBP(t.balance).padStart(14)} ${t.reference.padEnd(16)}`,
    )
  }

  const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
  const title = await gum("IG Transaction History", ["--bold", "--foreground", "212"])

  console.log("")
  console.log(`  ${title}`)
  console.log(box)
  console.log("")
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  console.log("\x1b[2J\x1b[H")
  console.log("═══ Lab: IG History Display ═══")
  console.log("")

  await activityTable(mockActivities)
  await transactionTable(mockTransactions)
}

main()
