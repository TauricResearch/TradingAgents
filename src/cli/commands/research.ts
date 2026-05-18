#!/usr/bin/env bun

/**
 * Research — TradingAgents analysis and research coverage.
 *
 * Subcommands:
 *   trading research coverage   — show watchlist coverage by research doc
 *   trading research analyze    — run analysis on a ticker (default)
 *
 * Usage:
 *   trading research coverage
 *   trading research analyze AAPL --write --fetch
 */

import { existsSync } from "node:fs"
import { join } from "node:path"
import { DatabaseFactory } from "@lib/db"
import { cfg } from "@lib/settings"
import { defineCommand } from "citty"
import { gum } from "../../../scripts/lib/gum.ts"

// ── Types ─────────────────────────────────────────────────────────────────────

interface ParsedState {
  entryPrice: number | null
  stopLoss: number | null
  positionSizing: string | null
  priceTarget: number | null
  rating: string | null
  action: string | null
}

interface CoverageGroup {
  research_doc: string
  ticker_count: number
  high_count: number
  medium_count: number
  low_count: number
  stale_count: number
  last_update: string | null
  tickers: string[]
}

// ── Coverage subcommand ───────────────────────────────────────────────────────

const coverageCommand = defineCommand({
  meta: { name: "coverage", description: "Show watchlist coverage by research document" },
  args: {},
  run: () => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    // Group watchlist by research_doc
    const groups = db
      .query<{
        research_doc: string | null
        ticker: string
        priority: string
        last_research_update: string | null
      }>(
        `SELECT research_doc, ticker, priority, last_research_update
         FROM watchlist
         ORDER BY research_doc NULLS LAST, priority DESC, ticker`,
      )
      .all()

    const STALE_DAYS = 90
    const now = new Date()

    // Group by research_doc
    const byDoc: Map<string, CoverageGroup> = new Map()
    let staleUnlinked = 0

    for (const row of groups) {
      const doc = row.research_doc ?? "__unlinked__"
      if (!byDoc.has(doc)) {
        byDoc.set(doc, {
          research_doc: doc,
          ticker_count: 0,
          high_count: 0,
          medium_count: 0,
          low_count: 0,
          stale_count: 0,
          last_update: null,
          tickers: [],
        })
      }
      const g = byDoc.get(doc)
      if (!g) continue

      g.ticker_count++
      g.tickers.push(row.ticker)

      if (row.priority === "high") g.high_count++
      else if (row.priority === "medium") g.medium_count++
      else g.low_count++

      if (row.last_research_update) {
        if (!g.last_update || row.last_research_update > g.last_update) {
          g.last_update = row.last_research_update
        }
        const updated = new Date(row.last_research_update)
        const threshold = new Date(now)
        threshold.setDate(threshold.getDate() - STALE_DAYS)
        if (updated < threshold) g.stale_count++
      } else if (!row.research_doc) {
        // unlinked = stale by definition
        g.stale_count++
        staleUnlinked++
      }
    }

    const totalWatchlist = groups.length
    const docsWithResearch = [...byDoc.keys()].filter((k) => k !== "__unlinked__").length

    // ── Output ─────────────────────────────────────────────────────────────

    const line = "─".repeat(80)
    console.log("")
    console.log("RESEARCH COVERAGE")
    console.log(line)
    console.log(
      `  ${String(totalWatchlist).padStart(3)} prospects on watchlist  ·  ${docsWithResearch} research doc(s)  ·  ${staleUnlinked} unlinked (stale)`,
    )
    console.log(line)

    // Research-linked entries first
    for (const [doc, g] of byDoc) {
      if (doc === "__unlinked__") continue
      const isStale = g.stale_count > 0
      const staleFlag = isStale ? " \x1b[33m⚠ STALE\x1b[0m" : ""
      const updateStr = g.last_update ?? "—"

      console.log("")
      console.log(
        `  ${g.research_doc}${staleFlag}  ·  ${g.ticker_count} ticker(s)  ·  updated: ${updateStr}`,
      )

      // Priority breakdown
      if (g.high_count > 0)
        console.log(
          `    \x1b[31mhigh:\x1b[0m   ${g.tickers
            .filter((t) => {
              const r = groups.find((x) => x.research_doc === doc && x.ticker === t)
              return r?.priority === "high"
            })
            .join(", ")}`,
        )
      if (g.medium_count > 0)
        console.log(
          `    \x1b[33mmedium:\x1b[0m ${g.tickers
            .filter((t) => {
              const r = groups.find((x) => x.research_doc === doc && x.ticker === t)
              return r?.priority === "medium"
            })
            .join(", ")}`,
        )
      if (g.low_count > 0)
        console.log(
          `    low:    ${g.tickers
            .filter((t) => {
              const r = groups.find((x) => x.research_doc === doc && x.ticker === t)
              return r?.priority === "low"
            })
            .join(", ")}`,
        )

      console.log("")
    }

    // Stale unlinked entries
    const unlinked = byDoc.get("__unlinked__")
    if (unlinked && unlinked.ticker_count > 0) {
      console.log(
        `  \x1b[33mUnlinked (no research doc)\x1b[0m  ·  ${unlinked.ticker_count} ticker(s)  ·  ⚠ stale`,
      )
      const unlinkedByPriority = {
        high: unlinked.tickers.filter(
          (t) => groups.find((x) => x.research_doc === null && x.ticker === t)?.priority === "high",
        ),
        medium: unlinked.tickers.filter(
          (t) =>
            groups.find((x) => x.research_doc === null && x.ticker === t)?.priority === "medium",
        ),
        low: unlinked.tickers.filter(
          (t) => groups.find((x) => x.research_doc === null && x.ticker === t)?.priority === "low",
        ),
      }
      if (unlinkedByPriority.high.length)
        console.log(`    \x1b[31mhigh:\x1b[0m   ${unlinkedByPriority.high.join(", ")}`)
      if (unlinkedByPriority.medium.length)
        console.log(`    \x1b[33mmedium:\x1b[0m ${unlinkedByPriority.medium.join(", ")}`)
      if (unlinkedByPriority.low.length)
        console.log(`    low:    ${unlinkedByPriority.low.join(", ")}`)

      console.log("")
      console.log(
        "  Run `trading watchlist` to see all. Link a research doc to activate screening.",
      )
    }

    console.log(line)
    console.log("")
  },
})

// ── Analyze subcommand (existing logic) ──────────────────────────────────────

async function findLatestStateFile(ticker: string): Promise<string | null> {
  const home = process.env.HOME ?? "~"
  const dir = join(home, ".tradingagents", "logs", ticker, "TradingAgentsStrategy_logs")
  if (!existsSync(dir)) return null

  const proc = Bun.spawn({
    cmd: ["bash", "-c", `ls -t "${dir}"/full_states_log_*.json | head -1`],
    stdout: "pipe",
    stderr: "pipe",
  })
  const path = (await new Response(proc.stdout).text()).trim()
  return path && existsSync(path) ? path : null
}

function parseState(path: string): ParsedState {
  try {
    const content = require("node:fs").readFileSync(path, "utf-8")
    const state = JSON.parse(content)
    const traderPlan: string = state.trader_investment_decision ?? ""
    const finalDecision: string = state.final_trade_decision ?? ""
    const entryMatch = traderPlan.match(/\*\*Entry Price\*\*:\s*([\d.]+)/)
    const stopMatch = traderPlan.match(/\*\*Stop Loss\*\*:\s*([\d.]+)/)
    const sizingMatch = traderPlan.match(/\*\*Position Sizing\*\*:\s*(.+?)(?:\n\n|\nFINAL)/s)
    const targetMatch = finalDecision.match(/\*\*Price Target\*\*:\s*([\d.]+)/)
    const ratingMatch = finalDecision.match(/\*\*Rating\*\*:\s*(\w+)/)
    const actionMatch = traderPlan.match(/\*\*Action\*\*:\s*(\w+)/)
    return {
      entryPrice: entryMatch ? parseFloat(entryMatch[1]) : null,
      stopLoss: stopMatch ? parseFloat(stopMatch[1]) : null,
      positionSizing: sizingMatch ? sizingMatch[1].trim() : null,
      priceTarget: targetMatch ? parseFloat(targetMatch[1]) : null,
      rating: ratingMatch ? ratingMatch[1] : null,
      action: actionMatch ? actionMatch[1] : null,
    }
  } catch {
    return {
      entryPrice: null,
      stopLoss: null,
      positionSizing: null,
      priceTarget: null,
      rating: null,
      action: null,
    }
  }
}

function latestPrice(db: ReturnType<typeof DatabaseFactory.get>, ticker: string): number | null {
  const row = db
    .query<{ close: number }, [string]>(
      "SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
    )
    .get(ticker)
  return row ? parseFloat(row.close) : null
}

async function fetchPrice(ticker: string): Promise<number | null> {
  try {
    const proc = Bun.spawn({
      cmd: ["bun", "run", "scripts/get_price.ts", ticker],
      stdout: "pipe",
      stderr: "pipe",
    })
    const text = await new Response(proc.stdout).text()
    const data = JSON.parse(text)
    return data.price ?? null
  } catch {
    return null
  }
}

async function displayResult(ticker: string, parsed: ParsedState, currentPrice: number | null) {
  const title = await gum(`${ticker} — Research Bridge`, ["--bold", "--foreground", "212"])
  console.log(`  ${title}`)
  const lines = [`${"Field".padEnd(18)} ${"Value"}`, "─".repeat(50)]
  const addLine = (label: string, value: string | null) => {
    lines.push(`${label.padEnd(18)} ${value ?? "\x1b[90m(not generated by pipeline)\x1b[0m"}`)
  }
  addLine("Action", parsed.action)
  addLine("Rating", parsed.rating)
  addLine("Entry Price", parsed.entryPrice != null ? `£${parsed.entryPrice.toFixed(2)}` : null)
  addLine("Stop Loss", parsed.stopLoss != null ? `£${parsed.stopLoss.toFixed(2)}` : null)
  addLine("Price Target", parsed.priceTarget != null ? `£${parsed.priceTarget.toFixed(2)}` : null)
  addLine("Position Sizing", parsed.positionSizing)
  addLine("Current Price", currentPrice != null ? `£${currentPrice.toFixed(2)}` : null)
  const box = await gum(lines.join("\n"), ["--border", "rounded", "--padding", "1 2"])
  console.log(box)
  if (parsed.entryPrice != null && currentPrice != null) {
    const gap = ((currentPrice - parsed.entryPrice) / parsed.entryPrice) * 100
    const colour = currentPrice <= parsed.entryPrice ? "\x1b[32m" : "\x1b[0m"
    console.log(`  ${colour}Gap to entry: ${gap >= 0 ? "+" : ""}${gap.toFixed(1)}%${"\x1b[0m"}`)
  }
  console.log("")
}

const analyzeCommand = defineCommand({
  meta: { name: "analyze", description: "Run TradingAgents analysis on a ticker" },
  args: {
    ticker: {
      type: "positional",
      description: "Stock ticker to research (e.g. AAPL, TKA.DE)",
      required: true,
    },
    write: {
      type: "boolean",
      description: "Write entry_price to watchlist.fair_value",
      default: false,
    },
    fetch: { type: "boolean", description: "Fetch current price after analysis", default: false },
    debates: { type: "string", description: "Number of debate rounds", default: "1" },
  },
  run: async ({ args }) => {
    const ticker = args.ticker
    const script = join(process.cwd(), "scripts", "py", "analyze_stream.py")
    if (!existsSync(script)) {
      console.error(`Error: analyze_stream.py not found at ${script}`)
      process.exit(1)
    }

    console.log(`Running TradingAgents analysis for ${ticker}...`)
    console.log("(This may take 2-5 minutes depending on LLM provider)\n")

    const env = { ...process.env, PYTHONUNBUFFERED: "1" }
    const abortController = new AbortController()
    const timeoutMs = 300_000
    const timeoutId = setTimeout(() => {
      abortController.abort()
    }, timeoutMs)

    const proc = Bun.spawn(
      [
        "python3",
        script,
        ticker,
        "--debates",
        args.debates,
        "--timeout",
        "300",
        "--heartbeat-interval",
        "15",
      ],
      { stdout: "inherit", stderr: "inherit", env, signal: abortController.signal },
    )
    const exitCode = await proc.exited
    clearTimeout(timeoutId)
    if (exitCode !== 0) {
      console.error(`\nAnalysis failed with exit code ${exitCode}`)
      process.exit(exitCode)
    }

    console.log("\nAnalysis complete. Parsing state...\n")
    const statePath = await findLatestStateFile(ticker)
    if (!statePath) {
      console.error(`No state file found for ${ticker}`)
      process.exit(1)
    }

    const parsed = parseState(statePath)
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()
    let currentPrice = latestPrice(db, ticker)
    if (currentPrice == null && args.fetch) currentPrice = await fetchPrice(ticker)
    await displayResult(ticker, parsed, currentPrice)

    if (args.write) {
      if (parsed.entryPrice == null) {
        console.log("  ⚠ No entry_price found in analysis.")
        return
      }
      const existing = db
        .query<{ id: number }, [string]>("SELECT id FROM watchlist WHERE ticker = ?")
        .get(ticker)
      if (existing) {
        db.run("UPDATE watchlist SET fair_value = ?, max_position_gbp = ? WHERE ticker = ?", [
          parsed.entryPrice,
          null,
          ticker,
        ])
        console.log(
          `  ✓ Updated watchlist: ${ticker} fair_value = £${parsed.entryPrice.toFixed(2)}`,
        )
      } else {
        db.run(
          "INSERT INTO watchlist (ticker, exchange, platform, priority, stage, added_date, thesis, fair_value) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
          [
            ticker,
            "US",
            "unknown",
            "medium",
            "analyzed",
            new Date().toISOString().slice(0, 10),
            "From pipeline research",
            parsed.entryPrice,
          ],
        )
        console.log(
          `  ✓ Added to watchlist: ${ticker} fair_value = £${parsed.entryPrice.toFixed(2)}`,
        )
      }
      if (parsed.positionSizing)
        console.log(`  ℹ Position sizing suggestion: ${parsed.positionSizing}`)
      console.log("\n  Run `trading buylist` to see all contingency items.")
    }
  },
})

// ── Main research command with subcommands ────────────────────────────────────

export const researchCommand = defineCommand({
  meta: {
    name: "research",
    description: "Research — coverage overview and TradingAgents analysis",
  },
  subCommands: {
    coverage: () => coverageCommand,
    analyze: () => analyzeCommand,
  },
  run: () => {
    // Default: show coverage if no subcommand given
    console.log("Usage: trading research <coverage|analyze>")
    console.log("  trading research coverage      — watchlist coverage by research doc")
    console.log("  trading research analyze TICKER — run TradingAgents analysis")
    process.exit(1)
  },
})
