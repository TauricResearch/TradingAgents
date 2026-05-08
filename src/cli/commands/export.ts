#!/usr/bin/env bun

/**
 * Export portfolio data to JSON or CSV.
 *
 * Usage: trading export <json|csv> [--file path]
 */

import { writeFileSync } from "node:fs"
import { defineCommand } from "citty"
import { DatabaseFactory } from "../../lib/db.ts"
import { cfg } from "../../server/lib/settings.ts"

interface PositionRow {
  ticker: string
  exchange: string
  platform: string
  quantity: number
  avg_cost: number
  entry_date: string
  status: string
}

interface AccountRow {
  id: string
  provider: string
  account_type: string
  name: string
  balance: number
  currency: string
}

function toJSON(data: unknown): string {
  return `${JSON.stringify(data, null, 2)}\n`
}

function toCSV(rows: Record<string, unknown>[]): string {
  if (rows.length === 0) return ""
  const headers = Object.keys(rows[0])
  const lines = [
    headers.join(","),
    ...rows.map((row) =>
      headers
        .map((h) => {
          const val = row[h]
          const str = val == null ? "" : String(val)
          if (str.includes(",") || str.includes('"') || str.includes("\n")) {
            return `"${str.replace(/"/g, '""')}"`
          }
          return str
        })
        .join(","),
    ),
  ]
  return `${lines.join("\n")}\n`
}

export const exportCommand = defineCommand({
  meta: {
    name: "export",
    description: "Export portfolio data to JSON or CSV",
  },
  args: {
    format: {
      type: "positional",
      description: "Export format: json or csv",
      required: true,
    },
    file: {
      type: "string",
      description: "Output file path (default: stdout)",
      alias: "o",
    },
  },
  run: ({ args }) => {
    const format = args.format.toLowerCase()
    if (format !== "json" && format !== "csv") {
      console.error(`❌ Unknown format: ${format}. Use 'json' or 'csv'`)
      process.exit(1)
    }

    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const positions = db
      .query(
        `SELECT ticker, exchange, platform, quantity, avg_cost, entry_date, status
         FROM positions
         WHERE status = 'open'
         ORDER BY platform, ticker`,
      )
      .all() as PositionRow[]

    const accounts = db
      .query(
        `SELECT id, provider, account_type, name, balance, currency
         FROM accounts
         ORDER BY provider, account_type`,
      )
      .all() as AccountRow[]

    const payload = {
      exported_at: new Date().toISOString(),
      positions: positions.map((p) => ({
        ticker: p.ticker,
        exchange: p.exchange,
        platform: p.platform,
        quantity: p.quantity,
        avg_cost: p.avg_cost,
        entry_date: p.entry_date,
      })),
      accounts: accounts.map((a) => ({
        id: a.id,
        provider: a.provider,
        account_type: a.account_type,
        name: a.name,
        balance: a.balance,
        currency: a.currency,
      })),
    }

    let output: string
    if (format === "json") {
      output = toJSON(payload)
    } else {
      // CSV: two sections with a blank line
      const posCSV = toCSV(payload.positions)
      const acctCSV = toCSV(payload.accounts)
      output = `# Positions\n${posCSV}\n# Accounts\n${acctCSV}`
    }

    if (args.file) {
      writeFileSync(args.file, output)
      console.log(
        `✓ Exported ${positions.length} positions, ${accounts.length} accounts to ${args.file}`,
      )
    } else {
      console.log(output)
    }
  },
})
