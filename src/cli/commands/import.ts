#!/usr/bin/env bun

/**
 * Import positions from CSV.
 *
 * Expected CSV format:
 *   ticker,exchange,platform,quantity,avg_cost,entry_date
 *
 * Usage: trading import <file.csv>
 */

import { existsSync, readFileSync } from "node:fs"
import { defineCommand } from "citty"
import { DatabaseFactory } from "../../lib/db.ts"
import { cfg } from "../../server/lib/settings.ts"

interface CsvRow {
  ticker: string
  exchange: string
  platform: string
  quantity: string
  avg_cost: string
  entry_date: string
}

function parseCSV(content: string): CsvRow[] {
  const lines = content.trim().split("\n")
  if (lines.length < 2) {
    throw new Error("CSV must have a header and at least one data row")
  }

  const header = lines[0].split(",").map((h) => h.trim().toLowerCase())
  const required = ["ticker", "quantity", "avg_cost", "entry_date"]
  for (const r of required) {
    if (!header.includes(r)) {
      throw new Error(`CSV header missing required column: ${r}`)
    }
  }

  const rows: CsvRow[] = []
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim()
    if (!line || line.startsWith("#")) continue

    const values: string[] = []
    let current = ""
    let inQuotes = false
    for (const char of line) {
      if (char === '"' && !inQuotes) {
        inQuotes = true
      } else if (char === '"' && inQuotes) {
        inQuotes = false
      } else if (char === "," && !inQuotes) {
        values.push(current.trim())
        current = ""
      } else {
        current += char
      }
    }
    values.push(current.trim())

    const row: Record<string, string> = {}
    for (let j = 0; j < header.length; j++) {
      row[header[j]] = values[j] ?? ""
    }

    rows.push({
      ticker: row.ticker ?? "",
      exchange: row.exchange ?? "US",
      platform: row.platform ?? "imported",
      quantity: row.quantity ?? "0",
      avg_cost: row.avg_cost ?? "0",
      entry_date: row.entry_date ?? "",
    })
  }

  return rows
}

export const importCommand = defineCommand({
  meta: {
    name: "import",
    description: "Import positions from CSV",
  },
  args: {
    file: {
      type: "positional",
      description: "Path to CSV file",
      required: true,
    },
    dryRun: {
      type: "boolean",
      description: "Preview without inserting",
      default: false,
    },
  },
  run: ({ args }) => {
    const filePath = args.file
    if (!existsSync(filePath)) {
      console.error(`❌ File not found: ${filePath}`)
      process.exit(1)
    }

    let rows: CsvRow[]
    try {
      const content = readFileSync(filePath, "utf-8")
      rows = parseCSV(content)
    } catch (err) {
      console.error(`❌ Failed to parse CSV: ${(err as Error).message}`)
      process.exit(1)
    }

    if (rows.length === 0) {
      console.log("No valid rows found in CSV.")
      return
    }

    console.log(`Found ${rows.length} position${rows.length === 1 ? "" : "s"} to import:`)
    console.log("")
    console.log(
      `${"Ticker".padEnd(12)} ${"Exchange".padEnd(8)} ${"Platform".padEnd(10)} ${"Qty".padStart(6)} ${"Avg Cost".padStart(10)} ${"Entry Date".padStart(12)}`,
    )
    console.log("─".repeat(70))

    for (const r of rows) {
      console.log(
        `${r.ticker.padEnd(12)} ${r.exchange.padEnd(8)} ${r.platform.padEnd(10)} ${r.quantity.padStart(6)} ${r.avg_cost.padStart(10)} ${r.entry_date.padStart(12)}`,
      )
    }

    if (args.dryRun) {
      console.log("")
      console.log("⚠️  Dry run — no changes made. Omit --dry-run to import.")
      return
    }

    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const stmt = db.prepare(
      `INSERT INTO positions (ticker, exchange, platform, quantity, avg_cost, entry_date, status)
       VALUES (?, ?, ?, ?, ?, ?, 'open')`,
    )

    let inserted = 0
    for (const r of rows) {
      try {
        stmt.run(
          r.ticker,
          r.exchange,
          r.platform,
          parseInt(r.quantity, 10),
          parseFloat(r.avg_cost),
          r.entry_date,
        )
        inserted++
      } catch (err) {
        console.error(`  ⚠️  Skipped ${r.ticker}: ${(err as Error).message}`)
      }
    }

    console.log("")
    console.log(`✓ Imported ${inserted}/${rows.length} positions`)
  },
})
