#!/usr/bin/env bun

/**
 * Regime Check — compute Markov regime state, transition matrix, and trading signal.
 *
 * Uses gum (charmbracelet/gum) for styled terminal output when available.
 * Falls back to plain ANSI if gum is not installed or stdout is not a TTY.
 *
 * Usage:
 *   trading regime AAPL              # current state + signal (gum if TTY)
 *   trading regime AAPL --forecast 2 # 2-day forecast
 *   trading regime AAPL --store      # persist to DB
 *   trading regime AAPL --json       # machine-readable JSON output
 *   trading regime AAPL --plain      # skip gum, use plain ANSI
 */

import { defineCommand } from "citty"
import { DatabaseFactory } from "../../lib/db.ts"
import { cfg } from "../../lib/settings.ts"
import {
  buildRegimeSignal,
  buildTransitionMatrix,
  findStationaryDistribution,
  generateStateStream,
  getPersistence,
  nDayProbabilities,
  signalToPositionSize,
  updateRegimeData,
  walkForwardBacktest,
  type WalkForwardResult,
} from "../../server/lib/markov/index.ts"
import { boxTable, gumStyle, isGumAvailable } from "../lib/gum-utils.ts"

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
function yellow(text: string) {
  return color(text, "\x1b[33m")
}

/** Render a mini bar (0-1) using Unicode blocks */
function bar(value: number, width: number = 10): string {
  const filled = Math.round(value * width)
  const empty = width - filled
  return "█".repeat(filled) + "░".repeat(empty)
}

/** Format signal with sign prefix */
function fmtSignal(s: number): string {
  return `${s >= 0 ? "+" : ""}${s.toFixed(4)}`
}

function stateLabel(state: string): string {
  switch (state) {
    case "bull":
      return green("▶ BULL")
    case "bear":
      return red("▼ BEAR")
    case "sideways":
      return yellow("■ SIDEWAYS")
    default:
      return state.toUpperCase()
  }
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

// ── Renderers ────────────────────────────────────────────────────────────────

interface RenderData {
  ticker: string
  date: string
  state: string
  lookbackDays: number
  signal: number
  signalDirection: string
  signalMagnitude: number
  pBull: number
  pSideways: number
  pBear: number
  matrix: {
    bull_to_bull: number
    bull_to_sideways: number
    bull_to_bear: number
    sideways_to_bull: number
    sideways_to_sideways: number
    sideways_to_bear: number
    bear_to_bull: number
    bear_to_sideways: number
    bear_to_bear: number
  }
  persistence: { bull: number; sideways: number; bear: number }
  forecast?: { days: number; bull: number; sideways: number; bear: number; signal: number }
  stationary?: { bull: number; sideways: number; bear: number }
  persisted: boolean
}

function renderGum(data: RenderData): string {
  const lines: string[] = []

  // ── Header ──
  lines.push(
    gumStyle(`Regime: ${data.ticker}`, {
      foreground: "#00d7ff",
      bold: true,
      border: "double",
      padding: "0 2",
      align: "center",
      width: 60,
    }),
  )
  lines.push("")

  // ── State + Signal row ──
  const stateIcon = data.state === "bull" ? "🟢" : data.state === "bear" ? "🔴" : "🟡"
  const stateLine = gumStyle(`${stateIcon} ${data.state.toUpperCase()}`, {
    bold: true,
    foreground: data.state === "bull" ? "#00ff00" : data.state === "bear" ? "#ff4444" : "#ffaa00",
  })
  const sigColor = data.signal >= 0 ? "#00ff00" : "#ff4444"
  const sigLine = gumStyle(`${fmtSignal(data.signal)}  ${data.signalDirection.toUpperCase()}`, {
    bold: true,
    foreground: sigColor,
  })

  lines.push(`  State    ${stateLine}    Signal   ${sigLine}`)
  lines.push(`  Date     ${data.date}  ·  ${data.lookbackDays} bars`)
  lines.push(`  Position ${(signalToPositionSize(data.signalMagnitude) * 100).toFixed(1)}%`)
  lines.push("")

  // ── Transition Matrix ──
  lines.push(gumStyle("Transition Matrix", { bold: true }))
  lines.push(
    boxTable(
      ["", "Bull", "Sideways", "Bear"],
      [
        [
          gumStyle("Bull", { bold: true, foreground: "#00ff00" }),
          data.matrix.bull_to_bull.toFixed(4),
          data.matrix.bull_to_sideways.toFixed(4),
          data.matrix.bull_to_bear.toFixed(4),
        ],
        [
          gumStyle("Side", { bold: true, foreground: "#ffaa00" }),
          data.matrix.sideways_to_bull.toFixed(4),
          data.matrix.sideways_to_sideways.toFixed(4),
          data.matrix.sideways_to_bear.toFixed(4),
        ],
        [
          gumStyle("Bear", { bold: true, foreground: "#ff4444" }),
          data.matrix.bear_to_bull.toFixed(4),
          data.matrix.bear_to_sideways.toFixed(4),
          data.matrix.bear_to_bear.toFixed(4),
        ],
      ],
    ),
  )
  lines.push("")

  // ── Next-Day Probabilities ──
  lines.push(gumStyle("Next-Day Probabilities", { bold: true }))
  lines.push(
    [
      `  P(${green("bull")})     ${data.pBull.toFixed(4)}  ${bar(data.pBull)}`,
      `  P(${yellow("sideways")}) ${data.pSideways.toFixed(4)}  ${bar(data.pSideways)}`,
      `  P(${red("bear")})     ${data.pBear.toFixed(4)}  ${bar(data.pBear)}`,
    ].join("\n"),
  )
  lines.push("")

  // ── Persistence ──
  lines.push(gumStyle("Persistence", { bold: true }))
  lines.push(
    [
      `  ${green("Bull")} ${bar(data.persistence.bull, 16)} ${data.persistence.bull.toFixed(4)}`,
      `  ${yellow("Side")} ${bar(data.persistence.sideways, 16)} ${data.persistence.sideways.toFixed(4)}`,
      `  ${red("Bear")} ${bar(data.persistence.bear, 16)} ${data.persistence.bear.toFixed(4)}`,
    ].join("\n"),
  )
  lines.push("")

  // ── Forecast ──
  if (data.forecast) {
    const fg = data.forecast
    lines.push(gumStyle(`${fg.days}-Day Forecast`, { bold: true }))
    lines.push(
      `  P(bull) ${fg.bull.toFixed(4)}  ·  P(sideways) ${fg.sideways.toFixed(4)}  ·  P(bear) ${fg.bear.toFixed(4)}`,
    )
    const fSig = fmtSignal(fg.signal)
    const fColor = fg.signal >= 0 ? "#00ff00" : "#ff4444"
    lines.push(`  Signal  ${gumStyle(fSig, { bold: true, foreground: fColor })}`)
    lines.push("")
  }

  // ── Stationary Distribution ──
  if (data.stationary) {
    const s = data.stationary
    lines.push("")
    lines.push(gumStyle("Stationary Distribution (long-run)", { bold: true }))
    lines.push(
      [
        `  ${green("Bull")} ${bar(s.bull, 16)} ${(s.bull * 100).toFixed(1)}%`,
        `  ${yellow("Side")} ${bar(s.sideways, 16)} ${(s.sideways * 100).toFixed(1)}%`,
        `  ${red("Bear")} ${bar(s.bear, 16)} ${(s.bear * 100).toFixed(1)}%`,
      ].join("\n"),
    )
  }

  // ── Footer ──
  if (data.persisted) {
    lines.push(gumStyle("✓ persisted to DB", { foreground: "#00ff00", bold: true }))
  }

  return lines.join("\n")
}

function renderPlain(data: RenderData): string {
  const lines: string[] = []

  lines.push("")
  lines.push(cyan(`=== Regime: ${data.ticker} ===`))
  lines.push("")
  lines.push(`${"State:".padEnd(20)} ${stateLabel(data.state)}`)
  lines.push(`${"Date:".padEnd(20)} ${data.date}`)
  lines.push(`${"Lookback:".padEnd(20)} ${data.lookbackDays} bars`)
  lines.push("")
  const sigStr = fmtSignal(data.signal)
  lines.push(`${"Signal:".padEnd(20)} ${data.signal >= 0 ? green(sigStr) : red(sigStr)}`)
  lines.push(`${"Direction:".padEnd(20)} ${data.signalDirection}`)
  lines.push(`${"Magnitude:".padEnd(20)} ${data.signalMagnitude.toFixed(4)}`)
  lines.push(
    `${"Position size:".padEnd(20)} ${(signalToPositionSize(data.signalMagnitude) * 100).toFixed(1)}%`,
  )
  lines.push("")

  lines.push("Transition Matrix:")
  lines.push(
    boxTable(
      ["", "Bull", "Sideways", "Bear"],
      [
        [
          green("Bull"),
          data.matrix.bull_to_bull.toFixed(4),
          data.matrix.bull_to_sideways.toFixed(4),
          data.matrix.bull_to_bear.toFixed(4),
        ],
        [
          yellow("Side"),
          data.matrix.sideways_to_bull.toFixed(4),
          data.matrix.sideways_to_sideways.toFixed(4),
          data.matrix.sideways_to_bear.toFixed(4),
        ],
        [
          red("Bear"),
          data.matrix.bear_to_bull.toFixed(4),
          data.matrix.bear_to_sideways.toFixed(4),
          data.matrix.bear_to_bear.toFixed(4),
        ],
      ],
    ),
  )
  lines.push("")

  lines.push("Next-day probabilities:")
  lines.push(`  P(bull):     ${data.pBull.toFixed(4)}`)
  lines.push(`  P(sideways): ${data.pSideways.toFixed(4)}`)
  lines.push(`  P(bear):     ${data.pBear.toFixed(4)}`)
  lines.push("")

  if (data.forecast) {
    const fg = data.forecast
    lines.push(`${fg.days}-day forecast:`)
    lines.push(`  P(bull):     ${fg.bull.toFixed(4)}`)
    lines.push(`  P(sideways): ${fg.sideways.toFixed(4)}`)
    lines.push(`  P(bear):     ${fg.bear.toFixed(4)}`)
    lines.push(`  Signal:      ${fmtSignal(fg.signal)}`)
    lines.push("")
  }

  lines.push("Persistence (stickiness):")
  lines.push(
    `  ${green("Bull")} ${bar(data.persistence.bull, 16)} ${data.persistence.bull.toFixed(4)}`,
  )
  lines.push(
    `  ${yellow("Side")} ${bar(data.persistence.sideways, 16)} ${data.persistence.sideways.toFixed(4)}`,
  )
  lines.push(
    `  ${red("Bear")} ${bar(data.persistence.bear, 16)} ${data.persistence.bear.toFixed(4)}`,
  )
  lines.push("")

  if (data.stationary) {
    const s = data.stationary
    lines.push("Stationary Distribution (long-run π = πP):")
    lines.push(
      `  ${green("Bull")} ${bar(s.bull, 16)} ${(s.bull * 100).toFixed(1)}%`,
    )
    lines.push(
      `  ${yellow("Side")} ${bar(s.sideways, 16)} ${(s.sideways * 100).toFixed(1)}%`,
    )
    lines.push(
      `  ${red("Bear")} ${bar(s.bear, 16)} ${(s.bear * 100).toFixed(1)}%`,
    )
    lines.push("")
  }

  if (data.persisted) {
    lines.push(green("✓ persisted to DB"))
  } else {
    lines.push("Run with --store to persist.")
  }
  lines.push("")

  return lines.join("\n")
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
    "--plain": {
      type: "boolean",
      description: "Skip gum styling, use plain ANSI output",
    },
    "--stationary": {
      type: "boolean",
      description: "Show long-run stationary distribution (π = πP)",
    },
    "--backtest": {
      type: "boolean",
      description: "Run walk-forward backtest (no data leakage)",
    },
  },
  run: async (ctx) => {
    const ticker = ctx.args.ticker as string
    const forecastDays = parseInt((ctx.args.forecast as string) ?? "0", 10) || 0
    const asJson = (ctx.args.json as boolean) ?? false
    const plain = (ctx.args.plain as boolean) ?? false
    const useGum = !plain && isGumAvailable()

    DatabaseFactory.connect(cfg.portfolio.db)

    try {
      // Step 1: Read price history
      const { prices, dates } = getPriceHistory(ticker)

      // ── Backtest mode ─────────────────────────────────────────────────
      if (ctx.args.backtest) {
        const result = walkForwardBacktest(prices, dates, { verbose: false })

        if (asJson) {
          console.log(JSON.stringify({
            ticker,
            ...result,
            regimeDistribution: result.regimeDistribution,
          }, null, 2))
          return
        }

        const lines: string[] = []
        lines.push(cyan(`\n=== Walk-Forward Backtest: ${ticker} ===\n`))
        lines.push(`${"Period:".padEnd(20)} ${result.startDate} → ${result.endDate} (${result.totalDays} days)`)
        lines.push(`${"Sharpe:".padEnd(20)} ${result.sharpe >= 0 ? green : red}${result.sharpe.toFixed(4)}`)
        lines.push(`${"Ann Return:".padEnd(20)} ${(result.annualReturn * 100).toFixed(2)}%`)
        lines.push(`${"Buy & Hold:".padEnd(20)} ${(result.buyAndHoldReturn * 100).toFixed(2)}%`)
        lines.push(`${"Max Drawdown:".padEnd(20)} ${red((result.maxDrawdown * 100).toFixed(2) + "%")}`)
        lines.push(`${"Win Rate:".padEnd(20)} ${(result.winRate * 100).toFixed(1)}% (${result.tradeCount} trades)`)
        lines.push("")
        lines.push("Regime Distribution:")
        lines.push(`  ${green("Bull")} ${bar(result.regimeDistribution.bull, 16)} ${(result.regimeDistribution.bull * 100).toFixed(1)}%`)
        lines.push(`  ${yellow("Side")} ${bar(result.regimeDistribution.sideways, 16)} ${(result.regimeDistribution.sideways * 100).toFixed(1)}%`)
        lines.push(`  ${red("Bear")} ${bar(result.regimeDistribution.bear, 16)} ${(result.regimeDistribution.bear * 100).toFixed(1)}%`)

        // Comparison summary
        const outperformance = result.annualReturn - result.buyAndHoldReturn
        if (outperformance > 0) {
          lines.push(green(`\n  Strategy outperformed buy-and-hold by ${(outperformance * 100).toFixed(2)}%`))
        } else {
          lines.push(red(`\n  Strategy underperformed buy-and-hold by ${(Math.abs(outperformance) * 100).toFixed(2)}%`))
        }
        lines.push("")

        if (useGum) {
          console.log(gumStyle(lines.join("\n"), { padding: "1 2" }))
        } else {
          console.log(lines.join("\n"))
        }
        return
      }

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
      const signal = ctx.args.store
        ? updateRegimeData(ticker)
        : buildRegimeSignal(ticker, currentDate, currentState, matrix)

      const ndays = forecastDays
      const fcast = ndays > 0 ? nDayProbabilities(matrix, currentState, ndays) : null
      const pers = getPersistence(matrix)
      const showStationary = (ctx.args.stationary as boolean) ?? false
      const station = showStationary ? findStationaryDistribution(matrix) : null

      // ── Output ──────────────────────────────────────────────────────────

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
        if (station) {
          output.stationary = station
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
        return
      }

      const data: RenderData = {
        ticker,
        date: currentDate,
        state: signal.currentState,
        lookbackDays,
        signal: signal.signal,
        signalDirection: signal.signalDirection,
        signalMagnitude: signal.signalMagnitude,
        pBull: signal.pBull,
        pSideways: signal.pSideways,
        pBear: signal.pBear,
        matrix,
        persistence: pers,
        stationary: station ?? undefined,
        persisted: !!ctx.args.store,
      }

      if (fcast) {
        data.forecast = {
          days: ndays,
          bull: fcast.bull,
          sideways: fcast.sideways,
          bear: fcast.bear,
          signal: fcast.bull - fcast.bear,
        }
      }

      if (useGum) {
        console.log(renderGum(data))
      } else {
        console.log(renderPlain(data))
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
