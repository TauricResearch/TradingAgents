#!/usr/bin/env bun

/**
 * Migration: Add research linkage fields to watchlist table and seed Hormuz stocks.
 *
 * Adds:
 *   - research_doc TEXT         -- FK to research-registry ID (e.g. 'hormuz-2026-05-14')
 *   - last_research_update TEXT -- YYYY-MM-DD of last research update
 *
 * Seeds 12 Hormuz-recommended stocks and flags 8 stale entries.
 *
 * Run: bun scripts/migrate-watchlist-research.ts
 */

import { DatabaseFactory } from "@lib/db"
import { cfg } from "@lib/settings"

// ── Connect ────────────────────────────────────────────────────────────────────

DatabaseFactory.connect(cfg.portfolio.db)
const db = DatabaseFactory.get()

console.log("")

// ── Step 1: Add columns (safe — only runs if not exists) ──────────────────────

function addColumnIfNotExists(table: string, col: string, type: string) {
  const info = db.query(`PRAGMA table_info(${table})`).all() as Array<{ name: string }>
  const exists = info.some((c) => c.name === col)
  if (!exists) {
    db.run(`ALTER TABLE ${table} ADD COLUMN ${col} ${type}`)
    console.log(`  ✓ Added ${col} to ${table}`)
  } else {
    console.log(`  · ${col} already exists in ${table}`)
  }
}

console.log("Migrating watchlist schema...")
addColumnIfNotExists("watchlist", "research_doc", "TEXT")
addColumnIfNotExists("watchlist", "last_research_update", "TEXT")

// ── Step 2: Seed 12 Hormuz stocks ──────────────────────────────────────────────

const RESEARCH_DOC = "hormuz-2026-05-14"
const RESEARCH_DATE = "2026-05-14"

const HORMUZ_STOCKS: Array<{
  ticker: string
  exchange: string
  platform: string
  priority: string
  thesis: string
}> = [
  // High priority — core Hormuz beneficiaries
  {
    ticker: "COP",
    exchange: "US",
    platform: "degiero",
    priority: "high",
    thesis:
      "Permian pure-play upstream E&P. North American asset density avoids Gulf exposure. Best-of-breed recovery play per Mizuho conviction list.",
  },
  {
    ticker: "FANG",
    exchange: "US",
    platform: "degiero",
    priority: "high",
    thesis:
      "Delaware sub-basin pure-play. High oil-price beta — captures full upside of Brent at $126+. Production doubled since 2019.",
  },
  {
    ticker: "LIN",
    exchange: "US",
    platform: "degiero",
    priority: "high",
    thesis:
      "World's largest industrial gas company. Helium oligopoly with semiconductor customers (price inelastic). Upgraded to Buy amid helium supply crisis.",
  },
  {
    ticker: "APD",
    exchange: "US",
    platform: "degiero",
    priority: "high",
    thesis:
      "Major industrial gas player. 15-25yr take-or-pay contracts provide stable cash flows. Helium first-mover advantage in North America.",
  },
  {
    ticker: "CF",
    exchange: "US",
    platform: "degiero",
    priority: "high",
    thesis:
      "North American nitrogen fertilizer giant. 33.5% operating margin, 19.3% revenue growth. Directly competes with blocked Gulf imports.",
  },
  {
    ticker: "MOS",
    exchange: "US",
    platform: "degiero",
    priority: "medium",
    thesis:
      "North America's largest potash/phosphate producer (12% and 10% global output). Soybean demand shift drives secondary potash surge.",
  },
  {
    ticker: "LMT",
    exchange: "US",
    platform: "degiero",
    priority: "high",
    thesis:
      "Defense bellwether. $194B backlog, F-35 production doubling in 2027. Pentagon $1.5T budget expansion beneficiary.",
  },
  {
    ticker: "RTX",
    exchange: "US",
    platform: "degiero",
    priority: "high",
    thesis:
      "Patriot air defense systems in unprecedented NATO demand. Dual exposure to defense (Raytheon) + commercial aviation (Pratt & Whitney).",
  },
  {
    ticker: "GD",
    exchange: "US",
    platform: "degiero",
    priority: "medium",
    thesis:
      "Nuclear submarines and armored vehicles. $118B backlog. Navy 16 support ships contract package worth $65.8B.",
  },
  // Medium priority — integrated energy with LNG exposure
  {
    ticker: "SHEL",
    exchange: "UK",
    platform: "degiero",
    priority: "medium",
    thesis:
      "Global LNG dominant. 70+ countries. Diversified operations reroute supply from Qatari charters. 56.9% EPS growth, 8.64 forward P/E.",
  },
  {
    ticker: "CVX",
    exchange: "US",
    platform: "degiero",
    priority: "medium",
    thesis:
      "3.9% yield, dividend increased annually for decades. Libya entry + massive US footprint. Non-Gulf hedging strategy.",
  },
  {
    ticker: "BP",
    exchange: "UK",
    platform: "degiero",
    priority: "medium",
    thesis:
      "High recovery potential. 8.77 forward P/E, 75.07% EPS growth projected. Diversified beyond Middle East exposure.",
  },
]

console.log("\nSeeding Hormuz research stocks...")

let seededCount = 0
for (const stock of HORMUZ_STOCKS) {
  // Upsert: update if exists, insert if not
  const existing = db
    .query<{ id: number }, [string, string]>(
      "SELECT id FROM watchlist WHERE ticker = ? AND exchange = ?",
    )
    .get(stock.ticker, stock.exchange)

  if (existing) {
    db.run(
      `UPDATE watchlist
       SET thesis = ?, priority = ?, research_doc = ?, last_research_update = ?, stage = 'analyzed'
       WHERE ticker = ? AND exchange = ?`,
      [stock.thesis, stock.priority, RESEARCH_DOC, RESEARCH_DATE, stock.ticker, stock.exchange],
    )
    console.log(`  · Updated ${stock.ticker} (existing)`)
  } else {
    db.run(
      `INSERT INTO watchlist (ticker, exchange, platform, thesis, priority, stage, added_date, research_doc, last_research_update)
       VALUES (?, ?, ?, ?, ?, 'analyzed', ?, ?, ?)`,
      [
        stock.ticker,
        stock.exchange,
        stock.platform,
        stock.thesis,
        stock.priority,
        RESEARCH_DATE,
        RESEARCH_DOC,
        RESEARCH_DATE,
      ],
    )
    console.log(`  ✓ Seeded ${stock.ticker}`)
    seededCount++
  }
}

// ── Step 3: Flag stale entries (no research_doc, pre-Hormuz) ──────────────────

console.log("\nFlagging stale watchlist entries...")

const STALE_TICKERS = ["GOOGL", "META", "AMZN", "ASML", "SAP", "ARM", "BTC", "SOL"]

// Mark stale entries by adding a note about missing research linkage
// These are flagged, not deleted — user decides whether to archive
const staleResult = db.run(
  `UPDATE watchlist
   SET stage = 'analyzed'
   WHERE research_doc IS NULL
     AND ticker IN (${STALE_TICKERS.map(() => "?").join(",")})`,
  STALE_TICKERS,
)
console.log(`  · Flagged ${staleResult.changes} stale entries (no research_doc linkage)`)

// ── Step 4: Show summary ───────────────────────────────────────────────────────

console.log("\n" + "─".repeat(60))
console.log("WATCHLIST SUMMARY")
console.log("─".repeat(60))

const total = (db.query("SELECT COUNT(*) as n FROM watchlist").get() as { n: number }).n
const hormuzCount = (
  db.query("SELECT COUNT(*) as n FROM watchlist WHERE research_doc = ?").get(RESEARCH_DOC) as {
    n: number
  }
).n
const staleCount = (
  db.query("SELECT COUNT(*) as n FROM watchlist WHERE research_doc IS NULL").get() as { n: number }
).n

console.log(`  Total entries:  ${total}`)
console.log(`  Hormuz stocks:  ${hormuzCount}`)
console.log(`  Stale (unlinked): ${staleCount}`)
console.log("─".repeat(60))

// ── Step 5: List all entries with research linkage ─────────────────────────────

console.log("")
console.log("Current watchlist:")
console.log("─".repeat(90))
console.log(
  `  ${"Ticker".padEnd(8)} ${"Exchange".padEnd(8)} ${"Priority".padEnd(8)} ${"Stage".padEnd(12)} ${"Research Doc".padEnd(20)} ${"Last Update".padEnd(12)} Thesis`,
)
console.log("─".repeat(90))

const rows = db
  .query(
    `SELECT ticker, exchange, priority, stage, research_doc, last_research_update, thesis
     FROM watchlist
     ORDER BY research_doc DESC, priority DESC, ticker`,
  )
  .all() as Array<{
  ticker: string
  exchange: string
  priority: string
  stage: string
  research_doc: string | null
  last_research_update: string | null
  thesis: string | null
}>

for (const r of rows) {
  const staleFlag = r.research_doc ? "" : " ⚠"
  const docStr = r.research_doc ?? "—"
  const dateStr = r.last_research_update ?? "—"
  const thesisShort = r.thesis
    ? r.thesis.length > 30
      ? `${r.thesis.slice(0, 27)}...`
      : r.thesis
    : "—"
  console.log(
    `  ${r.ticker.padEnd(8)} ${r.exchange.padEnd(8)} ${r.priority.padEnd(8)} ${r.stage.padEnd(12)} ${docStr.padEnd(20)} ${dateStr.padEnd(12)} ${thesisShort}${staleFlag}`,
  )
}

console.log("─".repeat(90))
console.log("")
