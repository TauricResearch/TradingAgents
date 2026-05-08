#!/usr/bin/env bun
/**
 * Seed the LIVE database with real portfolio data.
 *
 * Usage:
 *   bun scripts/seed_real_portfolio.ts
 *
 * WARNING: This clears all existing positions, accounts, and spread bets
 * from the LIVE database (portfolio.db) and replaces them with real data.
 *
 * Always backup first: just backup
 */

import { DatabaseFactory } from "../src/lib/db.ts"

const dbPath = process.env.PORTFOLIO_DB ?? "./portfolio.db"

// ── Real Data ─────────────────────────────────────────────────────────────

interface RealAccount {
  id: string
  provider: string
  account_type: string
  name: string
  balance: number
  currency: string
}

interface RealPosition {
  ticker: string
  exchange: string
  platform: string
  account_id: string
  quantity: number
  avg_cost: number
  currency: string
  entry_date: string
  thesis: string | null
}

const REAL_ACCOUNTS: RealAccount[] = [
  {
    id: "ig-spreadbet",
    provider: "IG",
    account_type: "spreadbet",
    name: "IG Spread Bet",
    balance: 511.64,
    currency: "GBP",
  },
  {
    id: "ig-isa",
    provider: "IG",
    account_type: "isa",
    name: "IG ISA",
    balance: 20868.5,
    currency: "GBP",
  },
  {
    id: "ig-shares",
    provider: "IG",
    account_type: "shares",
    name: "IG Share Dealing",
    balance: 9834.95,
    currency: "GBP",
  },
  {
    id: "ajbell",
    provider: "AJBell",
    account_type: "sipp",
    name: "AJBell SIPP",
    balance: 108221.44,
    currency: "GBP",
  },
  {
    id: "aviva",
    provider: "Aviva",
    account_type: "sipp",
    name: "Aviva Pension",
    balance: 134761.89,
    currency: "GBP",
  },
  {
    id: "nsandi",
    provider: "NS&I",
    account_type: "savings",
    name: "NS&I Premium Bonds",
    balance: 15875.0,
    currency: "GBP",
  },
  {
    id: "utmost-ewa",
    provider: "Utmost",
    account_type: "pension",
    name: "Utmost EWA",
    balance: 34171.21,
    currency: "GBP",
  },
  {
    id: "utmost-msa",
    provider: "Utmost",
    account_type: "pension",
    name: "Utmost MSA",
    balance: 2697.82,
    currency: "GBP",
  },
]

const REAL_POSITIONS: RealPosition[] = [
  {
    ticker: "TKA.DE",
    exchange: "XETRA",
    platform: "ig-shares",
    account_id: "ig-shares",
    quantity: 115,
    avg_cost: 10.92, // €1,255.80 / 115 shares (current value proxy)
    currency: "EUR",
    entry_date: "2026-01-01", // Placeholder — user should update with actual
    thesis: "Industrial conglomerate restructuring play",
  },
  {
    ticker: "TKMS.DE",
    exchange: "XETRA",
    platform: "ig-shares",
    account_id: "ig-shares",
    quantity: 5,
    avg_cost: 81.4, // €407.00 / 5 shares (current value proxy)
    currency: "EUR",
    entry_date: "2026-01-01", // Placeholder
    thesis: "Defence/shipbuilding subsidiary",
  },
]

// ── Main ──────────────────────────────────────────────────────────────────

function clearTestData(db: ReturnType<typeof DatabaseFactory.get>): void {
  console.log("Clearing test data from LIVE database...")

  db.run("DELETE FROM positions")
  db.run("DELETE FROM spreadbet_positions")
  db.run("DELETE FROM accounts")
  db.run("DELETE FROM trades")
  db.run("DELETE FROM signals")
  db.run("DELETE FROM watchlist")

  console.log("  ✓ Cleared: positions, spreadbet_positions, accounts, trades, signals, watchlist")
}

function insertAccounts(db: ReturnType<typeof DatabaseFactory.get>): void {
  console.log("Inserting real accounts...")

  const stmt = db.prepare(
    "INSERT INTO accounts (id, provider, account_type, name, balance, currency) VALUES (?, ?, ?, ?, ?, ?)",
  )

  for (const a of REAL_ACCOUNTS) {
    stmt.run(a.id, a.provider, a.account_type, a.name, a.balance, a.currency)
    console.log(
      `  ✓ ${a.name}: ${a.balance.toLocaleString("en-GB", { minimumFractionDigits: 2 })} ${a.currency}`,
    )
  }

  stmt.finalize()
}

function insertPositions(db: ReturnType<typeof DatabaseFactory.get>): void {
  console.log("Inserting real positions...")

  const stmt = db.prepare(
    "INSERT INTO positions (ticker, exchange, platform, account_id, quantity, avg_cost, entry_date, thesis, status, currency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
  )

  for (const p of REAL_POSITIONS) {
    stmt.run(
      p.ticker,
      p.exchange,
      p.platform,
      p.account_id,
      p.quantity,
      p.avg_cost,
      p.entry_date,
      p.thesis,
      p.currency,
    )
    console.log(`  ✓ ${p.ticker}: ${p.quantity} shares @ ${p.avg_cost} ${p.currency} (${p.thesis})`)
  }

  stmt.finalize()
}

function updateHledgerJournal(): void {
  const journalPath = process.env.HLEDGER_FILE ?? `${process.env.HOME}/.hledger.journal`
  const fs = require("node:fs")

  console.log(`Updating hledger journal: ${journalPath}`)

  const entries = REAL_ACCOUNTS.map((a) => {
    const accountPath = `assets:${a.provider.toLowerCase().replace(/\s+/g, "-")}:${a.account_type}:cash`
    return `2026-05-07 * "${a.name}"
  ${accountPath.padEnd(45)} ${a.balance.toFixed(2)} ${a.currency}
  equity:opening balances`
  }).join("\n\n")

  const positions = REAL_POSITIONS.map((p) => {
    const accountPath = `assets:ig:sharedealing:equity:${p.ticker}`
    const totalCost = p.avg_cost * p.quantity
    return `2026-05-07 * "Buy ${p.ticker}"
  ${accountPath.padEnd(45)} ${p.quantity} ${p.ticker} @@ ${totalCost.toFixed(2)} ${p.currency}
  assets:ig:sharedealing:cash`
  }).join("\n\n")

  const header = `; ── TradingAgents Journal ────────────────────────────────────────
;
; Account convention: assets:<platform>:<account_type>
;
; BASE CURRENCY: GBP
; All portfolio values in the UI are displayed in GBP.
; hledger holds native currencies (EUR, USD) — converted on display via live FX rates.
;
; AUTO-GENERATED: ${new Date().toISOString().slice(0, 10)}
; Source: scripts/seed_real_portfolio.ts
`

  const content = `${header}

${entries}

${positions}
`

  fs.writeFileSync(journalPath, content)
  console.log(
    `  ✓ Wrote ${REAL_ACCOUNTS.length} cash entries + ${REAL_POSITIONS.length} position entries`,
  )
}

function main() {
  console.log("=== Seed Real Portfolio ===")
  console.log(`Database: ${dbPath}`)
  console.log("")

  // Backup first
  console.log("Backing up current database...")
  const backupPath = `${dbPath}.backup-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}`
  const fs = require("node:fs")
  fs.copyFileSync(dbPath, backupPath)
  console.log(`  ✓ Backup: ${backupPath}`)
  console.log("")

  DatabaseFactory.connect(dbPath)
  const db = DatabaseFactory.get()

  try {
    clearTestData(db)
    console.log("")
    insertAccounts(db)
    console.log("")
    insertPositions(db)
    console.log("")
    updateHledgerJournal()
    console.log("")
    console.log("=== Done ===")
    console.log("Verify:")
    console.log("  just db-stats          # show LIVE database stats")
    console.log("  just hledger::hl       # show hledger balances")
    console.log("  bun run src/server/index.tsx # start dashboard and check holdings")
  } finally {
    DatabaseFactory.close()
  }
}

main()
