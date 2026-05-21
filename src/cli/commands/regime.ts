#!/usr/bin/env bun

/**
 * Regime Check — compute Markov regime state, transition matrix, and trading signal.
 *
 * Usage:
 *   trading regime AAPL              # current state + signal
 *   trading regime AAPL --forecast 2 # 2-day forecast
 *   trading regime AAPL --store      # persist to DB
 *   trading regime AAPL --json       # machine-readable JSON output
 */

import { defineCommand } from "citty"
import { DatabaseFactory } from "../../server/lib/db.ts"
import {
  buildRegimeSignal,
  buildTransitionMatrix,
  generateStateStream,
  getPersistence,
  nDayProbabilities,
  signalToPositionSize,
  updateRegimeData,
} from "../../server/lib/markov/index.ts"
import { cfg } from "../../server/lib/settings.ts"

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
    const msg = JSON.stringify({
      error: `Insufficient price history for ${ticker}`,
      detail: `${rows.length} bars (need ≥2)`,
      hint: `Sync prices first: trading prices sync --ticker ${ticker}`,
    })
    console.error(msg)
    process.exit(1)
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
    "--json": {
      type: "boolean",
      description: "Output as JSON (for scripting)",
    },
  },
  run: async (ctx) => {
    const ticker = ctx.args.ticker as string
    const forecastDays = parseInt((ctx.args.forecast as string) ?? "0", 10) || 0
    const asJson = (ctx.args.json as boolean) ?? false

    DatabaseFactory.connect(cfg.portfolio.db)

    try {
      // Step 1: Read price history
      const { prices, dates } = getPriceHistory(ticker)

      // Step 2: Classify states from returns
      const stateStream = generateStateStream(ticker, prices, dates)
      const states = stateStream.map((s) => s.state)

      if (states.length < 20) {
        const err = {
          error: `Insufficient state history for ${ticker}`,
          detail: `${states.length} states (need ≥20 for reliable signal)`,
          hint: `Sync more price data: trading prices sync --ticker ${ticker}`,
        }
        if (asJson) {
          console.log(JSON.stringify(err))
          process.exit(1)
        }
        console.error(red(`Error: ${err.error}`))
        console.error(red(`  ${err.detail}`))
        process.exit(1)
      }

      // Step 3: Build transition matrix (for display + non-store signal)
      const matrix = buildTransitionMatrix(states)
      const currentState = states[states.length - 1]!
      const currentDate = dates[dates.length - 1]!
      const lookbackDays = dates.length

      // Step 4-5: Generate signal and persist if requested
      // When --store, use updateRegimeData (FR-6 full pipeline with persistence)
      const signal = ctx.args.store
        ? updateRegimeData(ticker)
        : buildRegimeSignal(ticker, currentDate, currentState, matrix)

      // ── Output ──────────────────────────────────────────────────────────────

      const ndays = forecastDays
      const fcast = ndays > 0 ? nDayProbabilities(matrix, currentState, ndays) : null
      const pers = getPersistence(matrix)

      if (asJson) {
        const output: Record<string, unknown> = {
          ticker,
          date: currentDate,
          state: signal.currentState,
          lookbackDays,
          signal: signal.signal,
          signalDirection: signal.signalDirection,
          signalMagnitude: signal.signalMagnitude,
          positionSizePct: signalToPositionSize(signal.signalMagnitude) * 100,
          probabilities: {
            pBull: signal.pBull,
            pSideways: signal.pSideways,
            pBear: signal.pBear,
          },
          persistence: pers,
        }
        if (fcast) {
          output.forecast = {
            days: ndays,
            pBull: fcast.bull,
            pSideways: fcast.sideways,
            pBear: fcast.bear,
            signal: fcast.bull - fcast.bear,
          }
        }
        if (ctx.args.store) output.persisted = true
        console.log(JSON.stringify(output, null, 2))
      } else {
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
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      if (asJson) {
        console.log(
          JSON.stringify({
            error: message,
            detail: "Regime computation failed",
            hint: `Check price data is synced: trading prices sync --ticker ${ticker}`,
          }),
        )
      } else {
        console.error(red(`Error: ${message}`))
      }
      process.exit(1)
    }
  },
})
