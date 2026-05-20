/**
 * Markov Regime Detection — Signal Generation
 *
 * Computes regime signals from transition matrices.
 * Signal = P(bull | today) - P(bear | today)
 */

import type { TransitionMatrix } from "./matrix.js"
import { getNextStateProbabilities, nDayProbabilities } from "./matrix.js"
import type { MarketState } from "./state.js"

export interface RegimeSignal {
  ticker: string
  date: string
  currentState: MarketState
  pBull: number
  pBear: number
  pSideways: number
  signal: number // pBull - pBear, range [-1, 1]
  signalDirection: "long" | "short" | "neutral"
  signalMagnitude: number // absolute signal value, for position sizing
}

export interface NDaySignal extends RegimeSignal {
  forecastDays: number
  forecastPbull: number
  forecastPBear: number
  forecastPSideways: number
  forecastSignal: number
}

/**
 * Compute the trading signal for a given matrix and current state.
 * Signal = P(bull | current) - P(bear | current)
 */
export function computeSignal(
  m: TransitionMatrix,
  currentState: MarketState,
): {
  pBull: number
  pBear: number
  pSideways: number
  signal: number
  signalDirection: "long" | "short" | "neutral"
} {
  const [pBull, pSideways, pBear] = getNextStateProbabilities(m, currentState)
  const signal = pBull - pBear

  let signalDirection: "long" | "short" | "neutral"
  if (signal > 0.01) {
    signalDirection = "long"
  } else if (signal < -0.01) {
    signalDirection = "short"
  } else {
    signalDirection = "neutral"
  }

  return {
    pBull,
    pBear,
    pSideways,
    signal,
    signalDirection,
  }
}

/**
 * Build a full RegimeSignal for a ticker on a given date.
 */
export function buildRegimeSignal(
  ticker: string,
  date: string,
  currentState: MarketState,
  matrix: TransitionMatrix,
): RegimeSignal {
  const { pBull, pBear, pSideways, signal, signalDirection } = computeSignal(matrix, currentState)

  return {
    ticker,
    date,
    currentState,
    pBull,
    pBear,
    pSideways,
    signal,
    signalDirection,
    signalMagnitude: Math.abs(signal),
  }
}

/**
 * Build an N-day forecast signal.
 */
export function buildNDaySignal(
  ticker: string,
  date: string,
  currentState: MarketState,
  matrix: TransitionMatrix,
  nDays: number,
): NDaySignal {
  const forecast = nDayProbabilities(matrix, currentState, nDays)

  return {
    ...buildRegimeSignal(ticker, date, currentState, matrix),
    forecastDays: nDays,
    forecastPbull: forecast.bull,
    forecastPBear: forecast.bear,
    forecastPSideways: forecast.sideways,
    forecastSignal: forecast.bull - forecast.bear,
  }
}

/**
 * Get position size recommendation from signal magnitude.
 * Simple linear scaling: signal magnitude → position percentage.
 *
 * @param signal - signal magnitude (0-1)
 * @param maxPosition - maximum position size as decimal (default: 1.0 = 100%)
 * @returns position size as decimal
 */
export function signalToPositionSize(signal: number, maxPosition: number = 1.0): number {
  // Clamp signal to [0, 1]
  const clamped = Math.min(1, Math.max(0, Math.abs(signal)))
  return clamped * maxPosition
}

// Tests are inline in markov/index.ts — no console usage in production
