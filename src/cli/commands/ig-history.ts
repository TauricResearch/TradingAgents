#!/usr/bin/env bun
/**
 * IG activity and transaction history.
 *
 * Usage:
 *   trading ig history           # last 7 days activity
 *   trading ig history --transactions  # last 7 days transactions
 *   trading ig history --from 2026-05-01 --to 2026-05-08
 *   trading ig history --transactions --from 2026-05-01 --type TRADE
 */

import { defineCommand } from "citty"
import { gum } from "../../../scripts/lib/gum.ts"
import { IGClient } from "../../lib/ig-client.ts"

function getClient(): IGClient {
  const apiKey = process.env.IG_DEMO_API_KEY
  const username = process.env.IG_DEMO_USERNAME
  const password = process.env.IG_DEMO_PASSWORD
  if (!apiKey || !username || !password) {
    console.error("Missing IG credentials. Set IG_DEMO_API_KEY, IG_DEMO_USERNAME, IG_DEMO_PASSWORD")
    process.exit(1)
  }
  return new IGClient({
    apiKey,
    username,
    password,
    baseUrl: "https://demo-api.ig.com/gateway/deal",
  })
}

function fmtDate(iso: string): string {
  return iso.slice(0, 10)
}

function fmtGBP(n: number): string {
  const sign = n < 0 ? "-" : ""
  return `${sign}£${Math.abs(n).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function defaultDateRange(): { from: string; to: string } {
  const to = new Date()
  const from = new Date()
  from.setDate(to.getDate() - 7)
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  }
}

export const igHistoryCommand = defineCommand({
  meta: {
    name: "history",
    description: "IG activity and transaction history",
  },
  args: {
    transactions: {
      type: "boolean",
      description: "Show transaction history instead of activity",
      default: false,
    },
    from: {
      type: "string",
      description: "From date (YYYY-MM-DD)",
    },
    to: {
      type: "string",
      description: "To date (YYYY-MM-DD)",
    },
    type: {
      type: "string",
      description: "Transaction type filter (ALL, WITHDRAWAL, DEPOSIT, TRADE)",
      default: "ALL",
    },
    detailed: {
      type: "boolean",
      description: "Include full deal details in activity",
      default: false,
    },
  },
  run: async ({ args }) => {
    const client = getClient()
    await client.login()

    const range = defaultDateRange()
    const from = args.from ?? range.from
    const to = args.to ?? range.to

    if (args.transactions) {
      // ── Transaction history ─────────────────────────────────────────────
      const result = await client.getTransactionHistory({
        from,
        to,
        type: args.type,
      })

      const transactions = result.transactions ?? []

      if (transactions.length === 0) {
        console.log("No transactions found for the selected period.")
        return
      }

      const lines = [
        `${"Date".padEnd(12)} ${"Type".padEnd(12)} ${"Amount".padStart(14)} ${"Balance".padStart(14)} ${"Reference".padEnd(16)}`,
        "─".repeat(12 + 12 + 14 + 14 + 16 + 4),
      ]

      for (const t of transactions) {
        const amountColour = t.amount >= 0 ? "\x1b[32m" : "\x1b[31m"
        const reset = "\x1b[0m"
        lines.push(
          `${fmtDate(t.date).padEnd(12)} ${t.type.padEnd(12)} ${amountColour}${fmtGBP(t.amount).padStart(14)}${reset} ${fmtGBP(t.balance).padStart(14)} ${t.reference.padEnd(16)}`,
        )
      }

      const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
      const title = await gum("IG Transaction History", ["--bold", "--foreground", "212"])

      console.log("")
      console.log(`  ${title}`)
      console.log(box)
      console.log(`  \x1b[90mPeriod: ${from} → ${to}  ·  Type: ${args.type}\x1b[0m`)
      console.log("")
    } else {
      // ── Activity history ────────────────────────────────────────────────
      const result = await client.getActivityHistory({
        from,
        to,
        detailed: args.detailed,
      })

      const activities = result.activities ?? []

      if (activities.length === 0) {
        console.log("No activity found for the selected period.")
        return
      }

      const maxName = Math.max(10, ...activities.map((a) => a.details?.marketName?.length ?? 0))

      const lines = [
        `${"Date".padEnd(12)} ${"Type".padEnd(14)} ${"Dir".padEnd(4)} ${"Size".padStart(6)} ${"Level".padStart(10)} ${"Market".padEnd(maxName + 2)} ${"Status".padEnd(10)}`,
        "─".repeat(12 + 14 + 4 + 6 + 10 + maxName + 2 + 10 + 6),
      ]

      for (const a of activities) {
        const d = fmtDate(a.date)
        const statusColour = a.status === "ACCEPTED" ? "\x1b[32m" : "\x1b[31m"
        const reset = "\x1b[0m"
        const dir = a.details?.direction ?? "—"
        const size = a.details?.size ?? "—"
        const level = a.details?.level ?? "—"
        const name = a.details?.marketName ?? "—"

        lines.push(
          `${d.padEnd(12)} ${a.type.padEnd(14)} ${dir.padEnd(4)} ${String(size).padStart(6)} ${String(level).padStart(10)} ${name.padEnd(maxName + 2)} ${statusColour}${a.status.padEnd(10)}${reset}`,
        )
      }

      const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
      const title = await gum("IG Activity History", ["--bold", "--foreground", "212"])

      console.log("")
      console.log(`  ${title}`)
      console.log(box)
      console.log(`  \x1b[90mPeriod: ${from} → ${to}${args.detailed ? "  ·  Detailed" : ""}\x1b[0m`)
      console.log("")
    }
  },
})
