/**
 * Strategic Trade Calculator — pure functions for bracket order planning.
 *
 * Converts historical price data into a complete trade execution plan:
 *   - Volatility-adjusted entry zone
 *   - Technical profit targets (Fibonacci extensions)
 *   - Risk-managed stop loss (2× ATR)
 *   - Position sizing (2% rule)
 *
 * All functions are pure: no I/O, no side effects, no database access.
 * Input: price history array. Output: TradePlan object.
 */

// ── Types ───────────────────────────────────────────────────────────────────

export interface PriceBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface TradePlan {
  ticker: string
  entry: number
  stopLoss: number
  target1: number
  target2: number
  positionSize: number
  riskAmount: number
  riskPercent: number
  atr14: number
  concentrationFlag: boolean
  swingLow: number
  swingHigh: number
  insufficientHistory: boolean
}

export interface TradePlanInput {
  ticker: string
  priceHistory: PriceBar[]
  accountBalance: number
  riskPerTrade?: number // default 0.02
  entryPrice?: number // optional override
}

// ── Public API ──────────────────────────────────────────────────────────────

/**
 * Calculate a complete trade plan from price history and account parameters.
 *
 * Minimum history: 22 days (14 for ATR + 8 for swing detection).
 * If history is insufficient, returns a plan with `insufficientHistory: true`
 * and best-effort values.
 */
export function calculateTradePlan(input: TradePlanInput): TradePlan {
  const { ticker, priceHistory, accountBalance, riskPerTrade = 0.02, entryPrice } = input

  if (priceHistory.length === 0) {
    throw new Error("Price history is empty")
  }

  const sorted = [...priceHistory].sort((a, b) => a.date.localeCompare(b.date))
  const latest = sorted[sorted.length - 1]!
  const entry = entryPrice ?? latest.close

  // ATR requires at least 15 bars (14 periods + 1 prior close)
  const hasAtrData = sorted.length >= 15
  const atr = hasAtrData ? calculateATR(sorted, 14) : estimateATR(sorted)

  // Swing detection requires at least 22 bars
  const hasSwingData = sorted.length >= 22
  const { swingLow, swingHigh } = hasSwingData
    ? findSwingHighLow(sorted)
    : {
        swingLow: Math.min(...sorted.map((b) => b.low)),
        swingHigh: Math.max(...sorted.map((b) => b.high)),
      }

  const abMove = swingHigh - swingLow

  // Stop loss: 2× ATR below entry
  const stopLoss = entry - 2.0 * atr

  // Target 1: 138.2% Fibonacci extension of AB move
  const target1 = swingHigh + abMove * 1.382

  // Target 2: max of 161.8% Fib extension OR 1:2 risk/reward minimum
  const fibTarget2 = swingHigh + abMove * 1.618
  const risk = entry - stopLoss
  const minRewardTarget = risk > 0 ? entry + 2.0 * risk : entry * 1.02
  const target2 = Math.max(fibTarget2, minRewardTarget)

  // Position sizing: (account × risk%) / (entry - stop)
  const riskPerShare = entry - stopLoss
  const rawPositionSize = riskPerShare > 0 ? (accountBalance * riskPerTrade) / riskPerShare : 0
  const positionSize = Math.max(0, Math.floor(rawPositionSize))

  const riskAmount = positionSize * riskPerShare
  const riskPercent = accountBalance > 0 ? riskAmount / accountBalance : 0

  const positionValue = positionSize * entry
  const concentrationFlag = accountBalance > 0 && positionValue > accountBalance * 0.05

  return {
    ticker,
    entry: round2(entry),
    stopLoss: round2(stopLoss),
    target1: round2(target1),
    target2: round2(target2),
    positionSize,
    riskAmount: round2(riskAmount),
    riskPercent: round4(riskPercent),
    atr14: round4(atr),
    concentrationFlag,
    swingLow: round2(swingLow),
    swingHigh: round2(swingHigh),
    insufficientHistory: !hasAtrData || !hasSwingData,
  }
}

// ── Pure Functions ────────────────────────────────────────────────────────

/**
 * Calculate the Average True Range (ATR) over n periods.
 *
 * Formula: ATR = SMA of True Range over n periods
 * True Range = max(high-low, |high-prev_close|, |low-prev_close|)
 *
 * Requires at least n+1 bars (n periods + 1 prior close).
 */
export function calculateATR(bars: PriceBar[], n = 14): number {
  if (bars.length < n + 1) {
    return estimateATR(bars)
  }

  const trValues: number[] = []

  for (let i = 1; i < bars.length; i++) {
    const curr = bars[i]!
    const prev = bars[i - 1]!
    const tr = Math.max(
      curr.high - curr.low,
      Math.abs(curr.high - prev.close),
      Math.abs(curr.low - prev.close),
    )
    trValues.push(tr)
  }

  // Use the last n TR values
  const relevant = trValues.slice(-n)
  return relevant.reduce((sum, v) => sum + v, 0) / relevant.length
}

/**
 * Estimate ATR when insufficient history exists.
 * Fallback: average of (high - low) over available bars.
 */
export function estimateATR(bars: PriceBar[]): number {
  if (bars.length === 0) return 0
  const ranges = bars.map((b) => b.high - b.low)
  return ranges.reduce((sum, r) => sum + r, 0) / ranges.length
}

/**
 * Find the AB swing: Point A (swing low) and Point B (swing high).
 *
 * Algorithm:
 *   1. Point A = lowest low in the lookback window (last 22 bars)
 *   2. Point B = highest high between Point A and the latest bar
 *
 * If no clear swing (strong trend), uses min/max of the window.
 */
export function findSwingHighLow(bars: PriceBar[]): { swingLow: number; swingHigh: number } {
  if (bars.length === 0) return { swingLow: 0, swingHigh: 0 }

  // Use last 22 bars for swing detection
  const window = bars.length >= 22 ? bars.slice(-22) : bars

  let swingLow = window[0]!.low
  let swingLowIdx = 0

  for (let i = 1; i < window.length; i++) {
    const bar = window[i]!
    if (bar.low < swingLow) {
      swingLow = bar.low
      swingLowIdx = i
    }
  }

  // Point B: highest high after Point A
  let swingHigh = window[swingLowIdx]!.high
  for (let i = swingLowIdx + 1; i < window.length; i++) {
    const bar = window[i]!
    if (bar.high > swingHigh) {
      swingHigh = bar.high
    }
  }

  // Edge case: if B <= A (flat or inverted), use global min/max
  if (swingHigh <= swingLow) {
    swingLow = Math.min(...window.map((b) => b.low))
    swingHigh = Math.max(...window.map((b) => b.high))
  }

  return { swingLow, swingHigh }
}

/**
 * Calculate Fibonacci extension levels from an AB move.
 *
 * Extensions are measured from Point B outward:
 *   level = B + (B - A) × ratio
 *
 * Common ratios: 1.272, 1.382, 1.618, 2.0, 2.618
 */
export function fibonacciExtension(
  a: number,
  b: number,
  ratios: number[] = [1.382, 1.618],
): number[] {
  const move = b - a
  return ratios.map((r) => b + move * r)
}

// ── Helpers ───────────────────────────────────────────────────────────────

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

function round4(n: number): number {
  return Math.round(n * 10000) / 10000
}
