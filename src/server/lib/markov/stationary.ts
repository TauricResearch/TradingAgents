/**
 * Markov Regime Detection — Stationary Distribution
 *
 * Solves π = πP for the long-run equilibrium distribution of a 3-state Markov chain.
 *
 * Mathematics:
 *   The stationary distribution π satisfies πP = π, i.e., (P^T - I)π = 0.
 *   This is underdetermined — we replace one row with the sum constraint Σπᵢ = 1
 *   and solve the resulting 3×3 linear system.
 *
 *   Augmented system:
 *     [P^T - I with last row replaced by [1,1,1]] × π = [0, 0, 1]^T
 */

import { lusolve, type Matrix, matrix } from "mathjs"
import { type TransitionMatrix, toMathjsMatrix } from "./matrix.js"

export interface StationaryDistribution {
  bull: number // long-run proportion of bull days
  sideways: number // long-run proportion of sideways days
  bear: number // long-run proportion of bear days
}

/**
 * Compute the stationary distribution of a 3-state Markov transition matrix.
 *
 * Solves (P^T - I)π = 0 with Σπᵢ = 1 via LU decomposition.
 *
 * @param m - 3×3 transition probability matrix (rows sum to 1.0)
 * @returns StationaryDistribution with long-run proportions
 *
 * Edge cases:
 *   - Singular matrix (reducible chain) → uniform [1/3, 1/3, 1/3]
 *   - Invalid result (e.g. NaNs from pathological matrix) → uniform fallback
 *   - Result is normalized to sum to 1.0
 */
export function findStationaryDistribution(m: TransitionMatrix): StationaryDistribution {
  const P = toMathjsMatrix(m) // 3×3
  const I = matrix([
    // 3×3 identity
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ])

  // Build augmented matrix: P^T - I, then replace last row
  const Pt = transpose3(P)
  const A_raw = subtractMatrices(Pt, I) // actually returns Matrix through type

  // Build augmented matrix as plain array for lusolve input
  const A: number[][] = [
    [A_raw.get([0, 0]), A_raw.get([0, 1]), A_raw.get([0, 2])],
    [A_raw.get([1, 0]), A_raw.get([1, 1]), A_raw.get([1, 2])],
    [1, 1, 1], // Σπᵢ = 1 constraint replaces last row
  ]

  const b = [0, 0, 1]

  try {
    const x = lusolve(matrix(A), matrix(b)) as Matrix
    const raw = [x.get([0, 0]) as number, x.get([1, 0]) as number, x.get([2, 0]) as number]

    // Check for NaN or non-finite results
    if (raw.some((v) => !isFinite(v))) {
      return { bull: 1 / 3, sideways: 1 / 3, bear: 1 / 3 }
    }

    // Normalise to sum exactly 1.0 (handles floating-point drift)
    const total = raw.reduce((a, b) => a + b, 0)
    if (total <= 0) {
      return { bull: 1 / 3, sideways: 1 / 3, bear: 1 / 3 }
    }

    return {
      bull: raw[0]! / total,
      sideways: raw[1]! / total,
      bear: raw[2]! / total,
    }
  } catch {
    // Singular or unsolvable → uniform fallback
    return { bull: 1 / 3, sideways: 1 / 3, bear: 1 / 3 }
  }
}

/**
 * Compute stationary distribution from a raw counts matrix (before normalising).
 * Useful when you want to work with raw transition counts.
 *
 * @param counts - 3×3 transition counts matrix (rows: from-state, cols: to-state)
 * @returns StationaryDistribution
 *
 * Note: if any row sums to zero (no transitions observed from that state),
 * the matrix is padded to uniform [1,1,1] / 3 for that row before solving.
 */
export function stationaryFromCounts(counts: [number, number, number][]): StationaryDistribution {
  // Convert counts to probabilities, padding empty rows
  const probs = counts.map((row) => {
    const sum = row.reduce((a, b) => a + b, 0)
    if (sum === 0) return [1 / 3, 1 / 3, 1 / 3] as const
    return row.map((c) => c / sum) as [number, number, number]
  })

  return findStationaryDistribution({
    bull_to_bull: probs[0]![0]!,
    bull_to_sideways: probs[0]![1]!,
    bull_to_bear: probs[0]![2]!,
    sideways_to_bull: probs[1]![0]!,
    sideways_to_sideways: probs[1]![1]!,
    sideways_to_bear: probs[1]![2]!,
    bear_to_bull: probs[2]![0]!,
    bear_to_sideways: probs[2]![1]!,
    bear_to_bear: probs[2]![2]!,
  })
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Transpose a 3×3 mathjs matrix, returning a mutable MathjsMatrix. */
function transpose3(P: Matrix): Matrix {
  return matrix([
    [P.get([0, 0]), P.get([1, 0]), P.get([2, 0])],
    [P.get([0, 1]), P.get([1, 1]), P.get([2, 1])],
    [P.get([0, 2]), P.get([1, 2]), P.get([2, 2])],
  ])
}

/** Subtract two 3×3 matrices (A - B), returning a mutable MathjsMatrix. */
function subtractMatrices(A: Matrix, B: Matrix): Matrix {
  return matrix([
    [
      (A.get([0, 0]) as number) - (B.get([0, 0]) as number),
      (A.get([0, 1]) as number) - (B.get([0, 1]) as number),
      (A.get([0, 2]) as number) - (B.get([0, 2]) as number),
    ],
    [
      (A.get([1, 0]) as number) - (B.get([1, 0]) as number),
      (A.get([1, 1]) as number) - (B.get([1, 1]) as number),
      (A.get([1, 2]) as number) - (B.get([1, 2]) as number),
    ],
    [
      (A.get([2, 0]) as number) - (B.get([2, 0]) as number),
      (A.get([2, 1]) as number) - (B.get([2, 1]) as number),
      (A.get([2, 2]) as number) - (B.get([2, 2]) as number),
    ],
  ])
}

// ── Tests ────────────────────────────────────────────────────────────────────

/**
 * Run stationary distribution unit tests.
 * Returns true if all pass.
 */
export function testStationary(): boolean {
  let allPass = true
  const check = (name: string, cond: boolean) => {
    if (!cond) {
      console.error(`  ✗ ${name}`)
      allPass = false
    } else console.log(`  ✓ ${name}`)
  }

  console.log("\n=== Stationary Distribution Tests ===\n")

  // Test 1: All-bull chain — should converge to [1, 0, 0]
  const allBull: TransitionMatrix = {
    bull_to_bull: 1,
    bull_to_sideways: 0,
    bull_to_bear: 0,
    sideways_to_bull: 1,
    sideways_to_sideways: 0,
    sideways_to_bear: 0,
    bear_to_bull: 1,
    bear_to_sideways: 0,
    bear_to_bear: 0,
  }
  const d1 = findStationaryDistribution(allBull)
  check("All-bull converges to bull=1.0", Math.abs(d1.bull - 1.0) < 1e-10)
  check("All-bull sideways=0", Math.abs(d1.sideways - 0.0) < 1e-10)
  check("All-bull bear=0", Math.abs(d1.bear - 0.0) < 1e-10)
  check("All-bull sums to 1.0", Math.abs(d1.bull + d1.sideways + d1.bear - 1.0) < 1e-10)

  // Test 2: Symmetric matrix — should converge to uniform [1/3, 1/3, 1/3]
  const symmetric: TransitionMatrix = {
    bull_to_bull: 0.5,
    bull_to_sideways: 0.25,
    bull_to_bear: 0.25,
    sideways_to_bull: 0.25,
    sideways_to_sideways: 0.5,
    sideways_to_bear: 0.25,
    bear_to_bull: 0.25,
    bear_to_sideways: 0.25,
    bear_to_bear: 0.5,
  }
  const d2 = findStationaryDistribution(symmetric)
  check("Symmetric bull ≈ 1/3", Math.abs(d2.bull - 1 / 3) < 1e-6)
  check("Symmetric sideways ≈ 1/3", Math.abs(d2.sideways - 1 / 3) < 1e-6)
  check("Symmetric bear ≈ 1/3", Math.abs(d2.bear - 1 / 3) < 1e-6)
  check("Symmetric sums to 1.0", Math.abs(d2.bull + d2.sideways + d2.bear - 1.0) < 1e-10)

  // Test 3: Known matrix from Phase 1 tests
  // bull_to_bull=0.8, bull_to_bear=0.1 → bull dominates
  const known: TransitionMatrix = {
    bull_to_bull: 0.8,
    bull_to_sideways: 0.1,
    bull_to_bear: 0.1,
    sideways_to_bull: 0.2,
    sideways_to_sideways: 0.6,
    sideways_to_bear: 0.2,
    bear_to_bull: 0.1,
    bear_to_sideways: 0.2,
    bear_to_bear: 0.7,
  }
  const d3 = findStationaryDistribution(known)
  check("Known: bull > bear (assertion)", d3.bull > d3.bear)
  check("Known: bull > sideways", d3.bull > d3.sideways)
  check("Known: bull is largest (0.421)", d3.bull > d3.bear && d3.bull > d3.sideways)
  check("Known sums to 1.0", Math.abs(d3.bull + d3.sideways + d3.bear - 1.0) < 1e-10)
  console.log(
    `  Known stationary: bull=${d3.bull.toFixed(4)} sideways=${d3.sideways.toFixed(4)} bear=${d3.bear.toFixed(4)}`,
  )

  // Test 4: stationaryFromCounts with valid counts
  const counts: [number, number, number][] = [
    [80, 10, 10], // bull → mostly bull
    [20, 60, 20], // sideways → mostly sideways
    [10, 20, 70], // bear → mostly bear
  ]
  const d4 = stationaryFromCounts(counts)
  check("Counts: bull > bear", d4.bull > d4.bear)
  check("Counts sums to 1.0", Math.abs(d4.bull + d4.sideways + d4.bear - 1.0) < 1e-10)

  // Test 5: stationaryFromCounts with zero row → uniform fallback
  const zeroRow: [number, number, number][] = [
    [80, 10, 10],
    [0, 0, 0], // no transitions from sideways
    [10, 20, 70],
  ]
  const d5 = stationaryFromCounts(zeroRow)
  check("Zero-row: returns valid distribution", isFinite(d5.bull + d5.sideways + d5.bear))
  check("Zero-row sums to 1.0", Math.abs(d5.bull + d5.sideways + d5.bear - 1.0) < 1e-10)

  // Test 6: Verify stationary distribution satisfies πP = π (eigenvalue check)
  const residual = (v: StationaryDistribution, m: TransitionMatrix) => {
    const newBull =
      v.bull * m.bull_to_bull + v.sideways * m.sideways_to_bull + v.bear * m.bear_to_bull
    const newSideways =
      v.bull * m.bull_to_sideways +
      v.sideways * m.sideways_to_sideways +
      v.bear * m.bear_to_sideways
    const newBear =
      v.bull * m.bull_to_bear + v.sideways * m.sideways_to_bear + v.bear * m.bear_to_bear
    return Math.max(
      Math.abs(newBull - v.bull),
      Math.abs(newSideways - v.sideways),
      Math.abs(newBear - v.bear),
    )
  }
  const r3 = residual(d3, known)
  const r2 = residual(d2, symmetric)
  check(`Known residual < 1e-10 (${r3.toExponential(2)})`, r3 < 1e-10)
  check(`Symmetric residual < 1e-10 (${r2.toExponential(2)})`, r2 < 1e-10)

  if (allPass) {
    console.log("\n✓ All stationary distribution tests passed\n")
  } else {
    console.log("\n✗ Some tests failed\n")
  }
  return allPass
}
