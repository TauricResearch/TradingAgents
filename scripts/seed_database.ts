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
 * DB resolution (mirrors src/server/index.tsx):
 *   --db PATH         Explicit path (highest priority)
 *   PORTFOLIO_DB      DEV database path
 *   TEST_MODE=1       Uses TEST_PORTFOLIO_DB or ./test_portfolio.db
 *   default           ./portfolio.db
 */

import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"
import * as yaml from "js-yaml"
import { DatabaseFactory } from "../src/lib/db.ts"

const DEFAULT_DB = join(process.cwd(), "portfolio.db")
const POSITIONS_BASE = join(homedir(), ".tradingagents", "positions")
const POST_MORTEMS_DIR = join(homedir(), ".tradingagents", "post-mortems")

// ─── DB path resolution ──────────────────────────────────────────────────────

function resolveDbPath(explicitPath?: string): string {
  if (explicitPath) {
    const p = explicitPath.startsWith("/") ? explicitPath : join(process.cwd(), explicitPath)
    return p
  }
  if (process.env.PORTFOLIO_DB) return process.env.PORTFOLIO_DB
  if (process.env.TEST_MODE === "1") {
    return process.env.TEST_PORTFOLIO_DB ?? "./test_portfolio.db"
  }
  return DEFAULT_DB
}

// ─── SQLite helpers ──────────────────────────────────────────────────────────

// ─── Secret sanitization ─────────────────────────────────────────────────────

const SANITIZE_PATTERNS: [RegExp, string][] = [
  [/\bsk-[-A-Za-z0-9]{20,}/g, "[API_KEY_REMOVED]"],
  [/\bsk-ant(?:thropic)?[-][A-Za-z0-9]{20,}/gi, "[API_KEY_REMOVED]"],
  [/Bearer\s+[A-Za-z0-9_-]{10,}/g, "[TOKEN_REMOVED]"],
  [/https?:\/\/[^:\s]+:[^@\s]+@[^\s]+/g, "[URL_CREDS_REMOVED]"],
  [/(?:password|secret|apikey|api_key|token|auth)[=:]\s*[^\s;,]{8,}/gi, "[SECRET_REMOVED]"],
  [
    /-----BEGIN\s+(?:RSA|EC|OPENSSH|DSA|PRIVATE)\s+KEY-----[\s\S]*?-----END\s+\w+\s+KEY-----/g,
    "[PRIVATE_KEY_REMOVED]",
  ],
  [/[A-Fa-f0-9]{40,}/g, "[HEX_TOKEN_REMOVED]"],
]

function sanitize(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null
  let result = value
  for (const [pattern, replacement] of SANITIZE_PATTERNS) {
    result = result.replace(pattern, replacement)
  }
  return result
}

// ─── Date helpers ────────────────────────────────────────────────────────────

function d(weeks = 0, days = 0): string {
  const date = new Date()
  date.setDate(date.getDate() + weeks * 7 + days)
  return date.toISOString().split("T")[0]
}

// ─── Table clearing ──────────────────────────────────────────────────────────

function clearTable(table: string): void {
  const db = DatabaseFactory.get()
  if (table === "positions") {
    db.exec("DELETE FROM positions")
  } else if (table === "signals") {
    db.exec("DELETE FROM signals WHERE date BETWEEN '2026-01-01' AND '2026-04-01'")
  } else if (table === "watchlist") {
    db.exec("DELETE FROM watchlist WHERE platform = 'test'")
  } else if (table === "analyses") {
    db.exec("DELETE FROM analyses WHERE date BETWEEN '2026-01-01' AND '2026-04-01'")
  } else if (table === "prices") {
    db.exec("DELETE FROM prices")
  }
  console.log(`  Cleared ${table}`)
}

// ── Seed functions ──────────────────────────────────────────────────────────

function seedPositions(): void {
  clearTable("positions")

  const positions = [
    // degiero
    {
      ticker: "VWCE.DE",
      exchange: "XETRA",
      platform: "degiero",
      quantity: 35,
      avg_cost: 126.4,
      entry_date: d(-16),
      thesis: "All-world ETF accumulation — low-cost core holding",
      status: "open",
      notes: "Core satnav position. Accumulating quarterly.",
    },
    {
      ticker: "AAPL",
      exchange: "US",
      platform: "degiero",
      quantity: 25,
      avg_cost: 188.5,
      entry_date: d(-10),
      thesis: "Services segment compounding; Vision Pro ecosystem building",
      status: "open",
      notes: "Services margins 74%. WWDC catalyst watch.",
    },
    {
      ticker: "MSFT",
      exchange: "US",
      platform: "degiero",
      quantity: 20,
      avg_cost: 430.0,
      entry_date: d(-8),
      thesis: "Azure AI monetization accelerating; Copilot enterprise adoption strong",
      status: "open",
      notes: "GitHub Copilot 1.3M subscribers. Azure AI +30%.",
    },
    {
      ticker: "NVDA",
      exchange: "US",
      platform: "degiero",
      quantity: 15,
      avg_cost: 880.0,
      entry_date: d(-6),
      thesis: "AI infrastructure demand insatiable; H100/H200 supply constrained",
      status: "open",
      notes: "Blackwell architecture driving next wave.",
    },
    // ibkr
    {
      ticker: "AAPL",
      exchange: "US",
      platform: "ibkr",
      quantity: 150,
      avg_cost: 182.3,
      entry_date: d(-14),
      thesis: "Long-term AI services compounding — high conviction position",
      status: "open",
      notes: "High conviction. ~28% of ibkr portfolio (violates 15% max — to be trimmed).",
    },
    {
      ticker: "MSFT",
      exchange: "US",
      platform: "ibkr",
      quantity: 40,
      avg_cost: 408.0,
      entry_date: d(-7),
      thesis: "Cloud + AI platform play; GitHub Copilot enterprise roll-out",
      status: "open",
      notes: "GitHub Copilot enterprise rollout strong.",
    },
    {
      ticker: "TKA.DE",
      exchange: "XETRA",
      platform: "ibkr",
      quantity: 1000,
      avg_cost: 8.62,
      entry_date: d(-5),
      thesis: "German industrial automation; order pipeline strong for H2",
      status: "open",
      notes: "KONE partnership expected to close Q3.",
    },
    {
      ticker: "VWCE.DE",
      exchange: "XETRA",
      platform: "ibkr",
      quantity: 20,
      avg_cost: 133.2,
      entry_date: d(-4),
      thesis: "Core satnav ETF position alongside individual stock picks",
      status: "open",
      notes: "Core ETF alongside individual stock picks.",
    },
    // test
    {
      ticker: "AAPL",
      exchange: "US",
      platform: "test",
      quantity: 10,
      avg_cost: 192.0,
      entry_date: d(-3),
      thesis: "Testing signal accuracy — smaller position",
      status: "open",
      notes: "Test position — WWDC catalyst watch",
    },
    {
      ticker: "ETH",
      exchange: "CRYPTO",
      platform: "test",
      quantity: 0.5,
      avg_cost: 2850.0,
      entry_date: d(-2),
      thesis: "Crypto exposure test — ETH staking yield 3.8%",
      status: "open",
      notes: "Risk-off behaviour expected. Small position.",
    },
    {
      ticker: "TSLA",
      exchange: "US",
      platform: "test",
      quantity: 5,
      avg_cost: 245.0,
      entry_date: d(-1),
      thesis: "EV market share pressure; FSD licensing optionality",
      status: "open",
      notes: "Recent addition — watch for thesis invalidation",
    },
    {
      ticker: "VWCE.DE",
      exchange: "XETRA",
      platform: "test",
      quantity: 10,
      avg_cost: 132.0,
      entry_date: d(-3),
      thesis: "All-world ETF — low-cost core holding, accumulating",
      status: "open",
      notes: "Accumulating quarterly. MSCI World exposure.",
    },
  ]

  const db = DatabaseFactory.get()
  for (const p of positions) {
    db.run(
      `INSERT INTO positions (ticker, exchange, platform, quantity, avg_cost, entry_date, thesis, status, notes)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        p.ticker,
        p.exchange,
        p.platform,
        p.quantity,
        p.avg_cost,
        p.entry_date,
        sanitize(p.thesis),
        p.status,
        sanitize(p.notes),
      ],
    )
  }
  console.log(`  Inserted ${positions.length} positions`)
}

function seedSignals(): void {
  clearTable("signals")

  const signals = [
    {
      ticker: "VWCE.DE",
      platform: "degiero",
      date: d(-16),
      signal: "hold",
      confidence: 0.72,
      reasoning: "All-world ETF, low-cost, accumulating position. No thesis change.",
    },
    {
      ticker: "VWCE.DE",
      platform: "degiero",
      date: d(-12),
      signal: "hold",
      confidence: 0.7,
      reasoning: "MSCI World constituents strong. No need to rebalance.",
    },
    {
      ticker: "VWCE.DE",
      platform: "degiero",
      date: d(-8),
      signal: "overweight",
      confidence: 0.75,
      reasoning: "Q4 earnings beat. Global equity markets favouring developed market exposure.",
    },
    {
      ticker: "VWCE.DE",
      platform: "degiero",
      date: d(-4),
      signal: "buy",
      confidence: 0.78,
      reasoning: "Market dip provides entry opportunity. Accumulation phase continues.",
    },
    {
      ticker: "VWCE.DE",
      platform: "ibkr",
      date: d(-4),
      signal: "buy",
      confidence: 0.75,
      reasoning: "Core satnav position. Low-cost exposure to global equity.",
    },
    {
      ticker: "AAPL",
      platform: "test",
      date: d(-14),
      signal: "buy",
      confidence: 0.78,
      reasoning: "AI services integration driving margin expansion. Vision Pro ecosystem.",
    },
    {
      ticker: "AAPL",
      platform: "degiero",
      date: d(-10),
      signal: "hold",
      confidence: 0.7,
      reasoning: "Services revenue acceleration offset by iPhone softness. Hold.",
    },
    {
      ticker: "AAPL",
      platform: "degiero",
      date: d(-6),
      signal: "overweight",
      confidence: 0.8,
      reasoning: "WWDC catalyst identified. AI integration across device lineup strong.",
    },
    {
      ticker: "AAPL",
      platform: "degiero",
      date: d(-2),
      signal: "buy",
      confidence: 0.85,
      reasoning: "Services margins hit 74%. AI features driving upgrade cycle. Target raised.",
    },
    {
      ticker: "AAPL",
      platform: "ibkr",
      date: d(-14),
      signal: "buy",
      confidence: 0.82,
      reasoning: "Long-term AI compounding thesis. Larger position justified by conviction.",
    },
    {
      ticker: "AAPL",
      platform: "ibkr",
      date: d(-8),
      signal: "overweight",
      confidence: 0.78,
      reasoning: "Position overweight but thesis unchanged. Monitor for rebalancing.",
    },
    {
      ticker: "AAPL",
      platform: "ibkr",
      date: d(-3),
      signal: "buy",
      confidence: 0.88,
      reasoning: "Services segment 3-year CAGR 15%. Target price raised to $220.",
    },
    {
      ticker: "AAPL",
      platform: "test",
      date: d(-3),
      signal: "buy",
      confidence: 0.82,
      reasoning: "Signal accuracy test. AI services still primary driver.",
    },
    {
      ticker: "MSFT",
      platform: "degiero",
      date: d(-8),
      signal: "buy",
      confidence: 0.76,
      reasoning: "Azure AI monetization ahead of schedule. Copilot enterprise adoption.",
    },
    {
      ticker: "MSFT",
      platform: "degiero",
      date: d(-4),
      signal: "buy",
      confidence: 0.8,
      reasoning: "GitHub Copilot at 1.3M paid subscribers. Azure AI services revenue growing 30%.",
    },
    {
      ticker: "MSFT",
      platform: "ibkr",
      date: d(-7),
      signal: "buy",
      confidence: 0.75,
      reasoning: "Cloud + AI platform. GitHub Copilot enterprise rollout strong.",
    },
    {
      ticker: "MSFT",
      platform: "ibkr",
      date: d(-2),
      signal: "overweight",
      confidence: 0.79,
      reasoning: "Azure AI competitive moat widening. Target raised to $460.",
    },
    {
      ticker: "NVDA",
      platform: "degiero",
      date: d(-6),
      signal: "buy",
      confidence: 0.72,
      reasoning: "AI infrastructure spend insatiable. H100 supply constrained through Q2.",
    },
    {
      ticker: "NVDA",
      platform: "degiero",
      date: d(-2),
      signal: "overweight",
      confidence: 0.8,
      reasoning: "Blackwell architecture driving next wave. Data centre revenue +85%.",
    },
    {
      ticker: "TKA.DE",
      platform: "ibkr",
      date: d(-5),
      signal: "buy",
      confidence: 0.68,
      reasoning: "German industrial automation cycle bottoming. Order pipeline strong for H2.",
    },
    {
      ticker: "TKA.DE",
      platform: "ibkr",
      date: d(-1),
      signal: "buy",
      confidence: 0.73,
      reasoning: "KONE partnership accelerating revenue. Price target €10.50.",
    },
    {
      ticker: "TKA.DE",
      platform: "test",
      date: d(-16),
      signal: "sell",
      confidence: 0.55,
      reasoning: "Position too small for delisted tracking. Closed out.",
    },
    {
      ticker: "ETH",
      platform: "test",
      date: d(-2),
      signal: "buy",
      confidence: 0.6,
      reasoning: "Crypto exposure test. ETH staking yield 3.8%. Small position.",
    },
    {
      ticker: "TSLA",
      platform: "test",
      date: d(-1),
      signal: "underweight",
      confidence: 0.65,
      reasoning: "EV price war compressing margins. FSD licensing uncertain. Reduce.",
    },
    {
      ticker: "AAPL",
      platform: "ibkr",
      date: d(-26),
      signal: "buy",
      confidence: 0.75,
      reasoning: "Initial AAPL position entry",
    },
    {
      ticker: "AAPL",
      platform: "ibkr",
      date: d(-20),
      signal: "overweight",
      confidence: 0.8,
      reasoning: "AI integration thesis strengthening",
    },
    {
      ticker: "AAPL",
      platform: "ibkr",
      date: d(-16),
      signal: "hold",
      confidence: 0.72,
      reasoning: "Hold signal. Services growth stable.",
    },
    {
      ticker: "MSFT",
      platform: "degiero",
      date: d(-12),
      signal: "buy",
      confidence: 0.7,
      reasoning: "Initial MSFT position. Cloud + AI platform.",
    },
  ]

  const db = DatabaseFactory.get()
  for (const s of signals) {
    db.run(
      `INSERT INTO signals (ticker, platform, date, signal, reasoning, confidence)
       VALUES (?, ?, ?, ?, ?, ?)`,
      [s.ticker, s.platform, s.date, s.signal, sanitize(s.reasoning), String(s.confidence)],
    )
  }
  console.log(`  Inserted ${signals.length} signals`)
}

function seedWatchlist(): void {
  clearTable("watchlist")

  const watchlist = [
    {
      ticker: "GOOGL",
      platform: "degiero",
      exchange: "US",
      thesis: "Gemini Ultra competitive with GPT-4. Cloud growth accelerating.",
      priority: "high",
      stage: "analyzed",
    },
    {
      ticker: "AMZN",
      platform: "degiero",
      exchange: "US",
      thesis: "AWS AI services and Rufus e-commerce AI. Margin expansion.",
      priority: "high",
      stage: "candidate",
    },
    {
      ticker: "META",
      platform: "ibkr",
      exchange: "US",
      thesis: "Llama ecosystem and AI ad tools driving efficiency. Threads growth.",
      priority: "high",
      stage: "analyzed",
    },
    {
      ticker: "ASML",
      platform: "degiero",
      exchange: "EUR",
      thesis: "Lithography monopoly for advanced chips. AI capex beneficiaries.",
      priority: "medium",
      stage: "researching",
    },
    {
      ticker: "SAP",
      platform: "degiero",
      exchange: "EUR",
      thesis: "RISE with SAP transitioning to cloud. Joule AI assistant.",
      priority: "medium",
      stage: "researching",
    },
    {
      ticker: "BTC",
      platform: "test",
      exchange: "CRYPTO",
      thesis: "Bitcoin ETF inflows strong. Store of value narrative.",
      priority: "low",
      stage: "researching",
    },
    {
      ticker: "SOL",
      platform: "test",
      exchange: "CRYPTO",
      thesis: "Solana DeFi ecosystem growing. Low-cost transactions.",
      priority: "low",
      stage: "researching",
    },
    {
      ticker: "ARM",
      platform: "degiero",
      exchange: "US",
      thesis: "AI inference chip design. Royalty revenue growing.",
      priority: "medium",
      stage: "researching",
    },
  ]

  const db = DatabaseFactory.get()
  for (const w of watchlist) {
    db.run(
      `INSERT INTO watchlist (ticker, exchange, platform, thesis, priority, stage, added_date)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [w.ticker, w.exchange, w.platform, sanitize(w.thesis), w.priority, w.stage, d(-8)],
    )
  }
  console.log(`  Inserted ${watchlist.length} watchlist items`)
}

function seedAnalyses(): void {
  clearTable("analyses")

  const analyses = [
    {
      ticker: "AAPL",
      platform: "degiero",
      date: d(-10),
      decision:
        "Hold — Services revenue acceleration confirmed at 74% margins. iPhone softness offset by AI-driven upgrade cycle. Confidence 0.70.",
    },
    {
      ticker: "AAPL",
      platform: "ibkr",
      date: d(-14),
      decision:
        "Buy (overweight) — AI services compounding thesis strong. Position size justified by high conviction. Confidence 0.82.",
    },
    {
      ticker: "MSFT",
      platform: "degiero",
      date: d(-8),
      decision:
        "Buy — Azure AI monetization ahead of schedule. Copilot enterprise adoption exceeding targets. Confidence 0.76.",
    },
    {
      ticker: "NVDA",
      platform: "degiero",
      date: d(-6),
      decision:
        "Buy — AI infrastructure demand insatiable. H100 supply constrained. Confidence 0.72.",
    },
    {
      ticker: "TKA.DE",
      platform: "ibkr",
      date: d(-5),
      decision:
        "Buy — German industrial cycle bottoming. KONE deal pipeline strong. Confidence 0.68.",
    },
    {
      ticker: "VWCE.DE",
      platform: "degiero",
      date: d(-4),
      decision: "Buy — Market dip entry opportunity. Accumulation continues. Confidence 0.78.",
    },
    {
      ticker: "AAPL",
      platform: "degiero",
      date: d(-2),
      decision:
        "Buy — WWDC catalyst. AI features across device lineup strong. Target raised. Confidence 0.85.",
    },
  ]

  const db = DatabaseFactory.get()
  for (const a of analyses) {
    db.run(`INSERT INTO analyses (ticker, platform, date, decision) VALUES (?, ?, ?, ?)`, [
      a.ticker,
      a.platform,
      a.date,
      a.decision,
    ])
  }
  console.log(`  Inserted ${analyses.length} analyses`)
}

function seedExitPlans(): void {
  interface ExitPlan {
    platform: string
    ticker: string
    entry_price: number
    quantity: number
    entry_date: string
    thesis: string
    invalidation_price: number
    invalidation_thesis: string
    targets: Array<{ price: number; label: string; fraction: number }>
    time_stop: string
    notes?: string
  }

  const plans: ExitPlan[] = [
    {
      platform: "degiero",
      ticker: "VWCE.DE",
      entry_price: 126.4,
      quantity: 35,
      entry_date: d(-16),
      thesis: "All-world ETF accumulation — low-cost core holding",
      invalidation_price: 113.76,
      invalidation_thesis: "Global equity bear market; MSCI World -15% from peak",
      targets: [
        { price: 142.0, label: "Target 1: +12%", fraction: 0.33 },
        { price: 158.0, label: "Target 2: +25%", fraction: 0.33 },
        { price: 175.0, label: "Target 3: +38%", fraction: 0.34 },
      ],
      time_stop: d(0, 180),
      notes: "Accumulating quarterly. No rush to exit core ETF position.",
    },
    {
      platform: "degiero",
      ticker: "AAPL",
      entry_price: 188.5,
      quantity: 25,
      entry_date: d(-10),
      thesis: "Services segment compounding; Vision Pro ecosystem building",
      invalidation_price: 160.0,
      invalidation_thesis: "Services growth below 10% YoY — core thesis broken",
      targets: [
        { price: 220.0, label: "Target 1: +17%", fraction: 0.33 },
        { price: 250.0, label: "Target 2: +33%", fraction: 0.33 },
        { price: 280.0, label: "Target 3: +49%", fraction: 0.34 },
      ],
      time_stop: d(0, 120),
      notes: "Watch WWDC (June) for AI catalyst.",
    },
    {
      platform: "degiero",
      ticker: "MSFT",
      entry_price: 430.0,
      quantity: 20,
      entry_date: d(-8),
      thesis: "Azure AI monetization accelerating; Copilot enterprise adoption strong",
      invalidation_price: 387.0,
      invalidation_thesis: "Azure growth decelerates below 25% YoY",
      targets: [
        { price: 502.0, label: "Target 1: +17%", fraction: 0.5 },
        { price: 580.0, label: "Target 2: +35%", fraction: 0.5 },
      ],
      time_stop: d(0, 150),
    },
    {
      platform: "degiero",
      ticker: "NVDA",
      entry_price: 880.0,
      quantity: 15,
      entry_date: d(-6),
      thesis: "AI infrastructure demand insatiable; H100/H200 supply constrained",
      invalidation_price: 748.0,
      invalidation_thesis: "Data centre spend cuts; AMD MI300X competitive threat",
      targets: [
        { price: 1056.0, label: "Target 1: +20%", fraction: 0.5 },
        { price: 1320.0, label: "Target 2: +50%", fraction: 0.5 },
      ],
      time_stop: d(0, 180),
    },
    {
      platform: "ibkr",
      ticker: "AAPL",
      entry_price: 182.3,
      quantity: 150,
      entry_date: d(-14),
      thesis: "Long-term AI services compounding — high conviction position",
      invalidation_price: 155.0,
      invalidation_thesis: "Services growth below 12%; antitrust risk materialises",
      targets: [
        { price: 215.0, label: "Target 1: +18%", fraction: 0.33 },
        { price: 250.0, label: "Target 2: +37%", fraction: 0.33 },
        { price: 290.0, label: "Target 3: +59%", fraction: 0.34 },
      ],
      time_stop: d(0, 240),
      notes:
        "NOTE: Position is ~28% of ibkr portfolio — violates max-position rule (15%). Should trim to 65 shares.",
    },
    {
      platform: "ibkr",
      ticker: "MSFT",
      entry_price: 408.0,
      quantity: 40,
      entry_date: d(-7),
      thesis: "Cloud + AI platform play; GitHub Copilot enterprise roll-out",
      invalidation_price: 347.0,
      invalidation_thesis: "Azure decelerates; Copilot adoption below targets",
      targets: [
        { price: 480.0, label: "Target 1: +18%", fraction: 0.5 },
        { price: 550.0, label: "Target 2: +35%", fraction: 0.5 },
      ],
      time_stop: d(0, 180),
    },
    {
      platform: "ibkr",
      ticker: "TKA.DE",
      entry_price: 8.62,
      quantity: 1000,
      entry_date: d(-5),
      thesis: "German industrial automation; order pipeline strong for H2",
      invalidation_price: 7.33,
      invalidation_thesis: "Order intake negative; Chinese competition eroding margins",
      targets: [
        { price: 10.35, label: "Target 1: +20%", fraction: 0.5 },
        { price: 12.08, label: "Target 2: +40%", fraction: 0.5 },
      ],
      time_stop: d(0, 120),
      notes: "KONE partnership expected to close Q3.",
    },
    {
      platform: "ibkr",
      ticker: "VWCE.DE",
      entry_price: 133.2,
      quantity: 20,
      entry_date: d(-4),
      thesis: "Core satnav ETF position alongside individual stock picks",
      invalidation_price: 113.22,
      invalidation_thesis: "Global equity drawdown > 15%",
      targets: [
        { price: 146.52, label: "Target 1: +10%", fraction: 0.5 },
        { price: 159.84, label: "Target 2: +20%", fraction: 0.5 },
      ],
      time_stop: d(0, 180),
    },
    {
      platform: "test",
      ticker: "AAPL",
      entry_price: 192.0,
      quantity: 10,
      entry_date: d(-3),
      thesis: "Testing signal accuracy — smaller position",
      invalidation_price: 163.2,
      invalidation_thesis: "Services growth below 10%",
      targets: [
        { price: 225.0, label: "Target 1: +17%", fraction: 0.5 },
        { price: 268.0, label: "Target 2: +40%", fraction: 0.5 },
      ],
      time_stop: d(0, 120),
    },
    {
      platform: "test",
      ticker: "ETH",
      entry_price: 2850.0,
      quantity: 0.5,
      entry_date: d(-2),
      thesis: "Crypto exposure test — ETH staking yield 3.8%",
      invalidation_price: 2280.0,
      invalidation_thesis: "Ethereum mainnet failure; regulatory crackdown",
      targets: [
        { price: 3420.0, label: "Target 1: +20%", fraction: 0.5 },
        { price: 4275.0, label: "Target 2: +50%", fraction: 0.5 },
      ],
      time_stop: d(0, 90),
      notes: "Risk-off behaviour expected. Small position.",
    },
    {
      platform: "test",
      ticker: "TSLA",
      entry_price: 245.0,
      quantity: 5,
      entry_date: d(-1),
      thesis: "EV market share pressure; FSD licensing optionality",
      invalidation_price: 208.25,
      invalidation_thesis: "Margin compression below -5%; FSD delays",
      targets: [
        { price: 294.0, label: "Target 1: +20%", fraction: 0.5 },
        { price: 343.0, label: "Target 2: +40%", fraction: 0.5 },
      ],
      time_stop: d(0, 90),
    },
  ]

  // Clear existing YAML plans
  for (const platform of ["degiero", "ibkr", "test"]) {
    const dirPath = join(POSITIONS_BASE, platform)
    if (existsSync(dirPath)) {
      for (const file of readdirSync(dirPath).filter((n) => n.endsWith(".yaml"))) {
        const filePath = join(dirPath, file)
        unlinkSync(filePath)
      }
    }
  }

  for (const plan of plans) {
    const dirPath = join(POSITIONS_BASE, plan.platform)
    mkdirSync(dirPath, { recursive: true })

    // Serialize to YAML via js-yaml
    const yamlOut = yaml.dump(plan, { defaultFlowStyle: false, sortKeys: false })

    writeFileSync(join(dirPath, `${plan.ticker}.yaml`), yamlOut)
  }
  console.log(`  Wrote ${plans.length} exit plan YAML files`)
}

function seedPostMortems(): void {
  interface PostMortem {
    ticker: string
    platform: string
    exit_date: string
    entry_price: number
    exit_price: number
    thesis: string
    thesis_played_out: boolean
    ai_signal_correct: boolean
    exit_trigger: string
    lesson: string
  }

  const postMortems: PostMortem[] = [
    {
      ticker: "AAPL",
      platform: "ibkr",
      exit_date: d(-22),
      entry_price: 175.0,
      exit_price: 198.5,
      thesis: "Long-term AI services compounding — initial position entry",
      thesis_played_out: true,
      ai_signal_correct: true,
      exit_trigger: "target",
      lesson:
        "First target hit at +13.4%. Thesis unchanged — allowed to run to second target. Correct patience. AI signal (buy, 0.75) proved accurate. Exited 1/3 at first target, rode remainder.",
    },
    {
      ticker: "MSFT",
      platform: "ibkr",
      exit_date: d(-12),
      entry_price: 392.0,
      exit_price: 451.0,
      thesis: "Cloud + AI platform. GitHub Copilot enterprise rollout",
      thesis_played_out: true,
      ai_signal_correct: true,
      exit_trigger: "target",
      lesson:
        "Azure AI services revenue +30% QoQ confirmed. Copilot adoption strong. Exited full position at +15%. AI signal (buy, 0.70) fully justified. No regrets on exit timing.",
    },
    {
      ticker: "AAPL",
      platform: "ibkr",
      exit_date: d(-18),
      entry_price: 178.5,
      exit_price: 172.0,
      thesis: "Overweight — position size increased",
      thesis_played_out: false,
      ai_signal_correct: false,
      exit_trigger: "manual",
      lesson:
        "Thesis partially played out but position thesis (overweight) correct. Sold 30 shares at breakeven to reduce exposure. AI signal (overweight, 0.80) was too aggressive for position size. Rule: never increase conviction AND size simultaneously.",
    },
    {
      ticker: "TKA.DE",
      platform: "test",
      exit_date: d(-16),
      entry_price: 9.8,
      exit_price: 7.2,
      thesis: "Position too small for delisted tracking. Closed out.",
      thesis_played_out: false,
      ai_signal_correct: false,
      exit_trigger: "stop",
      lesson:
        "Stop loss correctly triggered at -26.5%. Thesis (delisted tracking) was wrong. Exit at stop was correct — saved remaining capital. AI signal (sell, 0.55) was low-confidence and correct.",
    },
  ]

  mkdirSync(POST_MORTEMS_DIR, { recursive: true })

  for (const pm of postMortems) {
    const retRaw = ((pm.exit_price - pm.entry_price) / pm.entry_price) * 100
    const ret = `${retRaw >= 0 ? "+" : ""}${retRaw.toFixed(1)}%`
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
`
    const filename = `${pm.exit_date.replace(/-/g, "")}-${pm.ticker}.md`
    writeFileSync(join(POST_MORTEMS_DIR, filename), content)
  }
  console.log(`  Wrote ${postMortems.length} post-mortems`)
}

// ─── Main ────────────────────────────────────────────────────────────────────

interface CliFlags {
  db?: string
  accounts?: boolean
  positions?: boolean
  signals?: boolean
  watchlist?: boolean
  analyses?: boolean
  "exit-plans"?: boolean
  "post-mortems"?: boolean
  "spread-bets"?: boolean
  "account-balances"?: boolean
  prices?: boolean
  all?: boolean
}

function parseArgs(): CliFlags {
  const args = Bun.argv.slice(2)
  const flags: CliFlags = {}
  let i = 0
  while (i < args.length) {
    const arg = args[i]
    if (arg === "--db") {
      flags.db = args[++i]
    } else if (arg === "--accounts") {
      flags.accounts = true
    } else if (arg === "--positions") {
      flags.positions = true
    } else if (arg === "--signals") {
      flags.signals = true
    } else if (arg === "--watchlist") {
      flags.watchlist = true
    } else if (arg === "--analyses") {
      flags.analyses = true
    } else if (arg === "--exit-plans") {
      flags["exit-plans"] = true
    } else if (arg === "--post-mortems") {
      flags["post-mortems"] = true
    } else if (arg === "--spread-bets") {
      flags["spread-bets"] = true
    } else if (arg === "--account-balances") {
      flags["account-balances"] = true
    } else if (arg === "--prices") {
      flags.prices = true
    } else if (arg === "--all") {
      flags.all = true
    } else if (!arg.startsWith("-")) {
      /* positional, ignore */
    }
    i++
  }
  return flags
}

// ─── Price seeding ──────────────────────────────────────────────────────────

interface PriceBar {
  date: string
  open: number | null
  high: number | null
  low: number | null
  close: number
  volume: number | null
}

async function seedPrices(): Promise<void> {
  const db = DatabaseFactory.get()

  // Get unique tickers from open positions
  const rows = db.query("SELECT DISTINCT ticker FROM positions WHERE status = 'open'").all() as {
    ticker: string
  }[]

  if (rows.length === 0) {
    console.log("  No open positions — nothing to seed prices for")
    return
  }

  console.log(`  Fetching prices for ${rows.length} tickers...`)

  // Fetch FX rates once and build gbp_rate map
  let gbpRateMap: Record<string, number> = { USD: 1, EUR: 1, GBP: 1 }
  try {
    const port = process.env.TA_DASHBOARD_PORT ?? "3000"
    const fxProc = Bun.spawnSync({
      cmd: ["curl", "-sf", `http://localhost:${port}/api/portfolio/fx-rates`],
      stdout: "pipe",
      stderr: "pipe",
    })
    if (fxProc.exitCode === 0) {
      const fx = JSON.parse(new TextDecoder().decode(fxProc.stdout)) as {
        GBPUSD?: number
        GBPEUR?: number
      }
      gbpRateMap = {
        USD: fx.GBPUSD ? 1 / fx.GBPUSD : 1,
        EUR: fx.GBPEUR ? 1 / fx.GBPEUR : 1,
        GBP: 1,
      }
    }
  } catch {
    // Use fallback rates
  }

  const insertStmt = db.prepare(`
    INSERT OR REPLACE INTO prices (ticker, date, open, high, low, close, volume, currency, gbp_rate)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `)

  for (const { ticker } of rows) {
    const proc = Bun.spawnSync({
      cmd: ["bun", "run", join(__dirname, "get_price.ts"), ticker],
      stdout: "pipe",
      stderr: "pipe",
    })

    if (proc.exitCode !== 0) {
      const err = new TextDecoder().decode(proc.stderr)
      console.error(`    ${ticker}: fetch failed — ${err.trim()}`)
      continue
    }

    let data: { history: PriceBar[]; currency?: string }
    try {
      data = JSON.parse(new TextDecoder().decode(proc.stdout))
    } catch {
      console.error(`    ${ticker}: invalid JSON response`)
      continue
    }

    const currency = data.currency ?? "USD"
    const gbpRate = gbpRateMap[currency] ?? null
    const history = data.history ?? []
    for (const bar of history) {
      insertStmt.run(
        ticker,
        bar.date,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
        currency,
        gbpRate,
      )
    }

    console.log(`    ${ticker}: ${history.length} bars seeded`)
  }
}

// ─── Main ────────────────────────────────────────────────────────────────────

// ─── Account seeding ───────────────────────────────────────────────────────

function seedAccounts(): void {
  const db = DatabaseFactory.get()
  db.exec(
    "DELETE FROM spreadbet_positions WHERE account_id LIKE 'ig-%' OR account_id = 'aviva' OR account_id = 'ajbell'",
  )
  db.exec(
    "DELETE FROM positions WHERE account_id LIKE 'ig-%' OR account_id = 'aviva' OR account_id = 'ajbell'",
  )
  db.exec(
    "DELETE FROM account_balances WHERE account_id LIKE 'ig-%' OR account_id = 'aviva' OR account_id = 'ajbell' OR account_id = 'nsandi' OR account_id = 'cash-other'",
  )
  db.exec(
    "DELETE FROM accounts WHERE id LIKE 'ig-%' OR id = 'aviva' OR id = 'ajbell' OR id = 'nsandi' OR id = 'cash-other'",
  )

  const accounts = [
    {
      id: "ig-isa",
      provider: "IG",
      account_type: "isa",
      name: "IG ISA",
      balance: 5000,
      currency: "GBP",
      notes: "Tax-free growth wrapper. Primary accumulation vehicle.",
    },
    {
      id: "ig-shares",
      provider: "IG",
      account_type: "shares",
      name: "IG Share Dealing",
      balance: 2000,
      currency: "GBP",
      notes: "CGT taxable. Used for positions exceeding ISA allowance.",
    },
    {
      id: "ig-spreadbet",
      provider: "IG",
      account_type: "spreadbet",
      name: "IG Spread Betting",
      balance: 10000,
      currency: "GBP",
      notes: "Tax-free betting account. Separate allocation (20%).",
    },
    {
      id: "aviva",
      provider: "Aviva",
      account_type: "sipp",
      name: "Aviva Pension",
      balance: 25000,
      currency: "GBP",
      notes: "Group workplace pension. Access from age 55.",
    },
    {
      id: "ajbell",
      provider: "AJ Bell",
      account_type: "sipp",
      name: "AJ Bell SIPP",
      balance: 15000,
      currency: "GBP",
      notes: "Self-invested personal pension. Drawdown planning.",
    },
    {
      id: "nsandi",
      provider: "NS&I",
      account_type: "savings",
      name: "NS&I Premium Bonds",
      balance: 15000,
      currency: "GBP",
      notes: "UK government savings. Manual balance update monthly.",
    },
    {
      id: "cash-other",
      provider: "Other",
      account_type: "cash",
      name: "Cash & Savings",
      balance: 8000,
      currency: "GBP",
      notes: "Bank accounts + legacy pots. Emergency fund.",
    },
  ]

  for (const a of accounts) {
    db.run(
      `INSERT OR REPLACE INTO accounts (id, provider, account_type, name, balance, currency, notes)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [a.id, a.provider, a.account_type, a.name, a.balance, a.currency, a.notes],
    )
  }
  console.log(`  Inserted ${accounts.length} accounts`)
}

// ─── Spread bet seeding ──────────────────────────────────────────────────────

function seedSpreadBets(): void {
  const db = DatabaseFactory.get()
  db.exec("DELETE FROM spreadbet_positions WHERE account_id = 'ig-spreadbet'")

  const bets = [
    {
      account_id: "ig-spreadbet",
      ticker: "AAPL",
      direction: "short",
      stake_per_point: 2,
      entry_price: 195.0,
      entry_date: d(-2),
      stop_price: 210.0,
      target_price: 170.0,
      status: "open",
      notes: "Short AAPL ahead of earnings risk.",
    },
    {
      account_id: "ig-spreadbet",
      ticker: "BTC",
      direction: "long",
      stake_per_point: 1,
      entry_price: 62000,
      entry_date: d(-1),
      stop_price: 55000,
      target_price: 75000,
      status: "open",
      notes: "BTC long on ETF inflows thesis.",
    },
  ]

  for (const b of bets) {
    db.run(
      `INSERT INTO spreadbet_positions (account_id, ticker, direction, stake_per_point, entry_price, entry_date, stop_price, target_price, status, notes)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        b.account_id,
        b.ticker,
        b.direction,
        b.stake_per_point,
        b.entry_price,
        b.entry_date,
        b.stop_price,
        b.target_price,
        b.status,
        sanitize(b.notes),
      ],
    )
  }
  console.log(`  Inserted ${bets.length} spread bet positions`)
}

// ─── Account balance history seeding ─────────────────────────────────────────

function seedAccountBalances(): void {
  const db = DatabaseFactory.get()
  db.exec("DELETE FROM account_balances WHERE account_id IN ('nsandi','cash-other')")

  const balances = [
    { account_id: "nsandi", balance: 15000, date: d(0, -30), note: "Monthly balance check" },
    { account_id: "nsandi", balance: 14850, date: d(0, -60), note: "Previous month" },
    { account_id: "cash-other", balance: 8000, date: d(0, -15), note: "Current cash position" },
    { account_id: "cash-other", balance: 9000, date: d(0, -45), note: "Previous cash position" },
  ]

  for (const b of balances) {
    db.run(`INSERT INTO account_balances (account_id, balance, date, note) VALUES (?, ?, ?, ?)`, [
      b.account_id,
      b.balance,
      b.date,
      b.note,
    ])
  }
  console.log(`  Inserted ${balances.length} account balance history entries`)
}

async function main() {
  const flags = parseArgs()
  const dbPath = resolveDbPath(flags.db)

  const db = DatabaseFactory.connect(dbPath)

  // Auto-apply schema (CREATE TABLE IF NOT EXISTS is idempotent)
  const schemaPath = join(__dirname, "..", "server", "lib", "schema.sql")
  if (existsSync(schemaPath)) {
    db.exec(readFileSync(schemaPath, "utf-8"))
  }

  // Migration: add stage column to watchlist if missing
  try {
    db.exec(
      "ALTER TABLE watchlist ADD COLUMN stage TEXT DEFAULT 'researching' CHECK(stage IN ('researching', 'analyzed', 'candidate', 'approved', 'acquired'))",
    )
  } catch (err) {
    if (!(err instanceof Error) || !/duplicate column name|already exists/i.test(err.message)) {
      throw err
    }
  }

  // Migration: add account_id column to positions if missing
  try {
    db.exec("ALTER TABLE positions ADD COLUMN account_id TEXT REFERENCES accounts(id)")
  } catch (err) {
    if (!(err instanceof Error) || !/duplicate column name|already exists/i.test(err.message)) {
      throw err
    }
  }

  // Migration: add positions account index if missing
  try {
    db.exec("CREATE INDEX idx_positions_account ON positions(account_id)")
  } catch (err) {
    if (!(err instanceof Error) || !/already exists/i.test(err.message)) {
      throw err
    }
  }

  const seedAll =
    !flags.accounts &&
    !flags.positions &&
    !flags.signals &&
    !flags.watchlist &&
    !flags.analyses &&
    !flags["exit-plans"] &&
    !flags["post-mortems"] &&
    !flags["spread-bets"] &&
    !flags["account-balances"] &&
    !flags.prices

  const isTest = dbPath.includes("test")
  console.log(`Seeding TradingAgents database${isTest ? " [TEST MODE]" : ""}...`)
  console.log(`  Target DB: ${dbPath}`)

  if (seedAll || flags.accounts) seedAccounts()
  if (seedAll || flags.positions) seedPositions()
  // --prices needs positions to exist first
  if (flags.prices && !seedAll && !flags.positions) seedPositions()
  if (seedAll || flags.signals) seedSignals()
  if (seedAll || flags.watchlist) seedWatchlist()
  if (seedAll || flags.analyses) seedAnalyses()
  if (seedAll || flags["exit-plans"]) seedExitPlans()
  if (seedAll || flags["post-mortems"]) seedPostMortems()
  if (seedAll || flags["spread-bets"]) seedSpreadBets()
  if (seedAll || flags["account-balances"]) seedAccountBalances()
  if (seedAll || flags.prices) await seedPrices()

  console.log("Done.")
}

main().catch((err) => {
  console.error("seed_database failed:", err)
  process.exit(1)
})
