/**
 * Markov Regime Detection — Transition Matrix
 *
 * Builds and operates on 3x3 state transition matrices.
 * Uses mathjs for matrix exponentiation (N-day forecasts).
 */

import { matrix, pow } from 'mathjs';
import type { MarketState } from './state.js';

// Matrix indices: 0=bull, 1=sideways, 2=bear
const BULL_IDX = 0;
const SIDEWAYS_IDX = 1;
const BEAR_IDX = 2;

export interface TransitionMatrix {
  bull_to_bull: number;
  bull_to_sideways: number;
  bull_to_bear: number;
  sideways_to_bull: number;
  sideways_to_sideways: number;
  sideways_to_bear: number;
  bear_to_bull: number;
  bear_to_sideways: number;
  bear_to_bear: number;
}

type RawMatrix = number[][];

function stateToIndex(state: MarketState): number {
  switch (state) {
    case 'bull': return BULL_IDX;
    case 'sideways': return SIDEWAYS_IDX;
    case 'bear': return BEAR_IDX;
  }
}

/**
 * Build transition probability matrix from a sequence of states.
 * Counts transitions and normalizes each row to sum to 1.0.
 */
export function buildTransitionMatrix(states: MarketState[]): TransitionMatrix {
  if (states.length < 2) {
    throw new Error('Need at least 2 states to build transition matrix');
  }

  // Count transitions
  const counts: RawMatrix = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ];

  for (let i = 0; i < states.length - 1; i++) {
    const fromIdx = stateToIndex(states[i]!);
    const toIdx = stateToIndex(states[i + 1]!);
    counts[fromIdx]![toIdx]!++;
  }

  // Normalize rows to probabilities
  const probs: RawMatrix = counts.map(row => {
    const total = row.reduce((a, b) => a + b, 0);
    if (total === 0) {
      return [1/3, 1/3, 1/3];
    }
    return row.map(c => c / total);
  });

  return {
    bull_to_bull: probs[BULL_IDX]![BULL_IDX]!,
    bull_to_sideways: probs[BULL_IDX]![SIDEWAYS_IDX]!,
    bull_to_bear: probs[BULL_IDX]![BEAR_IDX]!,
    sideways_to_bull: probs[SIDEWAYS_IDX]![BULL_IDX]!,
    sideways_to_sideways: probs[SIDEWAYS_IDX]![SIDEWAYS_IDX]!,
    sideways_to_bear: probs[SIDEWAYS_IDX]![BEAR_IDX]!,
    bear_to_bull: probs[BEAR_IDX]![BULL_IDX]!,
    bear_to_sideways: probs[BEAR_IDX]![SIDEWAYS_IDX]!,
    bear_to_bear: probs[BEAR_IDX]![BEAR_IDX]!,
  };
}

/**
 * Convert TransitionMatrix to mathjs matrix for operations.
 */
export function toMathjsMatrix(m: TransitionMatrix) {
  return matrix([
    [m.bull_to_bull, m.bull_to_sideways, m.bull_to_bear],
    [m.sideways_to_bull, m.sideways_to_sideways, m.sideways_to_bear],
    [m.bear_to_bull, m.bear_to_sideways, m.bear_to_bear],
  ]);
}

/**
 * Convert mathjs matrix back to TransitionMatrix.
 */
export function fromMathjsMatrix(mat: ReturnType<typeof matrix>): TransitionMatrix {
  const arr = mat.toArray() as number[][];
  return {
    bull_to_bull: arr[0]![0]!,
    bull_to_sideways: arr[0]![1]!,
    bull_to_bear: arr[0]![2]!,
    sideways_to_bull: arr[1]![0]!,
    sideways_to_sideways: arr[1]![1]!,
    sideways_to_bear: arr[1]![2]!,
    bear_to_bull: arr[2]![0]!,
    bear_to_sideways: arr[2]![1]!,
    bear_to_bear: arr[2]![2]!,
  };
}

/**
 * Verify that a matrix is valid (each row sums to 1.0).
 */
export function validateMatrix(m: TransitionMatrix): boolean {
  const rows = [
    [m.bull_to_bull, m.bull_to_sideways, m.bull_to_bear],
    [m.sideways_to_bull, m.sideways_to_sideways, m.sideways_to_bear],
    [m.bear_to_bull, m.bear_to_sideways, m.bear_to_bear],
  ];

  return rows.every(row => {
    const sum = row.reduce((a, b) => a + b, 0);
    return Math.abs(sum - 1.0) < 1e-10;
  });
}

/**
 * Compute N-day transition matrix: P^n.
 */
export function nDayMatrix(m: TransitionMatrix, n: number): TransitionMatrix {
  if (n < 0) throw new Error('n must be non-negative');
  if (n === 0) {
    return {
      bull_to_bull: 1, bull_to_sideways: 0, bull_to_bear: 0,
      sideways_to_bull: 0, sideways_to_sideways: 1, sideways_to_bear: 0,
      bear_to_bull: 0, bear_to_sideways: 0, bear_to_bear: 1,
    };
  }

  const mat = toMathjsMatrix(m);
  const powered = pow(mat, n) as ReturnType<typeof matrix>;
  return fromMathjsMatrix(powered);
}

/**
 * Get probability of each next state given current state.
 * Returns [P(bull), P(sideways), P(bear)].
 */
export function getNextStateProbabilities(m: TransitionMatrix, currentState: MarketState): [number, number, number] {
  const mat = toMathjsMatrix(m);
  const stateIdx = stateToIndex(currentState);
  const arr = mat.toArray() as number[][];
  const row = arr[stateIdx]!;
  return [row[0]!, row[1]!, row[2]!];
}

/**
 * Compute N-day probabilities for each target state starting from a given state.
 */
export function nDayProbabilities(
  m: TransitionMatrix,
  fromState: MarketState,
  n: number,
): { bull: number; sideways: number; bear: number } {
  const nMat = nDayMatrix(m, n);
  const probs = getNextStateProbabilities(nMat, fromState);
  return { bull: probs[0], sideways: probs[1], bear: probs[2] };
}

/**
 * Get the persistence diagonal values.
 * High values mean the state is "sticky" (bull markets stay bull, etc.)
 */
export function getPersistence(m: TransitionMatrix): { bull: number; sideways: number; bear: number } {
  return {
    bull: m.bull_to_bull,
    sideways: m.sideways_to_sideways,
    bear: m.bear_to_bear,
  };
}