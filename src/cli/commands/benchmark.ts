#!/usr/bin/env bun

/**
 * Compare portfolio returns vs. a passive benchmark index.
 *
 * Usage: trading benchmark [--benchmark TICKER] [--since YYYY-MM-DD]
 */

import { DatabaseFactory } from "@lib/db"
import { cfg } from "@lib/settings"
import { defineCommand } from "citty"

interface PositionRow {
  ticker: string
  quantity: number
  avg_cost: number
  entry_date: string
}

interface PriceRow {
  date: string
  close: number
  gbp_rate: number | null
}

function fmtPct(n: number | null): string {
  if (n == null) return "—"
  const sign = n >= 0 ? "+" : ""
  return `${sign}${(n * 100).toFixed(1)}%`
}

function annualize(totalReturn: number, days: number): number | null {
  if (days <= 0 || totalReturn <= -1) return null
  return (1 + totalReturn) ** (365 / days) - 1
}

export const benchmarkCommand = defineCommand({
  meta: {
    name: "benchmark",
    description: "Compare portfolio returns vs. a passive benchmark index",
  },
  args: {
    benchmark: {
      type: "string",
      description: "Benchmark ticker (default: VWCE.DE)",
      alias: "b",
      default: cfg.app.benchmarkTicker || "VWCE.DE",
    },
    since: {
      type: "string",
      description: "Custom start date (YYYY-MM-DD)",
      alias: "s",
    },
  },
  run: ({ args }) => {
    DatabaseFactory.connect(cfg.portfolio.db)
    const db = DatabaseFactory.get()

    const benchmarkTicker = args.benchmark

    // ── Load positions ──────────────────────────────────────────────────────

    const positions = db
      .query(
        `SELECT ticker, quantity, avg_cost, entry_date
         FROM positions
         WHERE status = 'open'
         ORDER BY entry_date`,
      )
      .all() as PositionRow[]

    if (positions.length === 0) {
      console.log("No open positions to benchmark.")
      return
    }

    // ── Helper: get price on or after date ─────────────────────────────────

    function getPriceOnOrAfter(ticker: string, targetDate: string): PriceRow | null {
      return db
        .query(
          `SELECT date, close, gbp_rate
           FROM prices
           WHERE ticker = ? AND date >= ?
           ORDER BY date ASC
           LIMIT 1`,
        )
        .get(ticker, targetDate) as PriceRow | null
    }

    function getLatestPrice(ticker: string): PriceRow | null {
      return db
        .query(
          `SELECT date, close, gbp_rate
           FROM prices
           WHERE ticker = ?
           ORDER BY date DESC
           LIMIT 1`,
        )
        .get(ticker) as PriceRow | null
    }

    // ── Determine analysis period ───────────────────────────────────────────

    let startDate: string
    if (args.since) {
      startDate = args.since
    } else {
      // Earliest position entry date that has price data
      const tickers = [...new Set(positions.map((p) => p.ticker))]
      let earliest: string | null = null
      for (const t of tickers) {
        const price = getPriceOnOrAfter(t, "2020-01-01")
        if (price && (!earliest || price.date < earliest)) {
          earliest = price.date
        }
      }
      startDate = earliest || positions[0].entry_date
    }

    // ── Get benchmark prices ────────────────────────────────────────────────

    const benchmarkStart = getPriceOnOrAfter(benchmarkTicker, startDate)
    const benchmarkLatest = getLatestPrice(benchmarkTicker)

    if (!benchmarkStart || !benchmarkLatest) {
      console.log(`No price data for benchmark ${benchmarkTicker}.`)
      console.log(`Run: trading sync prices ${benchmarkTicker}`)
      return
    }

    // ── Calculate portfolio values ─────────────────────────────────────────

    let totalEntryGBP = 0
    let totalCurrentGBP = 0

    for (const pos of positions) {
      const entryPrice = getPriceOnOrAfter(pos.ticker, pos.entry_date)
      const latestPrice = getLatestPrice(pos.ticker)

      if (!entryPrice || !latestPrice) continue

      // Use avg_cost as cost basis (already in native currency)
      // Convert to GBP using gbp_rate at entry (or 1.0 if not available)
      const entryGbpRate = entryPrice.gbp_rate ?? (entryPrice.close === pos.avg_cost ? 1 : 0.7874)
      const currentGbpRate = latestPrice.gbp_rate ?? entryGbpRate

      const entryValue = pos.quantity * pos.avg_cost * entryGbpRate
      const currentValue = pos.quantity * latestPrice.close * currentGbpRate

      totalEntryGBP += entryValue
      totalCurrentGBP += currentValue
    }

    if (totalEntryGBP <= 0) {
      console.log("Could not compute portfolio values — no price data for positions.")
      return
    }

    // ── Calculate benchmark values ─────────────────────────────────────────

    // Simulate: same GBP invested in benchmark at start
    const benchmarkShares = totalEntryGBP / (benchmarkStart.close * (benchmarkStart.gbp_rate ?? 1))
    const benchmarkCurrentGBP =
      benchmarkShares * benchmarkLatest.close * (benchmarkLatest.gbp_rate ?? 1)

    // ── Calculate returns ──────────────────────────────────────────────────

    const portfolioReturn = (totalCurrentGBP - totalEntryGBP) / totalEntryGBP
    const benchmarkReturn = (benchmarkCurrentGBP - totalEntryGBP) / totalEntryGBP
    const alpha = portfolioReturn - benchmarkReturn

    const daysHeld = Math.max(
      1,
      Math.round(
        (new Date(benchmarkLatest.date).getTime() - new Date(benchmarkStart.date).getTime()) /
          (1000 * 60 * 60 * 24),
      ),
    )

    const portAnn = annualize(portfolioReturn, daysHeld)
    const benchAnn = annualize(benchmarkReturn, daysHeld)
    const alphaAnn = portAnn != null && benchAnn != null ? portAnn - benchAnn : null

    // ── Print results ────────────────────────────────────────────────────────

    const winner =
      portfolioReturn > benchmarkReturn
        ? "\x1b[32mPortfolio\x1b[0m"
        : portfolioReturn < benchmarkReturn
          ? "\x1b[31mBenchmark\x1b[0m"
          : "Tie"

    const wPeriod = 18
    const wPort = 14
    const wBench = 14
    const wAlpha = 14
    const wWinner = 12

    const header = `${"Period".padEnd(wPeriod)} ${"Portfolio".padStart(wPort)} ${"Benchmark".padStart(wBench)} ${"Alpha".padStart(wAlpha)} ${"Winner".padStart(wWinner)}`
    const line = "═".repeat(header.length)

    console.log("")
    console.log(`BENCHMARK COMPARISON`)
    console.log(`Benchmark: ${benchmarkTicker}`)
    console.log(`Period: ${benchmarkStart.date} → ${benchmarkLatest.date} (${daysHeld} days)`)
    console.log(line)
    console.log(header)
    console.log("─".repeat(header.length))

    const portColor = portfolioReturn >= 0 ? "\x1b[32m" : "\x1b[31m"
    const benchColor = benchmarkReturn >= 0 ? "\x1b[32m" : "\x1b[31m"
    const alphaColor = alpha >= 0 ? "\x1b[32m" : "\x1b[31m"
    const reset = "\x1b[0m"

    console.log(
      `${"Total Return".padEnd(wPeriod)} ${portColor}${fmtPct(portfolioReturn).padStart(wPort)}${reset} ${benchColor}${fmtPct(benchmarkReturn).padStart(wBench)}${reset} ${alphaColor}${fmtPct(alpha).padStart(wAlpha)}${reset} ${winner.padStart(wWinner)}`,
    )

    if (portAnn != null && benchAnn != null) {
      const aColor = (alphaAnn ?? 0) >= 0 ? "\x1b[32m" : "\x1b[31m"
      console.log(
        `${"Annualized".padEnd(wPeriod)} ${portColor}${fmtPct(portAnn).padStart(wPort)}${reset} ${benchColor}${fmtPct(benchAnn).padStart(wBench)}${reset} ${aColor}${fmtPct(alphaAnn).padStart(wAlpha)}${reset} ${"".padStart(wWinner)}`,
      )
    }

    console.log(line)

    // ── Value breakdown ──────────────────────────────────────────────────────

    console.log("")
    console.log("VALUE BREAKDOWN")
    console.log(
      `  Portfolio cost basis:  £${totalEntryGBP.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    )
    console.log(
      `  Portfolio current:     £${totalCurrentGBP.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    )
    console.log(
      `  Benchmark current:     £${benchmarkCurrentGBP.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    )
    console.log(
      `  P&L vs benchmark:      ${alpha >= 0 ? "\x1b[32m" : "\x1b[31m"}£${(totalCurrentGBP - benchmarkCurrentGBP).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}\x1b[0m`,
    )
    console.log("")

    // ── Position-level detail ────────────────────────────────────────────────

    console.log("POSITION DETAIL")
    console.log(
      `${"Ticker".padEnd(10)} ${"Qty".padStart(6)} ${"Entry".padStart(10)} ${"Current".padStart(10)} ${"Return".padStart(10)}`,
    )
    console.log("─".repeat(55))

    for (const pos of positions) {
      const latestPrice = getLatestPrice(pos.ticker)
      if (!latestPrice) continue

      const gbpRate = latestPrice.gbp_rate ?? 0.7874
      const entryGbp = pos.quantity * pos.avg_cost * gbpRate
      const currentGbp = pos.quantity * latestPrice.close * gbpRate
      const ret = entryGbp > 0 ? (currentGbp - entryGbp) / entryGbp : null

      const retColor = ret != null && ret >= 0 ? "\x1b[32m" : "\x1b[31m"
      console.log(
        `${pos.ticker.padEnd(10)} ${String(pos.quantity).padStart(6)} ${pos.avg_cost.toFixed(2).padStart(10)} ${latestPrice.close.toFixed(2).padStart(10)} ${retColor}${fmtPct(ret).padStart(10)}\x1b[0m`,
      )
    }

    console.log("")
  },
})
