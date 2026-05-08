#!/usr/bin/env bun
/**
 * Seed initial portfolio from user's real data.
 *
 * Wipes ALL data from the database and rebuilds with:
 *   - Accounts (IG Spread Bet, IG ISA, IG Shares + external)
 *   - Positions (TKA.DE, TKMS.DE)
 *   - Account balances
 *
 * Source: scratchpad/initial-funds.csv
 * Entry date: 2026-05-08
 */

import { DatabaseFactory } from "../src/lib/db.ts"

const ENTRY_DATE = "2026-05-08"

interface Account {
  id: string
  provider: string
  account_type: string
  name: string
  balance: number
  currency: string
  notes?: string
}

interface Position {
  ticker: string
  exchange: string
  platform: string
  account_id: string
  quantity: number
  avg_cost: number
  entry_date: string
  notes?: string
}

// ── Data from scratchpad/initial-funds.csv ────────────────────────────────

const accounts: Account[] = [
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
    name: "IG Shares",
    balance: 8401.46,
    currency: "GBP",
  },
  {
    id: "ajbell",
    provider: "AJBell",
    account_type: "sipp",
    name: "AJBell",
    balance: 108221.44,
    currency: "GBP",
    notes: "External SIPP",
  },
  {
    id: "aviva",
    provider: "Aviva",
    account_type: "sipp",
    name: "Aviva",
    balance: 134761.89,
    currency: "GBP",
    notes: "External SIPP",
  },
  {
    id: "nsi",
    provider: "NSI",
    account_type: "savings",
    name: "NSI",
    balance: 15875.0,
    currency: "GBP",
    notes: "Premium Bonds",
  },
  {
    id: "utmost-ewa",
    provider: "Utmost",
    account_type: "savings",
    name: "Utmost EWA",
    balance: 34171.21,
    currency: "GBP",
    notes: "External savings",
  },
  {
    id: "utmost-msa",
    provider: "Utmost",
    account_type: "savings",
    name: "Utmost MSA",
    balance: 2697.82,
    currency: "GBP",
    notes: "External savings",
  },
]

const positions: Position[] = [
  {
    ticker: "TKA.DE",
    exchange: "XETRA",
    platform: "ig-shares",
    account_id: "ig-shares",
    quantity: 115,
    avg_cost: 10.2,
    entry_date: ENTRY_DATE,
    notes: "thyssenkrupp AG",
  },
  {
    ticker: "TKMS.DE",
    exchange: "XETRA",
    platform: "ig-shares",
    account_id: "ig-shares",
    quantity: 5,
    avg_cost: 0,
    entry_date: ENTRY_DATE,
    notes: "Tkms AG& Co KGaA",
  },
]

// ── Main ──────────────────────────────────────────────────────────────────

console.log("Seeding initial portfolio...")
console.log(`  Target DB: ${process.env.PORTFOLIO_DB ?? "portfolio.db"}`)
console.log(`  Entry date: ${ENTRY_DATE}`)

DatabaseFactory.connect(process.env.PORTFOLIO_DB ?? "portfolio.db")
const db = DatabaseFactory.get()

// ── Wipe everything ───────────────────────────────────────────────────────

console.log("\nWiping existing data...")

const tables = [
  "positions",
  "trades",
  "signals",
  "watchlist",
  "analyses",
  "spreadbet_positions",
  "account_balances",
  "accounts",
]

for (const table of tables) {
  db.exec(`DELETE FROM ${table}`)
  // Reset auto-increment counters
  try {
    db.exec(`DELETE FROM sqlite_sequence WHERE name = '${table}'`)
  } catch {
    // sqlite_sequence may not exist for tables without integer PK
  }
  console.log(`  Cleared ${table}`)
}

// ── Insert accounts ───────────────────────────────────────────────────────

console.log("\nInserting accounts...")

const insertAccount = db.prepare(
  `INSERT INTO accounts (id, provider, account_type, name, balance, currency, notes)
   VALUES (?, ?, ?, ?, ?, ?, ?)`,
)

for (const ac of accounts) {
  insertAccount.run(
    ac.id,
    ac.provider,
    ac.account_type,
    ac.name,
    ac.balance,
    ac.currency,
    ac.notes ?? null,
  )
  console.log(
    `  ${ac.name}: ${ac.balance.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${ac.currency}`,
  )
}

// ── Insert positions ──────────────────────────────────────────────────────

console.log("\nInserting positions...")

const insertPosition = db.prepare(
  `INSERT INTO positions (ticker, exchange, platform, account_id, quantity, avg_cost, entry_date, status, notes)
   VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)`,
)

for (const pos of positions) {
  insertPosition.run(
    pos.ticker,
    pos.exchange,
    pos.platform,
    pos.account_id,
    pos.quantity,
    pos.avg_cost,
    pos.entry_date,
    pos.notes ?? null,
  )
  console.log(`  ${pos.ticker}: ${pos.quantity} shares @ ${pos.avg_cost} EUR`)
}

// ── Verify ────────────────────────────────────────────────────────────────

console.log("\nVerification:")

const posCount = (db.query("SELECT COUNT(*) as n FROM positions").get() as { n: number }).n
const acctCount = (db.query("SELECT COUNT(*) as n FROM accounts").get() as { n: number }).n
const totalBalance = (
  db.query("SELECT SUM(balance) as total FROM accounts").get() as { total: number }
).total

console.log(`  Accounts: ${acctCount}`)
console.log(`  Positions: ${posCount}`)
console.log(
  `  Total balance across all accounts: £${totalBalance.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
)

console.log("\n✓ Done.")
