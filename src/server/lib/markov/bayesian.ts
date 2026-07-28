/**
 * Markov Regime Detection — Bayesian Transition Estimation
 *
 * Replaces the MLE point-estimate transition matrix with a Dirichlet-Multinomial
 * Bayesian posterior. The Dirichlet is the conjugate prior for the multinomial,
 * so the posterior is closed-form — no MCMC, no sampling, no iteration.
 *
 * Mathematics:
 *   Prior on each row of the 3×3 matrix:  Dirichlet(α₁, α₂, α₃)
 *   After observing transition counts c = [c₁, c₂, c₃] from a given state:
 *     Posterior = Dirichlet(α₁ + c₁, α₂ + c₂, α₃ + c₃)
 *
 *   Posterior mean (the shrinkage estimator that replaces the MLE):
 *     E[pⱼ | c] = (αⱼ + cⱼ) / (α₀ + n)
 *   where α₀ = Σαₖ (prior concentration) and n = Σcₖ (observed transitions).
 *   With a flat prior [1,1,1]:  E[pⱼ] = (1 + cⱼ) / (3 + n)
 *     - n = 0  → 1/3 (collapses to the prior — no opinion)
 *     - n → ∞  → cⱼ/n (recovers the MLE)
 *
 * The payoff at the signal level:
 *   MLE signal :  signal = P̂(bull) - P̂(bear)         (point estimate, no uncertainty)
 *   Bayesian   :  P(signal > 0)                       (probability the direction is correct)
 *
 * Exact computation of P(signal > 0):
 *   For current state s, the posterior over (p_bull, p_sideways, p_bear) is
 *   Dirichlet(α'_b, α'_s, α'_r). By the Dirichlet aggregation / neutrality
 *   property, q = p_bull / (p_bull + p_bear) ~ Beta(α'_b, α'_r), independent
 *   of u = p_bull + p_bear. Since signal = p_bull - p_bear = u(2q - 1) and
 *   u > 0 a.s., P(signal > 0) = P(q > 1/2) = 1 - I_{1/2}(α'_b, α'_r).
 *   This is exact — evaluated via the regularized incomplete beta function.
 */

import type { TransitionMatrix } from "./matrix.js"
import type { MarketState } from "./state.js"

// Matrix indices: 0=bull, 1=sideways, 2=bear
const BULL = 0
const SIDEWAYS = 1
const BEAR = 2

// ── Public types ─────────────────────────────────────────────────────────────

export interface BayesianMatrixResult {
  /** Posterior-mean transition matrix (shrinkage estimate; replaces the MLE) */
  posteriorMean: TransitionMatrix
  /** Posterior variance per cell (3×3) — uncertainty of each probability) */
  posteriorVariance: number[][]
  /** Effective sample size per cell: αⱼ + cⱼ — how much data backs each cell */
  effectiveSampleSize: number[][]
  /** Total observed transitions per from-state (row sums of counts) */
  rowTotals: [number, number, number]
  /** Prior used (per cell, same for every row when passed as a flat vector) */
  priorAlphas: number[]
}

export interface BayesianSignal {
  /** E[P(bull) - P(bear)] — posterior-mean signal */
  signalMean: number
  /** P(signal > 0) — probability the direction is correct (EXACT, via Beta tail) */
  signalConfidence: number
  /** Var[P(bull) - P(bear)] — exact posterior variance of the signal */
  signalVariance: number
  /** 95% credible interval on the signal [lower, upper] (Gaussian approx) */
  credibleInterval: [number, number]
  /** Posterior alphas for the current-state row: [bull, sideways, bear] */
  posteriorAlphas: [number, number, number]
}

// ── Core: posterior mean & variance ──────────────────────────────────────────

/**
 * Compute the Bayesian posterior transition matrix from raw transition counts.
 *
 * Each row of `counts` is the transition counts FROM that state (index 0=bull,
 * 1=sideways, 2=bear) TO each target state. The Dirichlet prior is applied
 * per row; a flat prior [1,1,1] expresses no prior opinion and shrinks rows
 * with thin data toward uniform.
 *
 * @param counts - 3×3 transition counts (rows: from-state, cols: to-state)
 * @param priorAlphas - Dirichlet prior per cell (default: [1,1,1] = flat)
 */
export function bayesianTransitionMatrix(
  counts: number[][],
  priorAlphas: number[] = [1, 1, 1],
): BayesianMatrixResult {
  validateCounts(counts)
  const alpha = normalizePrior(priorAlphas)

  const posteriorMean = zeroMatrix()
  const posteriorVariance: number[][] = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ]
  const effectiveSampleSize: number[][] = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ]
  const rowTotals: [number, number, number] = [0, 0, 0]

  for (const fromIdx of [BULL, SIDEWAYS, BEAR]) {
    const row = counts[fromIdx]!
    const n = row.reduce((a, b) => a + b, 0)

    // Posterior parameters: α'_ⱼ = αⱼ + cⱼ ; α'₀ = α₀ + n
    const posteriorParams = alpha.map((a, j) => a + (row[j] ?? 0))
    const alpha0Post = posteriorParams.reduce((a, b) => a + b, 0)

    rowTotals[fromIdx] = n

    for (const toIdx of [BULL, SIDEWAYS, BEAR]) {
      const ap = posteriorParams[toIdx]!

      effectiveSampleSize[fromIdx]![toIdx] = ap

      // E[pⱼ] = α'_ⱼ / α'₀
      posteriorMean[fromIdx]![toIdx] = ap / alpha0Post

      // Var[pⱼ] = α'_ⱼ (α'₀ - α'_ⱼ) / (α'₀² (α'₀ + 1))
      posteriorVariance[fromIdx]![toIdx] =
        (ap * (alpha0Post - ap)) / (alpha0Post * alpha0Post * (alpha0Post + 1))
    }
  }

  return {
    posteriorMean: toTransitionMatrix(posteriorMean),
    posteriorVariance,
    effectiveSampleSize,
    rowTotals,
    priorAlphas: alpha,
  }
}

// ── Core: Bayesian signal with exact P(signal > 0) ───────────────────────────

/**
 * Compute a Bayesian regime signal for a given current state, including the
 * exact posterior probability that the signal direction is correct.
 *
 * signal = P(bull | current) - P(bear | current)
 *
 * @param counts - 3×3 transition counts (rows: from-state, cols: to-state)
 * @param currentState - the regime observed today
 * @param priorAlphas - Dirichlet prior per cell (default: [1,1,1] = flat)
 */
export function bayesianSignal(
  counts: number[][],
  currentState: MarketState,
  priorAlphas: number[] = [1, 1, 1],
): BayesianSignal {
  validateCounts(counts)
  const alpha = normalizePrior(priorAlphas)

  const fromIdx = stateToIndex(currentState)
  const row = counts[fromIdx]!

  const posteriorParams: [number, number, number] = [
    alpha[0]! + (row[0] ?? 0),
    alpha[1]! + (row[1] ?? 0),
    alpha[2]! + (row[2] ?? 0),
  ]
  const [aBull, aSide, aBear] = posteriorParams
  const alpha0Post = aBull + aSide + aBear

  // E[signal] = E[p_bull] - E[p_bear]
  const signalMean = aBull / alpha0Post - aBear / alpha0Post

  // Var[p_bull - p_bear] = Var[p_bull] + Var[p_bear] - 2·Cov(p_bull, p_bear)
  //   Var[pⱼ]      = α'_ⱼ (α'₀ - α'_ⱼ) / (α'₀² (α'₀ + 1))
  //   Cov(pⱼ, pₖ)  = -α'_ⱼ α'_ₖ / (α'₀² (α'₀ + 1))   (j ≠ k)
  // Combining:
  //   Var[signal] = [(α'_b + α'_r) α'₀ - (α'_b - α'_r)²] / (α'₀² (α'₀ + 1))
  const denom = alpha0Post * alpha0Post * (alpha0Post + 1)
  const signalVariance = ((aBull + aBear) * alpha0Post - (aBull - aBear) * (aBull - aBear)) / denom

  // P(signal > 0) = P(Beta(α'_b, α'_r) > 1/2)  — EXACT (Dirichlet neutrality)
  const signalConfidence = betaTailAboveHalf(aBull, aBear)

  // 95% credible interval on the signal via the exact mean/variance (Gaussian approx).
  // The headline P(signal>0) above is exact; this interval is an approximation
  // suitable for quick "how wide is our uncertainty" reads.
  const stdDev = Math.sqrt(Math.max(signalVariance, 0))
  const credibleInterval: [number, number] = [
    signalMean - 1.959963984540054 * stdDev,
    signalMean + 1.959963984540054 * stdDev,
  ]

  return {
    signalMean,
    signalConfidence,
    signalVariance,
    credibleInterval,
    posteriorAlphas: posteriorParams,
  }
}

/**
 * Build a 3×3 transition-counts matrix from a sequence of observed states.
 * The MLE matrix (`buildTransitionMatrix`) drops counts; the Bayesian layer
 * needs the raw counts to apply the Dirichlet prior.
 */
export function countsFromStates(states: MarketState[]): number[][] {
  if (states.length < 2) {
    throw new Error("Need at least 2 states to count transitions")
  }
  const counts: number[][] = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ]
  for (let i = 0; i < states.length - 1; i++) {
    counts[stateToIndex(states[i]!)]![stateToIndex(states[i + 1]!)]!++
  }
  return counts
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function stateToIndex(state: MarketState): number {
  switch (state) {
    case "bull":
      return BULL
    case "sideways":
      return SIDEWAYS
    case "bear":
      return BEAR
  }
}

function validateCounts(counts: number[][]): void {
  if (!Array.isArray(counts) || counts.length !== 3) {
    throw new Error("counts must be a 3×3 array")
  }
  for (const row of counts) {
    if (!Array.isArray(row) || row.length !== 3) {
      throw new Error("counts must be a 3×3 array")
    }
    if (row.some((c) => !Number.isFinite(c) || c < 0)) {
      throw new Error("transition counts must be non-negative finite numbers")
    }
  }
}

function normalizePrior(priorAlphas: number[]): number[] {
  if (priorAlphas.length !== 3) {
    throw new Error("priorAlphas must have length 3")
  }
  if (priorAlphas.some((a) => !Number.isFinite(a) || a <= 0)) {
    throw new Error("prior alphas must be positive finite numbers")
  }
  return [...priorAlphas]
}

function zeroMatrix(): number[][] {
  return [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ]
}

function toTransitionMatrix(m: number[][]): TransitionMatrix {
  return {
    bull_to_bull: m[BULL]![BULL]!,
    bull_to_sideways: m[BULL]![SIDEWAYS]!,
    bull_to_bear: m[BULL]![BEAR]!,
    sideways_to_bull: m[SIDEWAYS]![BULL]!,
    sideways_to_sideways: m[SIDEWAYS]![SIDEWAYS]!,
    sideways_to_bear: m[SIDEWAYS]![BEAR]!,
    bear_to_bull: m[BEAR]![BULL]!,
    bear_to_sideways: m[BEAR]![SIDEWAYS]!,
    bear_to_bear: m[BEAR]![BEAR]!,
  }
}

// ── Special functions: regularized incomplete beta ───────────────────────────
//
// P(signal > 0) reduces to P(Beta(a, b) > 1/2) = 1 - I_{1/2}(a, b).
// Implemented via the Numerical Recipes `betai` algorithm: Lentz's continued
// fraction for the incomplete beta function, with the symmetry flip when
// x > (a+1)/(a+b+2) for numerical stability. This is exactly what scipy's
// betainc computes — closed-form, no sampling.

/** Natural log of the Gamma function (Lanczos approximation, g=5). */
function lnGamma(xx: number): number {
  // Canonical Lanczos coefficients (Numerical Recipes g=5). Written in their
  // shortest round-tripping decimal form (same doubles as the published values).
  const COF = [
    76.18009172947146, -86.50532032941678, 24.01409824083091, -1.231739572450155,
    0.001208650973866179, -0.000005395239384953,
  ]
  // STIR = sqrt(2π) — computed exactly rather than as a rounded literal.
  const STIR = Math.sqrt(2 * Math.PI)
  // Mirror Numerical Recipes exactly: shift argument by 1, then the
  // Stirling-like correction tmp = (x+5.5) - (x+0.5)·ln(x+5.5).
  const x = xx - 1
  let tmp = x + 5.5
  tmp -= (x + 0.5) * Math.log(tmp)
  let ser = 1.000000000190015
  for (let j = 0; j < 6; j++) {
    ser += COF[j]! / (x + j + 1)
  }
  return -tmp + Math.log(STIR * ser)
}

const BETA_EPS = 3.0e-16
const BETA_FPMIN = 1.0e-300
const BETA_MAXIT = 300

/** Continued-fraction expansion for the incomplete beta (Lentz's method). */
function betaContinuedFraction(a: number, b: number, x: number): number {
  const qab = a + b
  const qap = a + 1
  const qam = a - 1
  let c = 1
  let d = 1 - (qab * x) / qap
  if (Math.abs(d) < BETA_FPMIN) d = BETA_FPMIN
  d = 1 / d
  let h = d

  for (let m = 1; m <= BETA_MAXIT; m++) {
    const m2 = 2 * m

    // Even step
    let aa = (m * (b - m) * x) / ((qam + m2) * (a + m2))
    d = 1 + aa * d
    if (Math.abs(d) < BETA_FPMIN) d = BETA_FPMIN
    c = 1 + aa / c
    if (Math.abs(c) < BETA_FPMIN) c = BETA_FPMIN
    d = 1 / d
    h *= d * c

    // Odd step
    aa = (-(a + m) * (qab + m) * x) / ((a + m2) * (qap + m2))
    d = 1 + aa * d
    if (Math.abs(d) < BETA_FPMIN) d = BETA_FPMIN
    c = 1 + aa / c
    if (Math.abs(c) < BETA_FPMIN) c = BETA_FPMIN
    d = 1 / d
    const delta = d * c
    h *= delta
    if (Math.abs(delta - 1) < BETA_EPS) break
  }
  return h
}

/** Regularized incomplete beta function I_x(a, b). */
export function regularizedIncompleteBeta(a: number, b: number, x: number): number {
  if (x < 0 || x > 1) throw new Error(`regularizedIncompleteBeta: x must be in [0,1], got ${x}`)
  if (x === 0 || x === 1) return x

  // Symmetry flip for numerical stability
  if (x < (a + 1) / (a + b + 2)) {
    const bt = Math.exp(
      lnGamma(a + b) - lnGamma(a) - lnGamma(b) + a * Math.log(x) + b * Math.log(1 - x),
    )
    return (bt * betaContinuedFraction(a, b, x)) / a
  }
  // Use symmetry: I_x(a,b) = 1 - I_{1-x}(b,a). NOTE: the bt prefactor is
  // identical in both branches (a·log(x) + b·log(1-x)); only the betacf args,
  // the divisor, and the complement differ.
  const bt = Math.exp(
    lnGamma(a + b) - lnGamma(a) - lnGamma(b) + a * Math.log(x) + b * Math.log(1 - x),
  )
  return 1 - (bt * betaContinuedFraction(b, a, 1 - x)) / b
}

/**
 * P(Beta(a, b) > 0.5) — exact tail probability. Equals 1 - I_{0.5}(a, b).
 * This is the core of the Bayesian signal confidence.
 */
function betaTailAboveHalf(a: number, b: number): number {
  return 1 - regularizedIncompleteBeta(a, b, 0.5)
}

// ── Tests ────────────────────────────────────────────────────────────────────

/**
 * Run Bayesian transition estimation unit tests.
 * Returns true if all pass.
 */
export function testBayesian(): boolean {
  let allPass = true
  const check = (name: string, cond: boolean) => {
    if (!cond) {
      console.error(`  ✗ ${name}`)
      allPass = false
    } else {
      console.log(`  ✓ ${name}`)
    }
  }
  const approx = (x: number, y: number, tol = 1e-9) => Math.abs(x - y) < tol

  console.log("\n=== Bayesian Transition Estimation Tests ===\n")

  // ── Posterior mean: flat prior, no data → uniform prior ──
  const empty = bayesianTransitionMatrix([
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ])
  check("Flat prior + no data: bull→bull = 1/3", approx(empty.posteriorMean.bull_to_bull, 1 / 3))
  check("Flat prior + no data: bear→bear = 1/3", approx(empty.posteriorMean.bear_to_bear, 1 / 3))
  check(
    "Flat prior + no data: sideways→bear = 1/3",
    approx(empty.posteriorMean.sideways_to_bear, 1 / 3),
  )

  // ── Posterior mean: recovers MLE at large N ──
  // 1000 transitions all bull→bull → mean ≈ 1.0 (shrunk slightly toward 1/3)
  const bigN = bayesianTransitionMatrix([
    [1000, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ])
  // posterior mean = (α + c)/α₀ = (1+1000)/(3+1000) = 1001/1003
  check(
    "Large N bull→bull ≈ MLE (1001/1003)",
    approx(bigN.posteriorMean.bull_to_bull, 1001 / 1003, 1e-6),
  )

  // ── Posterior mean: known closed-form with flat prior ──
  // counts bull = [80, 10, 10], flat prior → E[bull→bull] = 81/103
  const known = bayesianTransitionMatrix([
    [80, 10, 10],
    [10, 80, 10],
    [10, 10, 80],
  ])
  check("Known bull→bull = 81/103", approx(known.posteriorMean.bull_to_bull, 81 / 103))
  check("Known bull→bear = 11/103", approx(known.posteriorMean.bull_to_bear, 11 / 103))
  check(
    "Rows sum to 1.0 (bull row)",
    approx(
      known.posteriorMean.bull_to_bull +
        known.posteriorMean.bull_to_sideways +
        known.posteriorMean.bull_to_bear,
      1.0,
    ),
  )

  // ── Informative prior pulls thin rows toward the prior ──
  // Prior strongly believes bull persists: [20, 5, 5]. 0 observations.
  const informative = bayesianTransitionMatrix(
    [
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0],
    ],
    [20, 5, 5],
  )
  check(
    "Informative prior + no data: bull→bull = 20/30",
    approx(informative.posteriorMean.bull_to_bull, 20 / 30),
  )

  // ── countsFromStates round-trip ──
  const seq: MarketState[] = ["bull", "bull", "bear", "bull", "sideways"]
  const counts = countsFromStates(seq)
  check("countsFromStates: bull→bull = 1", counts[0]![0] === 1)
  check("countsFromStates: bull→bear = 1", counts[0]![2] === 1)
  check("countsFromStates: bear→bull = 1", counts[2]![0] === 1)
  check("countsFromStates: total transitions = 4", counts.flat().reduce((a, b) => a + b, 0) === 4)

  // ── Special functions: incomplete beta against known values ──
  // I_{0.5}(1,1) = 0.5 (uniform); I_{0.5}(a,b) symmetry: I_{0.5}(a,b) = 1 - I_{0.5}(b,a)
  check("I_{0.5}(1,1) = 0.5 (uniform)", approx(regularizedIncompleteBeta(1, 1, 0.5), 0.5))
  check(
    "Beta symmetry I_{0.5}(2,5) + I_{0.5}(5,2) = 1",
    approx(regularizedIncompleteBeta(2, 5, 0.5) + regularizedIncompleteBeta(5, 2, 0.5), 1.0, 1e-10),
  )
  // Symmetric params → tail = 0.5
  check("Beta(3,3) tail at 0.5 = 0.5 (symmetric)", approx(betaTailAboveHalf(3, 3), 0.5))

  // ── Signal confidence: flat prior + no data → 0.5 (coin flip) ──
  const sEmpty = bayesianSignal(
    [
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0],
    ],
    "bull",
  )
  check("Signal confidence starts at 0.5 (no data)", approx(sEmpty.signalConfidence, 0.5))
  check("Signal mean is 0 (no data)", approx(sEmpty.signalMean, 0))

  // ── Signal confidence: converges toward 1 as bull transitions dominate ──
  // From bull: 100 → bull, 0 → bear. P(signal>0) should be very high.
  const sBull = bayesianSignal(
    [
      [100, 0, 0],
      [0, 0, 0],
      [0, 0, 0],
    ],
    "bull",
  )
  check("Bull-dominant confidence > 0.99", sBull.signalConfidence > 0.99)
  // E[signal] = (101/103) - (1/103) = 100/103
  check("Bull-dominant signal mean ≈ 100/103", approx(sBull.signalMean, 100 / 103, 1e-6))

  // And toward 0 as bear transitions dominate
  const sBear = bayesianSignal(
    [
      [0, 0, 100],
      [0, 0, 0],
      [0, 0, 0],
    ],
    "bull",
  )
  check("Bear-dominant confidence < 0.01", sBear.signalConfidence < 0.01)
  // E[signal] = (1/103) - (101/103) = -100/103
  check("Bear-dominant signal mean ≈ -100/103", approx(sBear.signalMean, -(100 / 103), 1e-6))

  // ── Signal confidence: balanced counts → 0.5 ──
  const sBal = bayesianSignal(
    [
      [50, 0, 50],
      [0, 0, 0],
      [0, 0, 0],
    ],
    "bull",
  )
  check("Balanced bull/bear confidence ≈ 0.5", approx(sBal.signalConfidence, 0.5, 1e-9))
  check("Balanced signal mean ≈ 0", approx(sBal.signalMean, 0, 1e-9))

  // ── Credible interval: wider with less data, narrower with more ──
  const wideCI = bayesianSignal(
    [
      [2, 0, 2],
      [0, 0, 0],
      [0, 0, 0],
    ],
    "bull",
  )
  const narrowCI = bayesianSignal(
    [
      [2000, 0, 2000],
      [0, 0, 0],
      [0, 0, 0],
    ],
    "bull",
  )
  const width = (ci: [number, number]) => ci[1] - ci[0]
  check(
    "CI narrows with more data",
    width(narrowCI.credibleInterval) < width(wideCI.credibleInterval),
  )

  // ── Variance is non-negative everywhere ──
  const anyNeg = known.posteriorVariance.flat().some((v) => v < -1e-15)
  check("Posterior variance non-negative everywhere", !anyNeg)

  // ── Validation: bad inputs throw ──
  try {
    bayesianTransitionMatrix([
      [1, 2],
      [3, 4],
    ])
    check("Non-3×3 counts throws", false)
  } catch {
    check("Non-3×3 counts throws", true)
  }
  try {
    bayesianTransitionMatrix([[1, 1, 1]], [0, 1, 1])
    check("Zero/negative prior alpha throws", false)
  } catch {
    check("Zero/negative prior alpha throws", true)
  }

  console.log(
    `\n  Examples:  empty=${sEmpty.signalConfidence.toFixed(4)}  ` +
      `bull=${sBull.signalConfidence.toFixed(4)}  ` +
      `bear=${sBear.signalConfidence.toFixed(4)}`,
  )

  if (allPass) {
    console.log("\n✓ All Bayesian estimation tests passed\n")
  } else {
    console.log("\n✗ Some tests failed\n")
  }
  return allPass
}
