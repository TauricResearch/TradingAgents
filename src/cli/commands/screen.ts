#!/usr/bin/env bun

/**
 * Screen — watchlist curation: rules, enrichment, screening, sentiment.
 *
 * Subcommands:
 *   screen create    — add a screening rule
 *   screen list      — list screening rules
 *   screen delete    — delete a screening rule
 *   screen enrich    — fetch and store fundamental enrichment data
 *   screen run       — evaluate screening rules against watchlist
 *   screen sentiment — fetch and score news headlines
 *   screen history   — show recent screening runs
 */

import { DatabaseFactory } from "@lib/db"
import { cfg } from "@lib/settings"
import {
  createScreeningRule,
  deleteScreeningRule,
  getLatestEnrichment,
  getRecentScreenings,
  insertSentiment,
  listScreeningRules,
  pruneOldSentiment,
  type ScreenCondition,
  saveScreeningHistory,
  upsertEnrichment,
} from "@server/lib/screening-data"
import { type CandidateData, screenCandidates } from "@server/lib/screening-engine"
import { defineCommand } from "citty"

// ── Helpers ──────────────────────────────────────────────────────────────────

function color(text: string, code: string): string {
  return `${code}${text}\x1b[0m`
}

function green(text: string) {
  return color(text, "\x1b[32m")
}
function red(text: string) {
  return color(text, "\x1b[31m")
}
function yellow(text: string) {
  return color(text, "\x1b[33m")
}

// ── Create ───────────────────────────────────────────────────────────────────

const createCommand = defineCommand({
  meta: { name: "create", description: "Create a screening rule" },
  args: {
    name: { type: "positional", required: true, description: "Rule name" },
    "--conditions": { type: "string", required: true, description: "JSON array of conditions" },
    "--description": { type: "string", description: "Rule description" },
    "--priority": { type: "string", description: "Priority (default: 0)" },
  },
  run: (ctx) => {
    DatabaseFactory.connect(cfg.portfolio.db)

    let conditions: ScreenCondition[]
    try {
      conditions = JSON.parse(ctx.args.conditions as string)
    } catch {
      console.error(red("Error: --conditions must be valid JSON array"))
      process.exit(1)
    }

    if (!Array.isArray(conditions)) {
      console.error(red("Error: --conditions must be an array"))
      process.exit(1)
    }

    const priority = parseInt((ctx.args.priority as string) ?? "0", 10)
    const id = createScreeningRule(
      ctx.args.name as string,
      conditions,
      ctx.args.description as string | undefined,
      priority,
    )

    console.log(green(`Created screening rule #${id}: ${ctx.args.name}`))
  },
})

// ── List ─────────────────────────────────────────────────────────────────────

const listCommand = defineCommand({
  meta: { name: "list", description: "List screening rules" },
  args: {},
  run: () => {
    DatabaseFactory.connect(cfg.portfolio.db)

    const rules = listScreeningRules()

    if (rules.length === 0) {
      console.log("No screening rules defined.")
      console.log("Run: trading screen create <name> --conditions '[{...}]'")
      return
    }

    const wId = 4
    const wName = 25
    const wCond = 40
    const wEnabled = 9

    console.log("")
    console.log("SCREENING RULES")
    console.log("─".repeat(90))
    console.log(
      `${"#".padEnd(wId)} ${"Name".padEnd(wName)} ${"Conditions".padEnd(wCond)} ${"Priority".padEnd(8)} ${"Enabled".padEnd(wEnabled)} Description`,
    )
    console.log("─".repeat(90))

    for (const r of rules) {
      const enabledColor = r.enabled ? green("yes") : red("no")
      const condStr = JSON.stringify(r.conditions).slice(0, 38)
      const descStr = r.description ? r.description.slice(0, 30) : "—"

      console.log(
        `${String(r.id).padEnd(wId)} ${r.name.padEnd(wName)} ${condStr.padEnd(wCond)} ${String(r.priority).padEnd(8)} ${enabledColor} ${descStr}`,
      )
    }

    console.log("")
    console.log(`${rules.length} rule(s)`)
  },
})

// ── Delete ───────────────────────────────────────────────────────────────────

const deleteCommand = defineCommand({
  meta: { name: "delete", description: "Delete a screening rule" },
  args: {
    id: { type: "positional", required: true, description: "Rule ID" },
  },
  run: (ctx) => {
    DatabaseFactory.connect(cfg.portfolio.db)

    const id = parseInt(ctx.args.id as string, 10)
    if (Number.isNaN(id)) {
      console.error(red("Error: id must be a number"))
      process.exit(1)
    }

    const deleted = deleteScreeningRule(id)
    if (deleted) {
      console.log(green(`Deleted rule #${id}`))
    } else {
      console.error(red(`Rule #${id} not found`))
      process.exit(1)
    }
  },
})

// ── Enrich ───────────────────────────────────────────────────────────────────

const enrichCommand = defineCommand({
  meta: { name: "enrich", description: "Fetch and store fundamental enrichment data" },
  args: {
    "--ticker": { type: "string", description: "Specific ticker" },
    "--all": { type: "boolean", description: "Enrich all watchlist candidates" },
  },
  run: async (ctx) => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    // Get tickers
    let tickers: string[] = []
    if (ctx.args.ticker) {
      tickers = [ctx.args.ticker as string]
    } else if (ctx.args.all) {
      const rows = db.query("SELECT DISTINCT ticker FROM watchlist").all() as Array<{
        ticker: string
      }>
      tickers = rows.map((r) => r.ticker)
    } else {
      console.error(red("Error: specify --ticker <TICKER> or --all"))
      process.exit(1)
    }

    console.log(`Enriching ${tickers.length} ticker(s)...`)
    const today = new Date().toISOString().split("T")[0]

    for (const ticker of tickers) {
      try {
        // Fetch from Yahoo Finance via yfinance Python
        const result = await enrichFromYahoo(ticker)
        if (result) {
          upsertEnrichment({ ticker, fetch_date: today, ...result, source: "yahoo_finance" })
          console.log(green(`  ${ticker}: enriched`))
        } else {
          console.log(yellow(`  ${ticker}: no data available`))
        }
      } catch (err) {
        console.error(red(`  ${ticker}: ${err}`))
      }
    }

    console.log(green("Enrichment complete."))
  },
})

// ── Run ──────────────────────────────────────────────────────────────────────

const runCommand = defineCommand({
  meta: { name: "run", description: "Run screening rules against watchlist" },
  args: {
    "--json": { type: "boolean", description: "Output as JSON" },
    "--stage": { type: "string", description: "Filter by stage (comma-separated)" },
  },
  run: async (ctx) => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    // Load rules
    const rules = listScreeningRules()

    // Load candidates with enrichment
    const candidateRows = db
      .query(
        `SELECT w.ticker, w.exchange, w.stage, w.priority, e.*
         FROM watchlist w
         LEFT JOIN watchlist_enrichment e ON w.ticker = e.ticker
         WHERE w.stage != 'acquired'
         ORDER BY w.priority DESC, w.ticker`,
      )
      .all() as Array<
      { ticker: string; exchange: string; stage: string; priority: string } & Record<
        string,
        unknown
      >
    >

    const stageFilter = ctx.args.stage
      ? (ctx.args.stage as string).split(",").map((s: string) => s.trim())
      : undefined

    const candidates: CandidateData[] = candidateRows.map((r) => ({
      ticker: r.ticker,
      exchange: r.exchange,
      stage: r.stage,
      priority: r.priority,
      enrichment: r.fetch_date
        ? {
            ticker: r.ticker,
            fetch_date: r.fetch_date as string,
            pe_forward: r.pe_forward as number | null,
            eps_growth_1y: r.eps_growth_1y as number | null,
            operating_margin: r.operating_margin as number | null,
            beta_1y: r.beta_1y as number | null,
            price_to_sales: r.price_to_sales as number | null,
            sector: r.sector as string | null,
            region: r.region as string | null,
            source: r.source as string,
            created_at: r.created_at as string,
          }
        : null,
    }))

    const result = screenCandidates({ candidates, rules, stageFilter })

    if (ctx.args.json) {
      console.log(JSON.stringify(result, null, 2))
      return
    }

    if (result.matches.length === 0) {
      console.log("No candidates match current screening rules.")
      return
    }

    // Save history
    const matchedTickers = result.matches.map((m) => m.ticker)
    saveScreeningHistory(matchedTickers, result.rules_evaluated)

    // Output table
    const wTicker = 12
    const wStage = 12
    const wScore = 8
    const wRules = 15
    const wReasons = 35

    console.log("")
    console.log("SCREENING RESULTS")
    console.log("─".repeat(100))
    console.log(
      `${"Ticker".padEnd(wTicker)} ${"Stage".padEnd(wStage)} ${"Score".padEnd(wScore)} ${"Matched Rules".padEnd(wRules)} Reasons`,
    )
    console.log("─".repeat(100))

    for (const m of result.matches) {
      const rulesStr = m.matched_rules.join(", ")
      const reasonsStr = m.match_reasons[0] ?? "—"

      console.log(
        `${m.ticker.padEnd(wTicker)} ${m.stage.padEnd(wStage)} ${String(m.priority_score).padEnd(wScore)} ${rulesStr.padEnd(wRules)} ${reasonsStr.slice(0, wReasons)}`,
      )
    }

    console.log("")
    console.log(
      `${result.matched_count}/${result.total_candidates} candidates matched (${result.rules_evaluated} rules evaluated)`,
    )
  },
})

// ── Sentiment ─────────────────────────────────────────────────────────────────

const sentimentCommand = defineCommand({
  meta: { name: "sentiment", description: "Fetch and score news headlines for tickers" },
  args: {
    "--ticker": { type: "string", description: "Specific ticker" },
    "--all": { type: "boolean", description: "Process all watchlist candidates" },
  },
  run: async (ctx) => {
    DatabaseFactory.connect(cfg.portfolio.db)

    const db = DatabaseFactory.get()
    let tickers: string[] = []

    if (ctx.args.ticker) {
      tickers = [ctx.args.ticker as string]
    } else if (ctx.args.all) {
      const rows = db.query("SELECT DISTINCT ticker FROM watchlist").all() as Array<{
        ticker: string
      }>
      tickers = rows.map((r) => r.ticker)
    } else {
      console.error(red("Error: specify --ticker <TICKER> or --all"))
      process.exit(1)
    }

    // Prune old headlines first
    const pruned = pruneOldSentiment(30)
    if (pruned > 0) console.log(`Pruned ${pruned} old headline(s)`)

    console.log(`Fetching headlines for ${tickers.length} ticker(s)...`)

    for (const ticker of tickers) {
      try {
        const enrichment = getLatestEnrichment(ticker)
        if (!enrichment) {
          console.log(yellow(`  ${ticker}: no enrichment data — run 'screen enrich' first`))
          continue
        }

        const enrichmentId = `${ticker}:${enrichment.fetch_date}`
        const headlines = await fetchHeadlines(ticker)

        for (const hl of headlines) {
          const score = scoreSentiment(hl.text)
          insertSentiment({
            ticker,
            published_date: hl.date,
            headline_text: hl.text,
            summary: hl.summary,
            sentiment_score: score,
            source: hl.source,
            enrichment_id: enrichmentId,
          })
        }

        const count = headlines.length
        console.log(green(`  ${ticker}: ${count} headline(s) scored`))
      } catch (err) {
        console.error(red(`  ${ticker}: ${err}`))
      }
    }

    console.log(green("Sentiment complete."))
  },
})

// ── History ───────────────────────────────────────────────────────────────────

const historyCommand = defineCommand({
  meta: { name: "history", description: "Show recent screening runs" },
  args: {
    "--limit": { type: "string", description: "Number of runs to show (default: 10)" },
  },
  run: (ctx) => {
    DatabaseFactory.connect(cfg.portfolio.db)

    const limit = parseInt((ctx.args.limit as string) ?? "10", 10)
    const screenings = getRecentScreenings(limit)

    if (screenings.length === 0) {
      console.log("No screening runs recorded yet.")
      return
    }

    console.log("")
    console.log("SCREENING HISTORY")
    console.log("─".repeat(70))
    console.log(`${"Date".padEnd(12)} ${"# Rules".padEnd(8)} ${"Matched Tickers".padEnd(50)}`)
    console.log("─".repeat(70))

    for (const s of screenings) {
      const tickers = s.tickers_matched.slice(0, 5).join(", ")
      const extra = s.tickers_matched.length > 5 ? ` (+${s.tickers_matched.length - 5})` : ""
      console.log(`${s.run_date.padEnd(12)} ${String(s.rule_count).padEnd(8)} ${tickers}${extra}`)
    }
  },
})

// ── Init ────────────────────────────────────────────────────────────────────

const initCommand = defineCommand({
  meta: { name: "init", description: "Apply screening schema to the database" },
  args: {},
  run: () => {
    const { readFileSync, existsSync } = require("node:fs")
    const { join } = require("node:path")

    const schemaPath = join(process.cwd(), "src", "server", "lib", "schema.sql")

    if (!existsSync(schemaPath)) {
      console.error(red(`Schema not found at ${schemaPath}`))
      process.exit(1)
    }

    const schema = readFileSync(schemaPath, "utf-8")

    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const newTables = [
      "screening_rules",
      "watchlist_enrichment",
      "watchlist_news_sentiment",
      "watchlist_screenings",
    ]

    // Parse schema: statements end with ');' (handle ')' and ';' on different lines)
    const statements: string[] = []
    let buffer = ""
    for (const line of schema.split("\n")) {
      buffer += `${line}\n`
      if (line.trim() === ");") {
        statements.push(buffer.trim())
        buffer = ""
      }
    }

    for (const stmt of statements) {
      if (!stmt) continue
      const lines = stmt.split("\n")
      const hasContent = lines.some((l) => {
        const t = l.trim()
        return t.length > 0 && !t.startsWith("--")
      })
      if (!hasContent) continue

      // Determine if this statement should be skipped
      const tableMatch = stmt.match(/CREATE TABLE IF NOT EXISTS\s+(\w+)/i)
      const indexMatch = stmt.match(
        /^CREATE INDEX\s+(\S+)(?:\s+IF\s+NOT\s+EXISTS)?\s+ON\s+(\w+)\(/i,
      )
      if (tableMatch && !newTables.includes(tableMatch[1])) continue // skip existing tables
      if (indexMatch && !newTables.includes(indexMatch[2])) continue // skip indexes for existing tables

      try {
        db.query(stmt).run()
      } catch (e) {
        console.log(yellow(`Schema warning: ${String(e).slice(0, 80)}`))
      }
    }

    const created = db
      .query(
        "SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'watchlist_%' OR name LIKE 'screening_%')",
      )
      .all() as Array<{ name: string }>

    console.log(
      green(`Screening tables: ${created.map((r) => r.name).join(", ") || "(none created)"}`),
    )
    db.close()
  },
})

// ── Main ─────────────────────────────────────────────────────────────────────

export const screenCommand = defineCommand({
  meta: {
    name: "screen",
    description: "Watchlist screening: rules, enrichment, evaluation, and sentiment",
  },
  subCommands: {
    create: () => Promise.resolve(createCommand),
    delete: () => Promise.resolve(deleteCommand),
    enrich: () => Promise.resolve(enrichCommand),
    history: () => Promise.resolve(historyCommand),
    init: () => Promise.resolve(initCommand),
    list: () => Promise.resolve(listCommand),
    run: () => Promise.resolve(runCommand),
    sentiment: () => Promise.resolve(sentimentCommand),
  },
})

// ── Yahoo Finance Enrichment ─────────────────────────────────────────────────

interface YahooEnrichment {
  pe_forward: number | null
  eps_growth_1y: number | null
  operating_margin: number | null
  beta_1y: number | null
  price_to_sales: number | null
  sector: string | null
  region: string | null
}

async function enrichFromYahoo(ticker: string): Promise<YahooEnrichment | null> {
  try {
    const { spawn } = require("node:child_process")
    const result = await new Promise<string>((resolve, reject) => {
      const child = spawn(
        "python3",
        [
          "-c",
          `
import yfinance as yf
t = yf.Ticker('${ticker}')
info = t.info
print({
    'pe_forward': info.get('forwardPE'),
    'eps_growth_1y': info.get('earningsGrowth'),
    'operating_margin': info.get('operatingMargin'),
    'beta_1y': info.get('beta'),
    'price_to_sales': info.get('priceToSalesTrailing12Months'),
    'sector': info.get('sector'),
    'region': info.get('region'),
})
`,
        ],
        { timeout: 15000 },
      )
      let out = ""
      child.stdout?.on("data", (d: Buffer) => {
        out += d.toString()
      })
      child.stderr?.on("data", (_d: Buffer) => {
        /* ignore */
      })
      child.on("close", (code) => {
        code === 0 ? resolve(out) : reject(new Error(`exit ${code}`))
      })
    })
    return JSON.parse(result.trim()) as YahooEnrichment
  } catch {
    return null
  }
}

// ── Headline Fetching ────────────────────────────────────────────────────────

interface Headline {
  date: string
  text: string
  summary: string
  source: string
}

async function fetchHeadlines(_ticker: string): Promise<Headline[]> {
  // Fetch from Yahoo Finance news page via defuddle-style approach
  // For now, return empty array — defuddle integration is R07.1
  // TODO: integrate defuddle/web_fetch
  return []
}

// ── Sentiment Scoring ─────────────────────────────────────────────────────────

function scoreSentiment(text: string): number {
  const bullish = [
    "beat",
    "surge",
    "growth",
    "upgrade",
    "strong",
    "profit",
    "gain",
    "record",
    "bullish",
    "buy",
  ]
  const bearish = [
    "miss",
    "drop",
    "loss",
    "downgrade",
    "weak",
    "decline",
    "cut",
    "bearish",
    "sell",
    "risk",
  ]

  const lower = text.toLowerCase()
  let score = 0

  for (const word of bullish) {
    if (lower.includes(word)) score += 0.2
  }
  for (const word of bearish) {
    if (lower.includes(word)) score -= 0.2
  }

  return Math.max(-1, Math.min(1, score))
}
