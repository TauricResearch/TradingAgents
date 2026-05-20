#!/usr/bin/env bun

/**
 * Regime Check — compute Markov regime state, transition matrix, and trading signal.
 *
 * Usage:
 *   trading regime AAPL              # current state + signal
 *   trading regime AAPL --forecast 2 # 2-day forecast
 *   trading regime AAPL --store      # persist to DB
 */

import { DatabaseFactory } from "@lib/db"
import { cfg } from "@lib/settings"
import { defineCommand } from "citty"
import {
  buildTransitionMatrix,
  getPersistence,
  nDayProbabilities,
} from "../../server/lib/markov/matrix.ts"
import { insertRegimeMatrix, upsertRegimeState } from "../../server/lib/markov/regime-data.ts"
import { buildRegimeSignal, signalToPositionSize } from "../../server/lib/markov/signal.ts"
import { generateStateStream } from "../../server/lib/markov/state.ts"

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
function cyan(text: string) {
  return color(text, "\x1b[36m")
}

/**
 * Read close prices from the SQLite prices table for a ticker.
 */
function getPriceHistory(ticker: string): { prices: number[]; dates: string[] } {
  const db = DatabaseFactory.get()
  const rows = db
    .query("SELECT date, close FROM prices WHERE ticker = ? ORDER BY date ASC")
    .all(ticker) as Array<{ date: string; close: number }>

  if (rows.length < 2) {
    throw new Error(`Insufficient price history for ${ticker}: ${rows.length} bars (need ≥2)`)
  }

  return {
    prices: rows.map((r) => parseFloat(String(r.close))),
    dates: rows.map((r) => r.date),
  }
}

// ── Command ─────────────────────────────────────────────────────────────────

export const regimeCommand = defineCommand({
  meta: {
    name: "regime",
    description: "Compute Markov regime state, transition matrix, and trading signal",
  },
  args: {
    ticker: {
      type: "positional",
      description: "Ticker symbol",
      required: true,
    },
    "--forecast": {
      type: "string",
      description: "N-day forecast (e.g. 2 = next 2 days)",
    },
    "--store": {
      type: "boolean",
      description: "Persist state and matrix to database",
    },
  },
  run: async (ctx) => {
    const ticker = ctx.args.ticker as string
    const forecastDays = parseInt((ctx.args.forecast as string) ?? "0", 10) || 0

    DatabaseFactory.connect(cfg.portfolio.db)

    try {
      // Step 1: Read price history
      const { prices, dates } = getPriceHistory(ticker)

      // Step 2: Classify states from returns
      const dailyReturns: number[] = []
      for (let i = 1; i < prices.length; i++) {
        dailyReturns.push((prices[i]! - prices[i - 1]!) / prices[i - 1]!)
      }

      const stateStream = generateStateStream(ticker, prices, dates)
      const states = stateStream.map((s) => s.state)

      if (states.length < 20) {
        throw new Error(
          `Insufficient state history for ${ticker}: ${states.length} states (need ≥20 for reliable signal)`,
        )
      }

      // Step 3: Build transition matrix
      const matrix = buildTransitionMatrix(states)
      const currentState = states[states.length - 1]!
      const currentDate = dates[dates.length - 1]!
      const lookbackDays = dates.length

      // Step 4: Generate signal
      const signal = buildRegimeSignal(ticker, currentDate, currentState, matrix)

      // Step 5: Persist if requested
      if (ctx.args.store) {
        // Store the latest state
        upsertRegimeState({
          ticker,
          date: currentDate,
          state: currentState,
          cumulative_return: dailyReturns.slice(-20).reduce((a, b) => a + b, 0),
        })
        // Store the matrix
        insertRegimeMatrix(ticker, currentDate, matrix)
      }

      // ── Output ──────────────────────────────────────────────────────────────

      const ndays = forecastDays
      const fcast = ndays > 0 ? nDayProbabilities(matrix, currentState, ndays) : null

      console.log("")
      console.log(cyan(`=== Regime: ${ticker} ===`))
      console.log("")
      console.log(`${"State:".padEnd(20)} ${signal.currentState.toUpperCase()}`)
      console.log(`${"Date:".padEnd(20)} ${currentDate}`)
      console.log(`${"Lookback:".padEnd(20)} ${lookbackDays} bars`)
      console.log("")
      console.log(
        `${"Signal:".padEnd(20)} ${signal.signal >= 0 ? green("") : red("")}${signal.signal.toFixed(4)}\x1b[0m`,
      )
      console.log(`${"Direction:".padEnd(20)} ${signal.signalDirection}`)
      console.log(`${"Magnitude:".padEnd(20)} ${signal.signalMagnitude.toFixed(4)}`)
      console.log(
        `${"Position size:".padEnd(20)} ${(signalToPositionSize(signal.signalMagnitude) * 100).toFixed(1)}%`,
      )
      console.log("")

      // Probabilities
      console.log("Transition probabilities (from today → tomorrow):")
      console.log(`  P(bull):     ${signal.pBull.toFixed(4)}`)
      console.log(`  P(sideways): ${signal.pSideways.toFixed(4)}`)
      console.log(`  P(bear):     ${signal.pBear.toFixed(4)}`)
      console.log("")

      if (fcast) {
        console.log(`${ndays}-day forecast:`)
        console.log(`  P(bull):     ${fcast.bull.toFixed(4)}`)
        console.log(`  P(sideways): ${fcast.sideways.toFixed(4)}`)
        console.log(`  P(bear):     ${fcast.bear.toFixed(4)}`)
        console.log(`  Signal:      ${(fcast.bull - fcast.bear).toFixed(4)}`)
        console.log("")
      }

      // Persistence diagonal
      const pers = getPersistence(matrix)
      console.log("Persistence (stickiness):")
      console.log(`  Bull:     ${pers.bull.toFixed(4)}`)
      console.log(`  Sideways: ${pers.sideways.toFixed(4)}`)
      console.log(`  Bear:     ${pers.bear.toFixed(4)}`)
      console.log("")

      if (ctx.args.store) {
        console.log(green("✓ persisted to DB"))
      } else {
        console.log("Run with --store to persist.")
      }
      console.log("")
    } catch (err) {
      console.error(red(`Error: ${err}`))
      process.exit(1)
    }
  },
})
