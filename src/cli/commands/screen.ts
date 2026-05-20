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
  getSentimentSummary,
  insertSentiment,
  listScreeningRules,
  pruneOldSentiment,
  type ScreenCondition,
  saveScreeningHistory,
  upsertEnrichment,
  upsertPatternFeatures,
} from "@server/lib/screening-data"
import {
  type CandidateData,
  detectShockStocks,
  screenCandidates,
} from "@server/lib/screening-engine"
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
    conditions: { type: "string", required: true, description: "JSON array of conditions" },
    description: { type: "string", description: "Rule description" },
    priority: { type: "string", description: "Priority (default: 0)" },
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
    ticker: { type: "string", description: "Specific ticker" },
    all: { type: "boolean", description: "Enrich all watchlist candidates" },
    pattern: {
      type: "boolean",
      description: "Also compute STL pattern features (requires 252 bars of price history)",
    },
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

          // Pattern features (R08 — STL decomposition)
          if (ctx.args.pattern) {
            await computeAndStorePatternFeatures(ticker, today)
          }

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
    json: { type: "boolean", description: "Output as JSON" },
    stage: { type: "string", description: "Filter by stage (comma-separated)" },
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

    const candidates: CandidateData[] = candidateRows.map((r) => {
      const sent = getSentimentSummary(r.ticker)
      return {
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
        sentiment_avg: sent.avg_score,
      }
    })

    const result = screenCandidates({ candidates, rules, stageFilter })

    // Save history whenever there are matches (before JSON early-return)
    if (result.matches.length > 0) {
      const matchedTickers = result.matches.map((m) => m.ticker)
      saveScreeningHistory(matchedTickers, result.rules_evaluated)
    }

    if (ctx.args.json) {
      console.log(JSON.stringify(result, null, 2))
      return
    }

    if (result.matches.length === 0) {
      console.log("No candidates match current screening rules.")
      return
    }

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
    ticker: { type: "string", description: "Specific ticker" },
    all: { type: "boolean", description: "Process all watchlist candidates" },
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

    for (let i = 0; i < tickers.length; i++) {
      const ticker = tickers[i]!

      // Rate limit: 1s delay between tickers (respect Google News RSS)
      if (i > 0) await new Promise((r) => setTimeout(r, 1000))
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
    limit: { type: "string", description: "Number of runs to show (default: 10)" },
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

// ── Shock ────────────────────────────────────────────────────────────────────

const shockCommand = defineCommand({
  meta: {
    name: "shock",
    description: "Detect shock stocks — strong fundamentals despite price drop",
  },
  args: {
    "--drop": { type: "string", description: "Minimum price drop % (default: 10)" },
    "--margin": { type: "string", description: "Min operating margin % (default: 20)" },
    "--ps": { type: "string", description: "Max price-to-sales ratio (default: 5)" },
    "--json": { type: "boolean", description: "Output as JSON" },
  },
  run: async (ctx) => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const priceDropPct = parseFloat((ctx.args.drop as string) ?? "10")
    const minMarginPct = parseFloat((ctx.args.margin as string) ?? "20")
    const maxPSRatio = parseFloat((ctx.args.ps as string) ?? "5")

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

    const candidates: CandidateData[] = candidateRows.map((r) => {
      const sent = getSentimentSummary(r.ticker)
      return {
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
        sentiment_avg: sent.avg_score,
      }
    })

    const shockStocks = detectShockStocks({ candidates, priceDropPct, minMarginPct, maxPSRatio })

    if (ctx.args.json) {
      console.log(
        JSON.stringify(
          { shockStocks, params: { priceDropPct, minMarginPct, maxPSRatio } },
          null,
          2,
        ),
      )
      return
    }

    if (shockStocks.length === 0) {
      console.log("No shock stocks detected with current criteria.")
      console.log(`  Drop: >${priceDropPct}% | Margin: >${minMarginPct}% | P/S: <${maxPSRatio}`)
      return
    }

    console.log("")
    console.log(`⚡ SHOCK STOCKS (${shockStocks.length} found)`)
    console.log(`  Criteria: drop >${priceDropPct}%, margin >${minMarginPct}%, P/S <${maxPSRatio}`)
    console.log("─".repeat(80))
    console.log(
      `${`Ticker`.padEnd(10)} ${`Stage`.padEnd(14)} ${`Op. Margin`.padEnd(12)} ${`P/S`.padEnd(8)} Reason`,
    )
    console.log("─".repeat(80))

    for (const s of shockStocks) {
      const marginStr =
        s.enrichment?.operating_margin != null
          ? `${s.enrichment.operating_margin.toFixed(1)}%`
          : "—"
      const psStr =
        s.enrichment?.price_to_sales != null ? s.enrichment.price_to_sales.toFixed(2) : "—"
      console.log(
        `${s.ticker.padEnd(10)} ${s.stage.padEnd(14)} ${marginStr.padEnd(12)} ${psStr.padEnd(8)} ${s.match_reasons[0] ?? "—"}`,
      )
    }

    console.log("─".repeat(80))
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

    // Parse schema: split on semicolons (handles single-line CREATE INDEX; statements)
    const rawStatements = schema.split(/;\s*(?:\r?\n|$)/)
    const statements = rawStatements
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
      .filter((s) => {
        const content = s.replace(/--.*$/gm, "").trim()
        return content.length > 0
      })
      .map((s) => `${s};`)

    for (const stmt of statements) {
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
    shock: () => Promise.resolve(shockCommand),
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
  const { spawn } = require("node:child_process")
  const result = await new Promise<string>((resolve, reject) => {
    const child = spawn("python3", [
      "-c",
      `import sys, json, yfinance
t = yf.Ticker(sys.argv[1]).info
print(json.dumps({
    'pe_forward': t.get('forwardPE'),
    'eps_growth_1y': t.get('earningsGrowth'),
    'operating_margin': t.get('operatingMargin'),
    'beta_1y': t.get('beta'),
    'price_to_sales': t.get('priceToSalesTrailing12Months'),
    'sector': t.get('sector'),
    'region': t.get('region'),
}))
`,
      ticker,
    ])
    let out = ""
    let errOut = ""
    child.stdout?.on("data", (d: Buffer) => {
      out += d.toString()
    })
    child.stderr?.on("data", (d: Buffer) => {
      errOut += d.toString()
    })
    child.on("close", (code) => {
      if (code === 0) resolve(out)
      else reject(new Error(`python3 exit ${code}: ${errOut || "(no stderr)"}`))
    })
  }).catch((err) => {
    throw new Error(`enrichFromYahoo(${ticker}): ${err}`)
  })
  return JSON.parse(result.trim()) as YahooEnrichment
}

// ── Pattern Feature Computation ──────────────────────────────────────────────

/**
 * Compute STL pattern features for a ticker via the Python script,
 * then upsert them into the enrichment row for today's date.
 */
async function computeAndStorePatternFeatures(ticker: string, fetchDate: string): Promise<void> {
  const { spawn } = require("node:child_process")
  const dbPath = cfg.portfolio.db

  const result = await new Promise<string>((resolve, reject) => {
    const child = spawn("python3", [
      "scripts/py/compute_pattern_features.py",
      ticker,
      "--db",
      dbPath,
    ])
    let out = ""
    let errOut = ""
    child.stdout?.on("data", (d: Buffer) => {
      out += d.toString()
    })
    child.stderr?.on("data", (d: Buffer) => {
      errOut += d.toString()
    })
    child.on("close", (code) => {
      if (code === 0) resolve(out)
      else reject(new Error(`python3 exit ${code}: ${errOut || "(no stderr)"}`))
    })
  })

  const features = JSON.parse(result.trim()) as {
    error?: string
    trend_strength: number
    trend_linearity: number
    seasonality_strength: number
    seasonality_stability: number
    residual_acf1: number
    spectral_entropy: number
    is_stationary: number
  }

  if (features.error) {
    console.log(yellow(`  ${ticker}: pattern skipped (${features.error})`))
    return
  }

  upsertPatternFeatures(ticker, fetchDate, {
    trend_strength: features.trend_strength,
    trend_linearity: features.trend_linearity,
    seasonality_strength: features.seasonality_strength,
    seasonality_stability: features.seasonality_stability,
    residual_acf1: features.residual_acf1,
    spectral_entropy: features.spectral_entropy,
    is_stationary: features.is_stationary,
  })

  console.log(green(`  ${ticker}: pattern features computed`))
}

// ── Headline Fetching ────────────────────────────────────────────────────────

interface Headline {
  date: string
  text: string
  summary: string
  source: string
}

/**
 * Fetch recent headlines for a ticker via Google News RSS.
 * Returns up to 20 headlines, sorted newest-first.
 *
 * Implementation note: Uses regex-based RSS parsing to avoid adding an XML
 * dependency. Google News RSS is a well-structured, predictable format.
 * Rate limit: caller should enforce 1s delay between tickers.
 */
async function fetchHeadlines(ticker: string): Promise<Headline[]> {
  const url = `https://news.google.com/rss/search?q=${encodeURIComponent(ticker)}+stock&hl=en-US&gl=US&ceid=US:en`

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10_000)

  let response: Response
  try {
    response = await fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0 (compatible; TradingAgents/1.0)" },
      signal: controller.signal,
    })
  } catch (err) {
    clearTimeout(timeout)
    throw new Error(`fetchHeadlines(${ticker}): fetch failed: ${err}`)
  }
  clearTimeout(timeout)

  if (!response.ok) {
    throw new Error(`fetchHeadlines(${ticker}): Google News RSS returned ${response.status}`)
  }

  const xml = await response.text()

  // Parse <item> elements with regex — RSS XML is predictable enough for this
  const itemRegex = /<item>([\s\S]*?)<\/item>/g
  const headlines: Headline[] = []

  let match = itemRegex.exec(xml)
  while (match !== null) {
    const item = match[1]!

    const titleMatch = /<title>(.*?)<\/title>/s.exec(item)
    const pubDateMatch = /<pubDate>(.*?)<\/pubDate>/s.exec(item)
    const descMatch = /<description>(.*?)<\/description>/s.exec(item)
    const sourceMatch = /<source[^>]*>(.*?)<\/source>/s.exec(item)

    const rawTitle = titleMatch?.[1] ?? ""
    const pubDate = pubDateMatch?.[1] ?? ""
    const rawDesc = descMatch?.[1] ?? ""
    const sourceName = sourceMatch?.[1] ?? ""

    // Decode HTML entities
    const decode = (s: string) =>
      s
        .replace(/&amp;/g, "&")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/&apos;/g, "'")

    // Strip " - Source Name" suffix from title
    const title = decode(rawTitle)
      .replace(/\s*-\s*[^-]+$/, "")
      .trim()

    // Extract plain text from description (strip HTML tags + CDATA)
    const desc = decode(rawDesc.replace(/<[^>]*>/g, "").replace(/<!\[CDATA\[|\]\]>/g, "")).trim()
    const summary = desc.slice(0, 200)
    const source = sourceName || "news"

    // Parse date, fall back to today
    let date: string
    try {
      date = new Date(pubDate).toISOString().split("T")[0]!
    } catch {
      date = new Date().toISOString().split("T")[0]!
    }

    headlines.push({ date, text: title, summary, source })

    if (headlines.length >= 20) break
    match = itemRegex.exec(xml)
  }

  return headlines
}

// ── Sentiment Scoring ─────────────────────────────────────────────────────────

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

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
    if (new RegExp(`\\b${escapeRegex(word)}\\b`, "i").test(lower)) score += 0.2
  }
  for (const word of bearish) {
    if (new RegExp(`\\b${escapeRegex(word)}\\b`, "i").test(lower)) score -= 0.2
  }

  return Math.max(-1, Math.min(1, score))
}
