/**
 * Markov Regime Detection — Walk-Forward Backtest
 *
 * Reproduces the article's Part 4 walk-forward structure in TypeScript.
 * For each day T from lookback_window to end of history:
 *   1. Build transition matrix using ONLY data up to day T (no future data)
 *   2. Generate signal for day T
 *   3. Apply signal to day T+1 returns
 *   4. Advance one day, repeat
 *
 * This prevents lookahead bias — the matrix at T uses only information
 * available at T, not the full retrospective dataset.
 */

import { buildTransitionMatrix, type TransitionMatrix } from "./matrix.js"
import { computeSignal } from "./signal.js"
import { classifyState, type MarketState } from "./state.js"
import { findStationaryDistribution } from "./stationary.js"

// ── Types ────────────────────────────────────────────────────────────────────

export interface WalkForwardResult {
  /** Daily strategy returns for each signal day */
  returns: number[]
  /** Raw signal values per day (pre-thresholding) */
  signals: number[]
  /** Cumulative equity curve */
  cumulativeReturns: number[]
  /** Annualized Sharpe ratio */
  sharpe: number
  /** Maximum drawdown as a decimal (e.g. 0.15 = 15%) */
  maxDrawdown: number
  /** Annualized return */
  annualReturn: number
  /** Number of days with non-zero position (trade days) */
  tradeCount: number
  /** Percentage of profitable days when positioned */
  winRate: number
  /** Distribution of regimes over the trading period */
  regimeDistribution: { bull: number; sideways: number; bear: number }
  /** Buy-and-hold annualized return for comparison */
  buyAndHoldReturn: number
  /** Start date of the backtest */
  startDate: string
  /** End date of the backtest */
  endDate: string
  /** Number of total trading days in the backtest */
  totalDays: number
}

export interface WalkForwardConfig {
  /** Minimum number of days needed for reliable matrix (default: 252 = 1 trading year) */
  lookbackWindow?: number
  /** Threshold for neutral position: |signal| < neutralThreshold → flat (default: 0.1) */
  neutralThreshold?: number
  /** Position sizing divisor: signal / sizingDivisor, clamped to [-1, 1] (default: 0.3) */
  sizingDivisor?: number
  /** Whether to log progress to console */
  verbose?: boolean
}

const DEFAULT_CONFIG: Required<WalkForwardConfig> = {
  lookbackWindow: 252,
  neutralThreshold: 0.1,
  sizingDivisor: 0.3,
  verbose: false,
}

// ── Implementation ───────────────────────────────────────────────────────────

/**
 * Run a walk-forward backtest using daily price data.
 *
 * Uses incremental state sliding — on each day, we re-classify states
 * from the historical window and rebuild the transition matrix.
 * No future data leaks into any matrix computation.
 *
 * @param prices - array of daily closing prices (oldest first)
 * @param dates - array of date strings aligned with prices (YYYY-MM-DD)
 * @param config - backtest configuration
 * @returns WalkForwardResult with full equity curve and metrics
 */
export function walkForwardBacktest(
  prices: number[],
  dates: string[],
  config: WalkForwardConfig = {},
): WalkForwardResult {
  const {
    lookbackWindow,
    neutralThreshold,
    sizingDivisor,
    verbose,
  } = { ...DEFAULT_CONFIG, ...config }

  if (prices.length < lookbackWindow + 20) {
    throw new Error(
      `Insufficient history: need at least ${lookbackWindow + 20} prices ` +
      `(${lookbackWindow} lookback + 20 state bars), got ${prices.length}`,
    )
  }

  if (prices.length !== dates.length) {
    throw new Error(`Price/date length mismatch: ${prices.length} vs ${dates.length}`)
  }

  // Compute daily returns for the entire series
  const dailyReturns: number[] = []
  for (let i = 1; i < prices.length; i++) {
    dailyReturns.push((prices[i]! - prices[i - 1]!) / prices[i - 1]!)
  }

  const strategyReturns: number[] = []
  const signalValues: number[] = []
  let equity = 1.0
  let peak = 1.0
  let maxDrawdownValue = 0.0
  let tradeDays = 0
  let winningDays = 0

  // Tracks regime counts over the walk-forward period for distribution
  const regimeCounts = { bull: 0, sideways: 0, bear: 0 }

  // We need at least lookbackWindow + 20 bars before the first signal point.
  // State classification uses 20 bars of prices.
  // The first signal day has lookbackWindow prices available for matrix build.
  const firstSignalIdx = lookbackWindow + 20

  for (let t = firstSignalIdx; t < prices.length; t++) {
    // ── Build matrix from data up to day T (inclusive) ──
    const windowPrices = prices.slice(0, t + 1)

    // Classify states from window
    const states: MarketState[] = []
    for (let i = 20; i < windowPrices.length; i++) {
      const startPrice = windowPrices[i - 20]!
      const endPrice = windowPrices[i]!
      const cumulativeReturn = (endPrice - startPrice) / startPrice
      states.push(classifyStateFromReturn(cumulativeReturn))
    }

    if (states.length < 2) continue

    const matrix = buildTransitionMatrix(states)
    const currentState = states[states.length - 1]!

    regimeCounts[currentState]++

    // ── Generate signal ──
    const { signal } = computeSignal(matrix, currentState)
    signalValues.push(signal)

    // ── Position sizing ──
    let positionSize = 0
    if (Math.abs(signal) >= neutralThreshold) {
      positionSize = signal / sizingDivisor
      // Clamp to [-1, 1]
      positionSize = Math.max(-1, Math.min(1, positionSize))
    }

    // ── Apply to next day's return (t → t+1) ──
    if (t + 1 < prices.length) {
      const nextReturn = dailyReturns[t]! // dailyReturns is offset by 1
      const strategyReturn = positionSize * nextReturn
      strategyReturns.push(strategyReturn)

      equity *= (1 + strategyReturn)
      if (equity > peak) peak = equity
      const drawdown = (peak - equity) / peak
      if (drawdown > maxDrawdownValue) maxDrawdownValue = drawdown

      if (positionSize !== 0) {
        tradeDays++
        if (strategyReturn > 0) winningDays++
      }
    }
  }

  // ── Metrics computation ──
  const totalDays = strategyReturns.length
  const tradingDaysPerYear = 252

  const meanReturn = totalDays > 0
    ? strategyReturns.reduce((a, b) => a + b, 0) / totalDays
    : 0
  const variance = totalDays > 1
    ? strategyReturns.reduce((a, b) => a + (b - meanReturn) ** 2, 0) / (totalDays - 1)
    : 0
  const stdDev = Math.sqrt(variance)
  const sharpe = stdDev > 0
    ? (meanReturn / stdDev) * Math.sqrt(tradingDaysPerYear)
    : 0
  const annualReturn = totalDays > 0
    ? (1 + meanReturn) ** tradingDaysPerYear - 1
    : 0

  const winRate = tradeDays > 0 ? winningDays / tradeDays : 0

  // Buy-and-hold comparison
  const buyAndHoldReturn = totalDays > 0
    ? (1 + (prices[prices.length - 1]! - prices[firstSignalIdx]!) / prices[firstSignalIdx]!) ** (tradingDaysPerYear / totalDays) - 1
    : 0

  // Cumulative returns
  const cumulativeReturns: number[] = []
  let cumEq = 1.0
  for (const r of strategyReturns) {
    cumEq *= (1 + r)
    cumulativeReturns.push(cumEq)
  }

  const totalRegimes = regimeCounts.bull + regimeCounts.sideways + regimeCounts.bear
  const regimeDistribution = totalRegimes > 0
    ? {
        bull: regimeCounts.bull / totalRegimes,
        sideways: regimeCounts.sideways / totalRegimes,
        bear: regimeCounts.bear / totalRegimes,
      }
    : { bull: 0, sideways: 0, bear: 0 }

  return {
    returns: strategyReturns,
    signals: signalValues,
    cumulativeReturns,
    sharpe,
    maxDrawdown: maxDrawdownValue,
    annualReturn,
    buyAndHoldReturn,
    tradeCount: tradeDays,
    winRate,
    regimeDistribution,
    startDate: dates[firstSignalIdx]!,
    endDate: dates[dates.length - 1]!,
    totalDays,
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Direct cumulative-return classification (avoids array creation). */
function classifyStateFromReturn(cumulativeReturn: number): MarketState {
  if (cumulativeReturn >= 0.05) return "bull"
  if (cumulativeReturn <= -0.05) return "bear"
  return "sideways"
}

// ── Tests ────────────────────────────────────────────────────────────────────

/**
 * Run walk-forward backtest unit tests using synthetic price data.
 * Returns true if all pass.
 */
export function testWalkForward(): boolean {
  let allPass = true
  const check = (name: string, cond: boolean) => {
    if (!cond) { console.error(`  ✗ ${name}`); allPass = false }
    else console.log(`  ✓ ${name}`)
  }

  console.log("\n=== Walk-Forward Backtest Tests ===\n")

  // Generate synthetic price data: 600 days of random walk with slight bull bias
  const nprices = 600
  const prices: number[] = [100]
  for (let i = 1; i < nprices; i++) {
    const shock = (Math.random() - 0.48) * 0.04  // Mean ~0.0008, std ~0.0116
    prices.push(prices[i - 1]! * (1 + shock))
  }

  const dates: string[] = prices.map((_, i) => {
    const d = new Date("2024-01-01")
    d.setDate(d.getDate() + i)
    return d.toISOString().split("T")[0]!
  })

  // Run backtest
  const result = walkForwardBacktest(prices, dates, { verbose: false })

  check("Result is defined", result != null)
  check("Has returns", result.returns.length > 0)
  check("Has signals", result.signals.length > 0)
  check("Has cumulative returns", result.cumulativeReturns.length > 0)
  check("Sharpe is finite", isFinite(result.sharpe))
  check("Sharpe range reasonable", Math.abs(result.sharpe) < 10)
  check("Max drawdown is finite", isFinite(result.maxDrawdown))
  check("Max drawdown range [0,1]", result.maxDrawdown >= 0 && result.maxDrawdown <= 1)
  check("Annual return is finite", isFinite(result.annualReturn))
  check("Trade count > 0", result.tradeCount > 0)
  check("Win rate in [0,1]", result.winRate >= 0 && result.winRate <= 1)
  check("Regime distribution sums to 1",
    Math.abs(result.regimeDistribution.bull + result.regimeDistribution.sideways + result.regimeDistribution.bear - 1.0) < 1e-10,
  )
  check("Start date before end date", result.startDate < result.endDate)
  check("Total days positive", result.totalDays > 0)
  check("Returns match totalDays", result.returns.length === result.totalDays)

  console.log(`\n  Backtest summary:`)
  console.log(`    Days: ${result.totalDays}`)
  console.log(`    Sharpe: ${result.sharpe.toFixed(4)}`)
  console.log(`    AnnReturn: ${(result.annualReturn * 100).toFixed(2)}%`)
  console.log(`    Buy&Hold: ${(result.buyAndHoldReturn * 100).toFixed(2)}%`)
  console.log(`    MaxDD: ${(result.maxDrawdown * 100).toFixed(2)}%`)
  console.log(`    WinRate: ${(result.winRate * 100).toFixed(1)}% (${result.tradeCount} trades)`)
  console.log(`    Regimes: Bull ${(result.regimeDistribution.bull * 100).toFixed(0)}% Side ${(result.regimeDistribution.sideways * 100).toFixed(0)}% Bear ${(result.regimeDistribution.bear * 100).toFixed(0)}%`)

  // ── Boundary test: too few prices ──
  try {
    walkForwardBacktest([100, 101], ["2024-01-01", "2024-01-02"])
    check("Too-few prices throws", false)
  } catch (e) {
    check("Too-few prices throws", e instanceof Error && e.message.includes("Insufficient"))
  }

  // ── Boundary test: exact minimum ──
  // 252 lookback + 20 state bars + 1 signal index + 1 return day = 274
  const exactCount = 252 + 20 + 2
  const exactPrices: number[] = []
  for (let i = 0; i < exactCount; i++) exactPrices.push(100 + i * 0.1)
  const exactDates: string[] = exactPrices.map((_, i) => {
    const d = new Date("2024-01-01")
    d.setDate(d.getDate() + i)
    return d.toISOString().split("T")[0]!
  })
  const minResult = walkForwardBacktest(exactPrices, exactDates, { lookbackWindow: 252 })
  check("Exact minimum: returns produced", minResult.returns.length > 0)
  check("Exact minimum: single signal day", minResult.returns.length === 1)

  if (allPass) {
    console.log("\n✓ All walk-forward backtest tests passed\n")
  } else {
    console.log("\n✗ Some tests failed\n")
  }
  return allPass
}