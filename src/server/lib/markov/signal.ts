/**
 * Markov Regime Detection — Signal Generation
 *
 * Computes regime signals from transition matrices.
 * Signal = P(bull | today) - P(bear | today)
 */

import type { MarketState } from './state.js';
import type { TransitionMatrix } from './matrix.js';
import { getNextStateProbabilities } from './matrix.js';

export interface RegimeSignal {
  ticker: string;
  date: string;
  currentState: MarketState;
  pBull: number;
  pBear: number;
  pSideways: number;
  signal: number;             // pBull - pBear, range [-1, 1]
  signalDirection: 'long' | 'short' | 'neutral';
  signalMagnitude: number;    // absolute signal value, for position sizing
}

export interface NDaySignal extends RegimeSignal {
  forecastDays: number;
  forecastPbull: number;
  forecastPBear: number;
  forecastPSideways: number;
  forecastSignal: number;
}

/**
 * Compute the trading signal for a given matrix and current state.
 * Signal = P(bull | current) - P(bear | current)
 */
export function computeSignal(m: TransitionMatrix, currentState: MarketState): {
  pBull: number;
  pBear: number;
  pSideways: number;
  signal: number;
  signalDirection: 'long' | 'short' | 'neutral';
} {
  const [pBull, pSideways, pBear] = getNextStateProbabilities(m, currentState);
  const signal = pBull - pBear;

  let signalDirection: 'long' | 'short' | 'neutral';
  if (signal > 0.01) {
    signalDirection = 'long';
  } else if (signal < -0.01) {
    signalDirection = 'short';
  } else {
    signalDirection = 'neutral';
  }

  return {
    pBull,
    pBear,
    pSideways,
    signal,
    signalDirection,
  };
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
  const { pBull, pBear, pSideways, signal, signalDirection } = computeSignal(matrix, currentState);

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
  };
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
  // Import here to avoid circular deps
  const { nDayProbabilities } = require('./matrix.js');

  const forecast = nDayProbabilities(matrix, currentState, nDays);
  const signal = computeSignal(matrix, currentState);

  return {
    ...buildRegimeSignal(ticker, date, currentState, matrix),
    forecastDays: nDays,
    forecastPbull: forecast.bull,
    forecastPBear: forecast.bear,
    forecastPSideways: forecast.sideways,
    forecastSignal: forecast.bull - forecast.bear,
  };
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
  const clamped = Math.min(1, Math.max(0, Math.abs(signal)));
  return clamped * maxPosition;
}

// --- Tests ---

export function runTests(): void {
  // Test 1: Strong bull signal
  const m1: TransitionMatrix = {
    bull_to_bull: 0.80,
    bull_to_sideways: 0.10,
    bull_to_bear: 0.10,
    sideways_to_bull: 0.20,
    sideways_to_sideways: 0.60,
    sideways_to_bear: 0.20,
    bear_to_bull: 0.10,
    bear_to_sideways: 0.20,
    bear_to_bear: 0.70,
  };

  const s1 = computeSignal(m1, 'bull');
  console.assert(s1.signal === 0.70, `Bull signal failed: got ${s1.signal}`);
  console.assert(s1.signalDirection === 'long', 'Bull direction failed');
  console.assert(s1.pBull === 0.80, 'P(bull) failed');
  console.assert(s1.pBear === 0.10, 'P(bear) failed');

  // Test 2: Strong bear signal
  const s2 = computeSignal(m1, 'bear');
  console.assert(s2.signal === -0.60, `Bear signal failed: got ${s2.signal}`);
  console.assert(s2.signalDirection === 'short', 'Bear direction failed');

  // Test 3: Neutral signal (equal probabilities)
  const mNeutral: TransitionMatrix = {
    bull_to_bull: 0.33,
    bull_to_sideways: 0.34,
    bull_to_bear: 0.33,
    sideways_to_bull: 0.33,
    sideways_to_sideways: 0.34,
    sideways_to_bear: 0.33,
    bear_to_bull: 0.33,
    bear_to_sideways: 0.34,
    bear_to_bear: 0.33,
  };

  const s3 = computeSignal(mNeutral, 'bull');
  console.assert(Math.abs(s3.signal) < 0.01, `Neutral signal failed: got ${s3.signal}`);
  console.assert(s3.signalDirection === 'neutral', 'Neutral direction failed');

  // Test 4: Signal range [-1, 1]
  const extremes: TransitionMatrix = {
    bull_to_bull: 1.0, bull_to_sideways: 0, bull_to_bear: 0,
    sideways_to_bull: 0, sideways_to_sideways: 1.0, sideways_to_bear: 0,
    bear_to_bull: 0, bear_to_sideways: 0, bear_to_bear: 1.0,
  };

  const s4a = computeSignal(extremes, 'bull');
  console.assert(s4a.signal === 1.0, 'Max bull signal failed');
  const s4b = computeSignal(extremes, 'bear');
  console.assert(s4b.signal === -1.0, 'Max bear signal failed');

  // Test 5: buildRegimeSignal
  const reg = buildRegimeSignal('AAPL', '2026-05-20', 'bull', m1);
  console.assert(reg.ticker === 'AAPL', 'RegimeSignal ticker failed');
  console.assert(reg.signal === 0.70, 'RegimeSignal signal failed');
  console.assert(reg.signalMagnitude === 0.70, 'RegimeSignal magnitude failed');

  // Test 6: signalToPositionSize
  console.assert(signalToPositionSize(0.5) === 0.5, 'Position size 0.5 failed');
  console.assert(signalToPositionSize(1.0) === 1.0, 'Position size 1.0 failed');
  console.assert(signalToPositionSize(0.0) === 0.0, 'Position size 0 failed');
  console.assert(signalToPositionSize(0.7, 0.5) === 0.35, 'Position size cap failed');

  console.log('✓ signal.ts tests passed');
}