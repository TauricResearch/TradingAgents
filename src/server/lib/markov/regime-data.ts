/**
 * Markov Regime Detection — Data Layer
 *
 * Reads/writes regime states and transition matrices to SQLite.
 * All access MUST go through DatabaseFactory.
 */

import { DatabaseFactory } from "@lib/db"
import type { WalkForwardResult } from "./backtest.js"
import type { HmmResult } from "./hmm.js"
import type { TransitionMatrix } from "./matrix.js"
import { buildTransitionMatrix } from "./matrix.js"
import { buildRegimeSignal, type RegimeSignal } from "./signal.js"
import { type DailyState, generateStateStream, type MarketState } from "./state.js"

// ── Types ────────────────────────────────────────────────────────────────────

// Re-export DailyState from state.ts for convenience
export type { DailyState }

type DbRegimeState = {
  ticker: string
  date: string
  state: string
  cumulative_return: number
}

type DbRegimeMatrix = {
  ticker: string
  as_of_date: string
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

// ── Regime States ────────────────────────────────────────────────────────────

/**
 * Insert or replace a daily regime state.
 */
export function upsertRegimeState(state: DailyState): void {
  const db = DatabaseFactory.get()
  db.query(
    `INSERT OR REPLACE INTO regime_states (ticker, date, state, cumulative_return)
     VALUES (?, ?, ?, ?)`,
  ).run(state.ticker, state.date, state.state, state.cumulativeReturn)
}

/**
 * Batch insert regime states from a daily state stream.
 */
export function insertRegimeStates(states: DailyState[]): void {
  const db = DatabaseFactory.get()
  const stmt = db.prepare(
    `INSERT OR REPLACE INTO regime_states (ticker, date, state, cumulative_return)
     VALUES (?, ?, ?, ?)`,
  )
  for (const s of states) {
    stmt.run(s.ticker, s.date, s.state, s.cumulativeReturn)
  }
}

/**
 * Get regime state history for a ticker, ordered by date ascending.
 */
export function getRegimeStates(ticker: string): DailyState[] {
  const db = DatabaseFactory.get()
  const rows = db
    .query("SELECT * FROM regime_states WHERE ticker = ? ORDER BY date ASC")
    .all(ticker) as DbRegimeState[]
  return rows.map((r) => ({
    ticker: r.ticker,
    date: r.date,
    state: r.state as MarketState,
    cumulativeReturn: parseFloat(String(r.cumulative_return)),
  }))
}

/**
 * Get the most recent regime state for a ticker.
 */
export function getLatestRegimeState(ticker: string): DailyState | null {
  const db = DatabaseFactory.get()
  const row = db
    .query("SELECT * FROM regime_states WHERE ticker = ? ORDER BY date DESC LIMIT 1")
    .get(ticker) as DbRegimeState | undefined
  if (!row) return null
  return {
    ticker: row.ticker,
    date: row.date,
    state: row.state as MarketState,
    cumulativeReturn: parseFloat(String(row.cumulative_return)),
  }
}

// ── Regime Matrices ──────────────────────────────────────────────────────────

/**
 * Store a transition matrix for a ticker on a given date.
 */
export function insertRegimeMatrix(
  ticker: string,
  asOfDate: string,
  matrix: TransitionMatrix,
): void {
  const db = DatabaseFactory.get()
  db.query(
    `INSERT OR REPLACE INTO regime_matrices
     (ticker, as_of_date, bull_to_bull, bull_to_sideways, bull_to_bear,
      sideways_to_bull, sideways_to_sideways, sideways_to_bear,
      bear_to_bull, bear_to_sideways, bear_to_bear)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    ticker,
    asOfDate,
    matrix.bull_to_bull,
    matrix.bull_to_sideways,
    matrix.bull_to_bear,
    matrix.sideways_to_bull,
    matrix.sideways_to_sideways,
    matrix.sideways_to_bear,
    matrix.bear_to_bull,
    matrix.bear_to_sideways,
    matrix.bear_to_bear,
  )
}

// ── Orchestration (FR-6) ─────────────────────────────────────────────────────

/**
 * Update regime data for a ticker: read prices, classify states, build matrix,
 * persist to DB, and return the current RegimeSignal.
 *
 * This is the primary entry point for the daily regime update pipeline.
 */
export function updateRegimeData(ticker: string): RegimeSignal {
  const db = DatabaseFactory.get()

  // 1. Read price history
  const rows = db
    .query("SELECT date, close FROM prices WHERE ticker = ? ORDER BY date ASC")
    .all(ticker) as Array<{ date: string; close: number }>

  if (rows.length < 21) {
    throw new Error(
      `Insufficient price history for ${ticker}: ${rows.length} bars (need ≥21 for 20-bar lookback)`,
    )
  }

  const prices = rows.map((r) => parseFloat(String(r.close)))
  const dates = rows.map((r) => r.date)

  // 2. Classify states from price history
  const stateStream = generateStateStream(ticker, prices, dates)
  const states = stateStream.map((s) => s.state)

  if (states.length < 20) {
    throw new Error(
      `Insufficient state history for ${ticker}: ${states.length} states (need ≥20 for reliable signal)`,
    )
  }

  // 3. Build transition matrix
  const matrix = buildTransitionMatrix(states)
  const currentState = states[states.length - 1]!
  const currentDate = dates[dates.length - 1]!

  // 4. Generate signal
  const signal = buildRegimeSignal(ticker, currentDate, currentState, matrix)

  // 5. Persist states and matrix
  insertRegimeStates(stateStream)

  // Compute cumulative return for the latest state
  const lookbackPrices = prices.slice(-21)
  const cumulativeReturn =
    (lookbackPrices[lookbackPrices.length - 1]! - lookbackPrices[0]!) / lookbackPrices[0]!

  upsertRegimeState({
    ticker,
    date: currentDate,
    state: currentState,
    cumulativeReturn: cumulativeReturn,
  })

  insertRegimeMatrix(ticker, currentDate, matrix)

  return signal
}

/**
 * Get the most recent transition matrix for a ticker.
 */
export function getLatestRegimeMatrix(
  ticker: string,
): { matrix: TransitionMatrix; asOfDate: string } | null {
  const db = DatabaseFactory.get()
  const row = db
    .query("SELECT * FROM regime_matrices WHERE ticker = ? ORDER BY as_of_date DESC LIMIT 1")
    .get(ticker) as DbRegimeMatrix | undefined
  if (!row) return null
  return {
    asOfDate: row.as_of_date,
    matrix: {
      bull_to_bull: parseFloat(String(row.bull_to_bull)),
      bull_to_sideways: parseFloat(String(row.bull_to_sideways)),
      bull_to_bear: parseFloat(String(row.bull_to_bear)),
      sideways_to_bull: parseFloat(String(row.sideways_to_bull)),
      sideways_to_sideways: parseFloat(String(row.sideways_to_sideways)),
      sideways_to_bear: parseFloat(String(row.sideways_to_bear)),
      bear_to_bull: parseFloat(String(row.bear_to_bull)),
      bear_to_sideways: parseFloat(String(row.bear_to_sideways)),
      bear_to_bear: parseFloat(String(row.bear_to_bear)),
    },
  }
}

// ── Walk-Forward Backtests (MARKOV-002-S02) ─────────────────────────────────

/**
 * Persist a walk-forward backtest result. One row per (ticker, run_date).
 * REAL columns are stored as-is; callers read with parseFloat().
 */
export function insertRegimeBacktest(
  ticker: string,
  result: WalkForwardResult,
  lookbackWindow: number = 252,
): void {
  const db = DatabaseFactory.get()
  db.query(
    `INSERT OR REPLACE INTO regime_backtests
     (ticker, lookback_window, sharpe, max_drawdown, annual_return, buy_and_hold,
      trade_count, win_rate, bull_pct, sideways_pct, bear_pct, total_days)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    ticker,
    lookbackWindow,
    result.sharpe,
    result.maxDrawdown,
    result.annualReturn,
    result.buyAndHoldReturn,
    result.tradeCount,
    result.winRate,
    result.regimeDistribution.bull,
    result.regimeDistribution.sideways,
    result.regimeDistribution.bear,
    result.totalDays,
  )
}

// ── HMM Fitted Models (MARKOV-002-S03) ───────────────────────────────────────

/**
 * Persist an HMM fit. The learned transition matrix is stored as JSON
 * (array of arrays) in transition_matrix_json.
 */
export function insertRegimeHmmModel(ticker: string, hmm: HmmResult): void {
  const db = DatabaseFactory.get()
  const [bullMean, sidewaysMean, bearMean] = hmm.stateMeans
  const [bullVol, sidewaysVol, bearVol] = hmm.stateVols
  db.query(
    `INSERT OR REPLACE INTO regime_hmm_models
     (ticker, n_states, log_likelihood, converged,
      bull_mean, bull_vol, sideways_mean, sideways_vol, bear_mean, bear_vol,
      transition_matrix_json)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    ticker,
    hmm.stateMeans.length,
    hmm.logLikelihood,
    hmm.converged ? 1 : 0,
    bullMean!,
    bullVol!,
    sidewaysMean!,
    sidewaysVol!,
    bearMean!,
    bearVol!,
    JSON.stringify(hmm.transitionMatrix),
  )
}
