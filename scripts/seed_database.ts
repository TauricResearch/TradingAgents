#!/usr/bin/env bun
/**
 * Seed the TradingAgents database with realistic simulation data.
 *
 * Usage:
 *   bun run scripts/seed_database.ts              # Full reset + seed
 *   bun run scripts/seed_database.ts --positions  # Positions only
 *   bun run scripts/seed_database.ts --signals    # Signals only
 *   bun run scripts/seed_database.ts --all        # Everything (default)
 *
 * DB resolution (mirrors server/index.tsx):
 *   --db PATH         Explicit path (highest priority)
 *   PORTFOLIO_DB      DEV database path
 *   TEST_MODE=1       Uses TEST_PORTFOLIO_DB or ./test_portfolio.db
 *   default           ./portfolio.db
 */

import { Database } from "bun:sqlite";
import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync, unlinkSync } from "fs";
import { join, dirname } from "path";
import { homedir } from "os";
import * as yaml from "js-yaml";

const DEFAULT_DB = join(process.cwd(), "portfolio.db");
const POSITIONS_BASE = join(homedir(), ".tradingagents", "positions");
const POST_MORTEMS_DIR = join(homedir(), ".tradingagents", "post-mortems");

// ─── DB path resolution ──────────────────────────────────────────────────────

function resolveDbPath(explicitPath?: string): string {
  if (explicitPath) {
    const p = explicitPath.startsWith("/")
      ? explicitPath
      : join(process.cwd(), explicitPath);
    return p;
  }
  if (process.env.PORTFOLIO_DB) return process.env.PORTFOLIO_DB;
  if (process.env.TEST_MODE === "1") {
    return process.env.TEST_PORTFOLIO_DB ?? "./test_portfolio.db";
  }
  return DEFAULT_DB;
}

// ─── SQLite helpers ──────────────────────────────────────────────────────────

let _db: Database;

function getDb(): Database {
  if (!_db) throw new Error("DB not initialized — call main() first");
  return _db;
}

function connectDb(path: string): Database {
  const db = new Database(path);
  db.exec("PRAGMA journal_mode = WAL");
  db.exec("PRAGMA busy_timeout = 5000");
  db.exec("PRAGMA foreign_keys = ON");
  _db = db;
  return db;
}

// ─── Secret sanitization ─────────────────────────────────────────────────────

const SANITIZE_PATTERNS: [RegExp, string][] = [
  [/\bsk-[-A-Za-z0-9]{20,}/g, "[API_KEY_REMOVED]"],
  [/\bsk-ant(?:thropic)?[-][A-Za-z0-9]{20,}/gi, "[API_KEY_REMOVED]"],
  [/Bearer\s+[A-Za-z0-9_\-]{10,}/g, "[TOKEN_REMOVED]"],
  [/https?:\/\/[^:\s]+:[^@\s]+@[^\s]+/g, "[URL_CREDS_REMOVED]"],
  [/(?:password|secret|apikey|api_key|token|auth)[=:]\s*[^\s;,]{8,}/gi, "[SECRET_REMOVED]"],
  [/-----BEGIN\s+(?:RSA|EC|OPENSSH|DSA|PRIVATE)\s+KEY-----[\s\S]*?-----END\s+\w+\s+KEY-----/g, "[PRIVATE_KEY_REMOVED]"],
  [/[A-Fa-f0-9]{40,}/g, "[HEX_TOKEN_REMOVED]"],
];

function sanitize(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  let result = value;
  for (const [pattern, replacement] of SANITIZE_PATTERNS) {
    result = result.replace(pattern, replacement);
  }
  return result;
}

// ─── Date helpers ────────────────────────────────────────────────────────────

function d(weeks = 0, days = 0): string {
  const date = new Date();
  date.setDate(date.getDate() + weeks * 7 + days);
  return date.toISOString().split("T")[0];
}

// ─── Table clearing ──────────────────────────────────────────────────────────

function clearTable(table: string): void {
  const db = getDb();
  if (table === "positions") {
    db.exec("DELETE FROM positions WHERE platform = 'test'");
  } else if (table === "signals") {
    db.exec("DELETE FROM signals WHERE date BETWEEN '2026-01-01' AND '2026-04-01'");
  } else if (table === "watchlist") {
    db.exec("DELETE FROM watchlist WHERE platform = 'test'");
  } else if (table === "analyses") {
    db.exec("DELETE FROM analyses WHERE date BETWEEN '2026-01-01' AND '2026-04-01'");
  }
  console.log(`  Cleared ${table}`);
}

// ── Seed functions ──────────────────────────────────────────────────────────

function seedPositions(): void {
  clearTable("positions");

  const positions = [
    { ticker: "VWCE.DE", exchange: "XETRA", platform: "test", quantity: 10, avg_cost: 132.00, entry_date: d(-3), thesis: "All-world ETF — low-cost core holding, accumulating", status: "open", notes: "Accumulating quarterly. MSCI World exposure." },
    { ticker: "AAPL", exchange: "US", platform: "test", quantity: 10, avg_cost: 192.00, entry_date: d(-3), thesis: "Testing signal accuracy — smaller position", status: "open", notes: "Test position — WWDC catalyst watch" },
    { ticker: "ETH", exchange: "CRYPTO", platform: "test", quantity: 0.5, avg_cost: 2850.00, entry_date: d(-2), thesis: "Crypto exposure test — ETH staking yield 3.8%", status: "open", notes: "Risk-off behaviour expected. Small position." },
    { ticker: "TSLA", exchange: "US", platform: "test", quantity: 5, avg_cost: 245.00, entry_date: d(-1), thesis: "EV market share pressure; FSD licensing optionality", status: "open", notes: "Recent addition — watch for thesis invalidation" },
  ];

  const db = getDb();
  for (const p of positions) {
    db.run(
      `INSERT INTO positions (ticker, exchange, platform, quantity, avg_cost, entry_date, thesis, status, notes)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [p.ticker, p.exchange, p.platform, p.quantity, p.avg_cost, p.entry_date, sanitize(p.thesis), p.status, sanitize(p.notes)],
    );
  }
  db.exec("DELETE FROM positions WHERE platform = 'degiero' OR platform = 'ibkr'");
  console.log(`  Inserted ${positions.length} positions`);
}

function seedSignals(): void {
  clearTable("signals");

  const signals = [
    { ticker: "VWCE.DE", platform: "degiero", date: d(-16), signal: "hold", confidence: 0.72, reasoning: "All-world ETF, low-cost, accumulating position. No thesis change." },
    { ticker: "VWCE.DE", platform: "degiero", date: d(-12), signal: "hold", confidence: 0.70, reasoning: "MSCI World constituents strong. No need to rebalance." },
    { ticker: "VWCE.DE", platform: "degiero", date: d(-8), signal: "overweight", confidence: 0.75, reasoning: "Q4 earnings beat. Global equity markets favouring developed market exposure." },
    { ticker: "VWCE.DE", platform: "degiero", date: d(-4), signal: "buy", confidence: 0.78, reasoning: "Market dip provides entry opportunity. Accumulation phase continues." },
    { ticker: "VWCE.DE", platform: "ibkr", date: d(-4), signal: "buy", confidence: 0.75, reasoning: "Core satnav position. Low-cost exposure to global equity." },
    { ticker: "AAPL", platform: "test", date: d(-14), signal: "buy", confidence: 0.78, reasoning: "AI services integration driving margin expansion. Vision Pro ecosystem." },
    { ticker: "AAPL", platform: "degiero", date: d(-10), signal: "hold", confidence: 0.70, reasoning: "Services revenue acceleration offset by iPhone softness. Hold." },
    { ticker: "AAPL", platform: "degiero", date: d(-6), signal: "overweight", confidence: 0.80, reasoning: "WWDC catalyst identified. AI integration across device lineup strong." },
    { ticker: "AAPL", platform: "degiero", date: d(-2), signal: "buy", confidence: 0.85, reasoning: "Services margins hit 74%. AI features driving upgrade cycle. Target raised." },
    { ticker: "AAPL", platform: "ibkr", date: d(-14), signal: "buy", confidence: 0.82, reasoning: "Long-term AI compounding thesis. Larger position justified by conviction." },
    { ticker: "AAPL", platform: "ibkr", date: d(-8), signal: "overweight", confidence: 0.78, reasoning: "Position overweight but thesis unchanged. Monitor for rebalancing." },
    { ticker: "AAPL", platform: "ibkr", date: d(-3), signal: "buy", confidence: 0.88, reasoning: "Services segment 3-year CAGR 15%. Target price raised to $220." },
    { ticker: "AAPL", platform: "test", date: d(-3), signal: "buy", confidence: 0.82, reasoning: "Signal accuracy test. AI services still primary driver." },
    { ticker: "MSFT", platform: "degiero", date: d(-8), signal: "buy", confidence: 0.76, reasoning: "Azure AI monetization ahead of schedule. Copilot enterprise adoption." },
    { ticker: "MSFT", platform: "degiero", date: d(-4), signal: "buy", confidence: 0.80, reasoning: "GitHub Copilot at 1.3M paid subscribers. Azure AI services revenue growing 30%." },
    { ticker: "MSFT", platform: "ibkr", date: d(-7), signal: "buy", confidence: 0.75, reasoning: "Cloud + AI platform. GitHub Copilot enterprise rollout strong." },
    { ticker: "MSFT", platform: "ibkr", date: d(-2), signal: "overweight", confidence: 0.79, reasoning: "Azure AI competitive moat widening. Target raised to $460." },
    { ticker: "NVDA", platform: "degiero", date: d(-6), signal: "buy", confidence: 0.72, reasoning: "AI infrastructure spend insatiable. H100 supply constrained through Q2." },
    { ticker: "NVDA", platform: "degiero", date: d(-2), signal: "overweight", confidence: 0.80, reasoning: "Blackwell architecture driving next wave. Data centre revenue +85%." },
    { ticker: "TKA.DE", platform: "ibkr", date: d(-5), signal: "buy", confidence: 0.68, reasoning: "German industrial automation cycle bottoming. Order pipeline strong for H2." },
    { ticker: "TKA.DE", platform: "ibkr", date: d(-1), signal: "buy", confidence: 0.73, reasoning: "KONE partnership accelerating revenue. Price target €10.50." },
    { ticker: "TKA.DE", platform: "test", date: d(-16), signal: "sell", confidence: 0.55, reasoning: "Position too small for delisted tracking. Closed out." },
    { ticker: "ETH", platform: "test", date: d(-2), signal: "buy", confidence: 0.60, reasoning: "Crypto exposure test. ETH staking yield 3.8%. Small position." },
    { ticker: "TSLA", platform: "test", date: d(-1), signal: "underweight", confidence: 0.65, reasoning: "EV price war compressing margins. FSD licensing uncertain. Reduce." },
    { ticker: "AAPL", platform: "ibkr", date: d(-26), signal: "buy", confidence: 0.75, reasoning: "Initial AAPL position entry" },
    { ticker: "AAPL", platform: "ibkr", date: d(-20), signal: "overweight", confidence: 0.80, reasoning: "AI integration thesis strengthening" },
    { ticker: "AAPL", platform: "ibkr", date: d(-16), signal: "hold", confidence: 0.72, reasoning: "Hold signal. Services growth stable." },
    { ticker: "MSFT", platform: "degiero", date: d(-12), signal: "buy", confidence: 0.70, reasoning: "Initial MSFT position. Cloud + AI platform." },
  ];

  const db = getDb();
  for (const s of signals) {
    db.run(
      `INSERT INTO signals (ticker, platform, date, signal, reasoning, confidence)
       VALUES (?, ?, ?, ?, ?, ?)`,
      [s.ticker, s.platform, s.date, s.signal, sanitize(s.reasoning), String(s.confidence)],
    );
  }
  console.log(`  Inserted ${signals.length} signals`);
}

function seedWatchlist(): void {
  clearTable("watchlist");

  const watchlist = [
    { ticker: "GOOGL", platform: "degiero", exchange: "US", thesis: "Gemini Ultra competitive with GPT-4. Cloud growth accelerating.", priority: "high", stage: "analyzed" },
    { ticker: "AMZN", platform: "degiero", exchange: "US", thesis: "AWS AI services and Rufus e-commerce AI. Margin expansion.", priority: "high", stage: "candidate" },
    { ticker: "META", platform: "ibkr", exchange: "US", thesis: "Llama ecosystem and AI ad tools driving efficiency. Threads growth.", priority: "high", stage: "analyzed" },
    { ticker: "ASML", platform: "degiero", exchange: "EUR", thesis: "Lithography monopoly for advanced chips. AI capex beneficiaries.", priority: "medium", stage: "researching" },
    { ticker: "SAP", platform: "degiero", exchange: "EUR", thesis: "RISE with SAP transitioning to cloud. Joule AI assistant.", priority: "medium", stage: "researching" },
    { ticker: "BTC", platform: "test", exchange: "CRYPTO", thesis: "Bitcoin ETF inflows strong. Store of value narrative.", priority: "low", stage: "researching" },
    { ticker: "SOL", platform: "test", exchange: "CRYPTO", thesis: "Solana DeFi ecosystem growing. Low-cost transactions.", priority: "low", stage: "researching" },
    { ticker: "ARM", platform: "degiero", exchange: "US", thesis: "AI inference chip design. Royalty revenue growing.", priority: "medium", stage: "researching" },
  ];

  const db = getDb();
  for (const w of watchlist) {
    db.run(
      `INSERT INTO watchlist (ticker, exchange, platform, thesis, priority, stage, added_date)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [w.ticker, w.exchange, w.platform, sanitize(w.thesis), w.priority, w.stage, d(-8)],
    );
  }
  console.log(`  Inserted ${watchlist.length} watchlist items`);
}

function seedAnalyses(): void {
  clearTable("analyses");

  const analyses = [
    { ticker: "AAPL", platform: "degiero", date: d(-10), decision: "Hold — Services revenue acceleration confirmed at 74% margins. iPhone softness offset by AI-driven upgrade cycle. Confidence 0.70." },
    { ticker: "AAPL", platform: "ibkr", date: d(-14), decision: "Buy (overweight) — AI services compounding thesis strong. Position size justified by high conviction. Confidence 0.82." },
    { ticker: "MSFT", platform: "degiero", date: d(-8), decision: "Buy — Azure AI monetization ahead of schedule. Copilot enterprise adoption exceeding targets. Confidence 0.76." },
    { ticker: "NVDA", platform: "degiero", date: d(-6), decision: "Buy — AI infrastructure demand insatiable. H100 supply constrained. Confidence 0.72." },
    { ticker: "TKA.DE", platform: "ibkr", date: d(-5), decision: "Buy — German industrial cycle bottoming. KONE deal pipeline strong. Confidence 0.68." },
    { ticker: "VWCE.DE", platform: "degiero", date: d(-4), decision: "Buy — Market dip entry opportunity. Accumulation continues. Confidence 0.78." },
    { ticker: "AAPL", platform: "degiero", date: d(-2), decision: "Buy — WWDC catalyst. AI features across device lineup strong. Target raised. Confidence 0.85." },
  ];

  const db = getDb();
  for (const a of analyses) {
    db.run(
      `INSERT INTO analyses (ticker, platform, date, decision) VALUES (?, ?, ?, ?)`,
      [a.ticker, a.platform, a.date, a.decision],
    );
  }
  console.log(`  Inserted ${analyses.length} analyses`);
}

function seedExitPlans(): void {
  interface ExitPlan {
    platform: string;
    ticker: string;
    entry_price: number;
    quantity: number;
    entry_date: string;
    thesis: string;
    invalidation_price: number;
    invalidation_thesis: string;
    targets: Array<{ price: number; label: string; fraction: number }>;
    time_stop: string;
    notes?: string;
  }

  const plans: ExitPlan[] = [
    { platform: "degiero", ticker: "VWCE.DE", entry_price: 126.40, quantity: 35, entry_date: d(-16), thesis: "All-world ETF accumulation — low-cost core holding", invalidation_price: 113.76, invalidation_thesis: "Global equity bear market; MSCI World -15% from peak", targets: [{ price: 142.00, label: "Target 1: +12%", fraction: 0.33 }, { price: 158.00, label: "Target 2: +25%", fraction: 0.33 }, { price: 175.00, label: "Target 3: +38%", fraction: 0.34 }], time_stop: d(0, 180), notes: "Accumulating quarterly. No rush to exit core ETF position." },
    { platform: "degiero", ticker: "AAPL", entry_price: 188.50, quantity: 25, entry_date: d(-10), thesis: "Services segment compounding; Vision Pro ecosystem building", invalidation_price: 160.00, invalidation_thesis: "Services growth below 10% YoY — core thesis broken", targets: [{ price: 220.00, label: "Target 1: +17%", fraction: 0.33 }, { price: 250.00, label: "Target 2: +33%", fraction: 0.33 }, { price: 280.00, label: "Target 3: +49%", fraction: 0.34 }], time_stop: d(0, 120), notes: "Watch WWDC (June) for AI catalyst." },
    { platform: "degiero", ticker: "MSFT", entry_price: 430.00, quantity: 20, entry_date: d(-8), thesis: "Azure AI monetization accelerating; Copilot enterprise adoption strong", invalidation_price: 387.00, invalidation_thesis: "Azure growth decelerates below 25% YoY", targets: [{ price: 502.00, label: "Target 1: +17%", fraction: 0.50 }, { price: 580.00, label: "Target 2: +35%", fraction: 0.50 }], time_stop: d(0, 150) },
    { platform: "degiero", ticker: "NVDA", entry_price: 880.00, quantity: 15, entry_date: d(-6), thesis: "AI infrastructure demand insatiable; H100/H200 supply constrained", invalidation_price: 748.00, invalidation_thesis: "Data centre spend cuts; AMD MI300X competitive threat", targets: [{ price: 1056.00, label: "Target 1: +20%", fraction: 0.50 }, { price: 1320.00, label: "Target 2: +50%", fraction: 0.50 }], time_stop: d(0, 180) },
    { platform: "ibkr", ticker: "AAPL", entry_price: 182.30, quantity: 150, entry_date: d(-14), thesis: "Long-term AI services compounding — high conviction position", invalidation_price: 155.00, invalidation_thesis: "Services growth below 12%; antitrust risk materialises", targets: [{ price: 215.00, label: "Target 1: +18%", fraction: 0.33 }, { price: 250.00, label: "Target 2: +37%", fraction: 0.33 }, { price: 290.00, label: "Target 3: +59%", fraction: 0.34 }], time_stop: d(0, 240), notes: "NOTE: Position is ~28% of ibkr portfolio — violates max-position rule (15%). Should trim to 65 shares." },
    { platform: "ibkr", ticker: "MSFT", entry_price: 408.00, quantity: 40, entry_date: d(-7), thesis: "Cloud + AI platform play; GitHub Copilot enterprise roll-out", invalidation_price: 347.00, invalidation_thesis: "Azure decelerates; Copilot adoption below targets", targets: [{ price: 480.00, label: "Target 1: +18%", fraction: 0.50 }, { price: 550.00, label: "Target 2: +35%", fraction: 0.50 }], time_stop: d(0, 180) },
    { platform: "ibkr", ticker: "TKA.DE", entry_price: 8.62, quantity: 1000, entry_date: d(-5), thesis: "German industrial automation; order pipeline strong for H2", invalidation_price: 7.33, invalidation_thesis: "Order intake negative; Chinese competition eroding margins", targets: [{ price: 10.35, label: "Target 1: +20%", fraction: 0.50 }, { price: 12.08, label: "Target 2: +40%", fraction: 0.50 }], time_stop: d(0, 120), notes: "KONE partnership expected to close Q3." },
    { platform: "ibkr", ticker: "VWCE.DE", entry_price: 133.20, quantity: 20, entry_date: d(-4), thesis: "Core satnav ETF position alongside individual stock picks", invalidation_price: 113.22, invalidation_thesis: "Global equity drawdown > 15%", targets: [{ price: 146.52, label: "Target 1: +10%", fraction: 0.50 }, { price: 159.84, label: "Target 2: +20%", fraction: 0.50 }], time_stop: d(0, 180) },
    { platform: "test", ticker: "AAPL", entry_price: 192.00, quantity: 10, entry_date: d(-3), thesis: "Testing signal accuracy — smaller position", invalidation_price: 163.20, invalidation_thesis: "Services growth below 10%", targets: [{ price: 225.00, label: "Target 1: +17%", fraction: 0.50 }, { price: 268.00, label: "Target 2: +40%", fraction: 0.50 }], time_stop: d(0, 120) },
    { platform: "test", ticker: "ETH", entry_price: 2850.00, quantity: 0.5, entry_date: d(-2), thesis: "Crypto exposure test — ETH staking yield 3.8%", invalidation_price: 2280.00, invalidation_thesis: "Ethereum mainnet failure; regulatory crackdown", targets: [{ price: 3420.00, label: "Target 1: +20%", fraction: 0.50 }, { price: 4275.00, label: "Target 2: +50%", fraction: 0.50 }], time_stop: d(0, 90), notes: "Risk-off behaviour expected. Small position." },
    { platform: "test", ticker: "TSLA", entry_price: 245.00, quantity: 5, entry_date: d(-1), thesis: "EV market share pressure; FSD licensing optionality", invalidation_price: 208.25, invalidation_thesis: "Margin compression below -5%; FSD delays", targets: [{ price: 294.00, label: "Target 1: +20%", fraction: 0.50 }, { price: 343.00, label: "Target 2: +40%", fraction: 0.50 }], time_stop: d(0, 90) },
  ];

  // Clear existing YAML plans
  for (const platform of ["degiero", "ibkr", "test"]) {
    const dirPath = join(POSITIONS_BASE, platform);
    if (existsSync(dirPath)) {
      for (const file of readdirSync(dirPath).filter((n) => n.endsWith(".yaml"))) {
        const filePath = join(dirPath, file);
        unlinkSync(filePath);
      }
    }
  }

  for (const plan of plans) {
    const dirPath = join(POSITIONS_BASE, plan.platform);
    mkdirSync(dirPath, { recursive: true });

    // Serialize to YAML via js-yaml
    const yamlOut = yaml.dump(plan, { defaultFlowStyle: false, sortKeys: false });

    writeFileSync(join(dirPath, `${plan.ticker}.yaml`), yamlOut);
  }
  console.log(`  Wrote ${plans.length} exit plan YAML files`);
}

function seedPostMortems(): void {
  interface PostMortem {
    ticker: string;
    platform: string;
    exit_date: string;
    entry_price: number;
    exit_price: number;
    thesis: string;
    thesis_played_out: boolean;
    ai_signal_correct: boolean;
    exit_trigger: string;
    lesson: string;
  }

  const postMortems: PostMortem[] = [
    { ticker: "AAPL", platform: "ibkr", exit_date: d(-22), entry_price: 175.00, exit_price: 198.50, thesis: "Long-term AI services compounding — initial position entry", thesis_played_out: true, ai_signal_correct: true, exit_trigger: "target", lesson: "First target hit at +13.4%. Thesis unchanged — allowed to run to second target. Correct patience. AI signal (buy, 0.75) proved accurate. Exited 1/3 at first target, rode remainder." },
    { ticker: "MSFT", platform: "ibkr", exit_date: d(-12), entry_price: 392.00, exit_price: 451.00, thesis: "Cloud + AI platform. GitHub Copilot enterprise rollout", thesis_played_out: true, ai_signal_correct: true, exit_trigger: "target", lesson: "Azure AI services revenue +30% QoQ confirmed. Copilot adoption strong. Exited full position at +15%. AI signal (buy, 0.70) fully justified. No regrets on exit timing." },
    { ticker: "AAPL", platform: "ibkr", exit_date: d(-18), entry_price: 178.50, exit_price: 172.00, thesis: "Overweight — position size increased", thesis_played_out: false, ai_signal_correct: false, exit_trigger: "manual", lesson: "Thesis partially played out but position thesis (overweight) correct. Sold 30 shares at breakeven to reduce exposure. AI signal (overweight, 0.80) was too aggressive for position size. Rule: never increase conviction AND size simultaneously." },
    { ticker: "TKA.DE", platform: "test", exit_date: d(-16), entry_price: 9.80, exit_price: 7.20, thesis: "Position too small for delisted tracking. Closed out.", thesis_played_out: false, ai_signal_correct: false, exit_trigger: "stop", lesson: "Stop loss correctly triggered at -26.5%. Thesis (delisted tracking) was wrong. Exit at stop was correct — saved remaining capital. AI signal (sell, 0.55) was low-confidence and correct." },
  ];

  mkdirSync(POST_MORTEMS_DIR, { recursive: true });

  for (const pm of postMortems) {
    const retRaw = ((pm.exit_price - pm.entry_price) / pm.entry_price) * 100;
    const ret = `${retRaw >= 0 ? "+" : ""}${retRaw.toFixed(1)}%`;
    const content = `# Post-Mortem: ${pm.ticker}

**Exit Date:** ${pm.exit_date}
**Entry Price:** €${pm.entry_price.toFixed(2)}
**Exit Price:** €${pm.exit_price.toFixed(2)}
**Return:** ${ret}

## Thesis
${sanitize(pm.thesis) ?? pm.thesis}

## Outcome
- Thesis played out: ${pm.thesis_played_out ? "✅ Yes" : "❌ No"}
- AI signal correct: ${pm.ai_signal_correct ? "✅ Yes" : "❌ No"}
- Exit trigger: ${pm.exit_trigger}

## Lesson
${sanitize(pm.lesson) ?? pm.lesson}

---
*Post-mortem for ${pm.ticker} position (${pm.platform})*
`;
    const filename = `${pm.exit_date.replace(/-/g, "")}-${pm.ticker}.md`;
    writeFileSync(join(POST_MORTEMS_DIR, filename), content);
  }
  console.log(`  Wrote ${postMortems.length} post-mortems`);
}

// ─── Main ────────────────────────────────────────────────────────────────────

interface CliFlags {
  db?: string;
  positions?: boolean;
  signals?: boolean;
  watchlist?: boolean;
  analyses?: boolean;
  "exit-plans"?: boolean;
  "post-mortems"?: boolean;
  all?: boolean;
}

function parseArgs(): CliFlags {
  const args = Bun.argv.slice(2);
  const flags: CliFlags = {};
  let i = 0;
  while (i < args.length) {
    const arg = args[i];
    if (arg === "--db") { flags.db = args[++i]; }
    else if (arg === "--positions") { flags.positions = true; }
    else if (arg === "--signals") { flags.signals = true; }
    else if (arg === "--watchlist") { flags.watchlist = true; }
    else if (arg === "--analyses") { flags.analyses = true; }
    else if (arg === "--exit-plans") { flags["exit-plans"] = true; }
    else if (arg === "--post-mortems") { flags["post-mortems"] = true; }
    else if (arg === "--all") { flags.all = true; }
    else if (!arg.startsWith("-")) { /* positional, ignore */ }
    i++;
  }
  return flags;
}

async function main() {
  const flags = parseArgs();
  const dbPath = resolveDbPath(flags.db);

  connectDb(dbPath);

  const seedAll =
    !flags.positions && !flags.signals && !flags.watchlist &&
    !flags.analyses && !flags["exit-plans"] && !flags["post-mortems"];

  const isTest = dbPath.endsWith("test_portfolio.db");
  console.log(`Seeding TradingAgents database${isTest ? " [TEST MODE]" : ""}...`);
  console.log(`  Target DB: ${dbPath}`);

  if (seedAll || flags.positions) seedPositions();
  if (seedAll || flags.signals) seedSignals();
  if (seedAll || flags.watchlist) seedWatchlist();
  if (seedAll || flags.analyses) seedAnalyses();
  if (seedAll || flags["exit-plans"]) seedExitPlans();
  if (seedAll || flags["post-mortems"]) seedPostMortems();

  console.log("Done.");
}

main();