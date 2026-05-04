#!/usr/bin/env bun
/**
 * Sync daily price records for open positions.
 *
 * Usage:
 *   bun run scripts/sync-prices.ts               # Catch up all open positions to today
 *   bun run scripts/sync-prices.ts --ticker AAPL # Backfill single ticker from entry date
 *   bun run scripts/sync-prices.ts --all         # Full catch-up (gap fill + latest)
 *
 * DB resolution (mirrors server/index.tsx):
 *   --db PATH       Explicit path
 *   TEST_MODE=1     Uses TEST_PORTFOLIO_DB
 *   default         ./portfolio.db
 */

import { Database } from "bun:sqlite";
import { readFileSync, existsSync } from "fs";
import { join } from "path";
import { homedir } from "os";

const DEFAULT_DB = join(process.cwd(), "portfolio.db");

// ─── DB path resolution ──────────────────────────────────────────────────────

function resolveDbPath(explicitPath?: string): string {
  if (explicitPath) return explicitPath.startsWith("/") ? explicitPath : join(process.cwd(), explicitPath);
  if (process.env.PORTFOLIO_DB) return process.env.PORTFOLIO_DB;
  if (process.env.TEST_MODE === "1") return process.env.TEST_PORTFOLIO_DB ?? "./test_portfolio.db";
  return DEFAULT_DB;
}

// ─── DB setup ────────────────────────────────────────────────────────────────

function connectDb(path: string): Database {
  const db = new Database(path);
  db.exec("PRAGMA journal_mode = WAL");
  db.exec("PRAGMA busy_timeout = 5000");

  // Auto-apply schema
  const schemaPath = join(__dirname, "..", "server", "lib", "schema.sql");
  if (existsSync(schemaPath)) db.exec(readFileSync(schemaPath, "utf-8"));

  return db;
}

// ─── Price fetching (reuse get_price.ts) ────────────────────────────────────

interface PriceBar {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

function fetchHistory(ticker: string): PriceBar[] {
  const proc = Bun.spawnSync({
    cmd: ["bun", "run", join(__dirname, "get_price.ts"), ticker],
    stdout: "pipe",
    stderr: "pipe",
  });

  if (proc.exitCode !== 0) {
    const err = new TextDecoder().decode(proc.stderr).trim();
    throw new Error(`get_price.ts failed for ${ticker}: ${err}`);
  }

  const data = JSON.parse(new TextDecoder().decode(proc.stdout)) as { history?: PriceBar[] };
  return data.history ?? [];
}

// ─── Core sync logic ─────────────────────────────────────────────────────────

interface SyncResult {
  ticker: string;
  action: string;
  upserted: number;
  skipped: number;
  error?: string;
}

function upsertPrices(
  db: Database,
  ticker: string,
  bars: PriceBar[],
  dryRun = false,
): { upserted: number; skipped: number } {
  if (bars.length === 0) return { upserted: 0, skipped: 0 };

  const stmt = db.prepare(`
    INSERT OR REPLACE INTO prices (ticker, date, open, high, low, close, volume, currency)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'GBP')
  `);

  let upserted = 0;
  let skipped = 0;

  for (const bar of bars) {
    if (dryRun) {
      console.log(`    [dry-run] upsert ${ticker} ${bar.date} close=${bar.close}`);
      upserted++;
    } else {
      stmt.run(ticker, bar.date, bar.open, bar.high, bar.low, bar.close, bar.volume);
      upserted++;
    }
  }

  return { upserted, skipped };
}

function catchUpTicker(
  db: Database,
  ticker: string,
  options: { dryRun?: boolean } = {},
): SyncResult {
  try {
    const bars = fetchHistory(ticker);
    if (bars.length === 0) {
      return { ticker, action: "catch-up", upserted: 0, skipped: 0, error: "no data returned" };
    }

    const { upserted, skipped } = upsertPrices(db, ticker, bars, options.dryRun);
    return { ticker, action: "catch-up", upserted, skipped };
  } catch (e: unknown) {
    return { ticker, action: "catch-up", upserted: 0, skipped: 0, error: (e as Error).message };
  }
}

function backfillTicker(
  db: Database,
  ticker: string,
  fromDate: string,
  options: { dryRun?: boolean } = {},
): SyncResult {
  try {
    const bars = fetchHistory(ticker);
    if (bars.length === 0) {
      return { ticker, action: "backfill", upserted: 0, skipped: 0, error: "no data returned" };
    }

    // Filter bars to only those >= fromDate
    const filtered = bars.filter((b) => b.date >= fromDate);

    if (filtered.length === 0) {
      return { ticker, action: "backfill", upserted: 0, skipped: 0, error: `no bars on or after ${fromDate}` };
    }

    const { upserted } = upsertPrices(db, ticker, filtered, options.dryRun);
    return { ticker, action: "backfill", upserted, skipped: bars.length - filtered.length };
  } catch (e: unknown) {
    return { ticker, action: "backfill", upserted: 0, skipped: 0, error: (e as Error).message };
  }
}

function detectGaps(
  db: Database,
  ticker: string,
): { from: string; to: string }[] {
  const rows = db
    .query(
      `SELECT date FROM prices WHERE ticker = ? ORDER BY date ASC`,
    )
    .all(ticker) as { date: string }[];

  if (rows.length < 2) return [];

  const gaps: { from: string; to: string }[] = [];
  for (let i = 1; i < rows.length; i++) {
    const prev = new Date(rows[i - 1].date);
    const curr = new Date(rows[i].date);
    // Count only weekdays between prev and curr (exclude weekends)
    let weekdays = 0;
    const cursor = new Date(prev);
    cursor.setDate(cursor.getDate() + 1);
    while (cursor < curr) {
      const dow = cursor.getDay();
      if (dow !== 0 && dow !== 6) weekdays++;
      cursor.setDate(cursor.getDate() + 1);
    }
    if (weekdays > 1) {
      // Real gap: prev +1 weekday to curr -1 weekday
      const gapStart = new Date(prev);
      let d = gapStart.getDay();
      do { gapStart.setDate(gapStart.getDate() + 1); d = gapStart.getDay(); } while (d === 0 || d === 6);
      const gapEnd = new Date(curr);
      do { gapEnd.setDate(gapEnd.getDate() - 1); d = gapEnd.getDay(); } while (d === 0 || d === 6);
      gaps.push({
        from: gapStart.toISOString().split("T")[0],
        to: gapEnd.toISOString().split("T")[0],
      });
    }
  }
  return gaps;
}

function fillGap(
  db: Database,
  ticker: string,
  fromDate: string,
  toDate: string,
  options: { dryRun?: boolean } = {},
): SyncResult {
  // Yahoo Finance returns up to 1mo of history. For gap fill, we'll re-fetch
  // the ticker and selectively upsert only bars within the gap window.
  // For large gaps (>30 days) we may miss data — warn about it.
  try {
    const bars = fetchHistory(ticker);
    const filtered = bars.filter((b) => b.date >= fromDate && b.date <= toDate);

    if (filtered.length === 0) {
      return { ticker, action: "fill-gap", upserted: 0, skipped: 0, error: `no bars for gap ${fromDate}–${toDate} (may exceed 1mo window)` };
    }

    const { upserted } = upsertPrices(db, ticker, filtered, options.dryRun);
    return { ticker, action: "fill-gap", upserted, skipped: 0 };
  } catch (e: unknown) {
    return { ticker, action: "fill-gap", upserted: 0, skipped: 0, error: (e as Error).message };
  }
}

// ─── CLI args ────────────────────────────────────────────────────────────────

interface CliArgs {
  db?: string;
  ticker?: string;
  all?: boolean;
  dryRun?: boolean;
  verbose?: boolean;
}

function parseArgs(): CliArgs {
  const args = Bun.argv.slice(2);
  const flags: CliArgs = {};
  let i = 0;
  while (i < args.length) {
    const a = args[i];
    if (a === "--db") flags.db = args[++i];
    else if (a === "--ticker") flags.ticker = args[++i];
    else if (a === "--all") flags.all = true;
    else if (a === "--dry-run") flags.dryRun = true;
    else if (a === "--verbose" || a === "-v") flags.verbose = true;
    i++;
  }
  return flags;
}

// ─── Main ────────────────────────────────────────────────────────────────────

async function main() {
  const flags = parseArgs();
  const dbPath = resolveDbPath(flags.db);
  const db = connectDb(dbPath);
  const isTest = dbPath.includes("test");

  console.log(`sync-prices${isTest ? " [TEST MODE]" : ""}`);
  console.log(`  Target DB: ${dbPath}`);

  const results: SyncResult[] = [];

  if (flags.ticker) {
    // ── Single ticker: catch up
    if (flags.verbose) console.log(`  Mode: catch-up single ticker`);
    const result = catchUpTicker(db, flags.ticker, { dryRun: flags.dryRun });
    results.push(result);
  } else if (flags.all) {
    // ── Full sync: gap fill + catch-up for all open positions
    if (flags.verbose) console.log(`  Mode: full sync (gap fill + catch-up)`);

    const tickers = db
      .query(`SELECT DISTINCT ticker FROM positions WHERE status = 'open'`)
      .all() as { ticker: string }[];

    if (tickers.length === 0) {
      console.log(`  No open positions.`);
      return;
    }

    for (const { ticker } of tickers) {
      // 1. Detect and fill gaps
      const gaps = detectGaps(db, ticker);
      if (gaps.length > 0) {
        if (flags.verbose) console.log(`  ${ticker}: ${gaps.length} gap(s) detected`);
        for (const gap of gaps) {
          const r = fillGap(db, ticker, gap.from, gap.to, { dryRun: flags.dryRun });
          results.push(r);
        }
      }

      // 2. Catch up to today (upsert latest bar if not already there)
      const r = catchUpTicker(db, ticker, { dryRun: flags.dryRun });
      results.push(r);
    }
  } else {
    // ── Default: catch up all open positions
    if (flags.verbose) console.log(`  Mode: catch-up all open positions`);

    const tickers = db
      .query(`SELECT DISTINCT ticker FROM positions WHERE status = 'open'`)
      .all() as { ticker: string }[];

    if (tickers.length === 0) {
      console.log(`  No open positions.`);
      return;
    }

    for (const { ticker } of tickers) {
      const r = catchUpTicker(db, ticker, { dryRun: flags.dryRun });
      results.push(r);
    }
  }

  // ── Summary
  console.log(`\nResults:`);
  let totalUpserted = 0;
  let totalErrors = 0;

  for (const r of results) {
    if (r.error) {
      console.log(`  ❌ ${r.ticker}: ${r.error}`);
      totalErrors++;
    } else {
      console.log(`  ✅ ${r.ticker}: ${r.action} +${r.upserted} bars`);
      totalUpserted += r.upserted;
    }
  }

  console.log(`\n  Total: ${totalUpserted} bars upserted${totalErrors > 0 ? `, ${totalErrors} errors` : ""}`);
}

main();