/**
 * Markov Regime Detection — Hidden Markov Model
 *
 * TypeScript wrapper for a Gaussian HMM fit in Python via the existing
 * subprocess bridge (scripts/py/markov_hmm.py, hmmlearn). The article is
 * explicit: reimplementing Baum-Welch + Viterbi in TypeScript is a research
 * project — the pragmatic path is hmmlearn behind a JSON-lines bridge, exactly
 * like scripts/py/analyze_stream.py.
 *
 * Why HMM over observable states: in an HMM the true regime is a *hidden*
 * state. What we observe are returns. Each hidden state generates returns from
 * its own distribution. The model learns both the regime transitions AND the
 * return distributions simultaneously — without hand-labeled thresholds.
 *
 * State labelling: after fitting, states are sorted by mean return so
 *   0 = bull (highest mean), 1 = sideways, 2 = bear (lowest)
 * This matches the observable engine's indexing (bull/sideways/bear = 0/1/2),
 * so HMM and observable regimes can be compared directly.
 *
 * Multi-start fitting (≥5 random seeds, keep max log-likelihood) is handled in
 * the Python layer — Baum-Welch converges to local maxima, so a single init
 * frequently produces suboptimal regime assignments.
 */

import { projectRoot, runPythonStdinJson } from "../subprocess.js"
import { buildTransitionMatrix, type TransitionMatrix } from "./matrix.js"
import { buildRegimeSignal, type RegimeSignal } from "./signal.js"
import { generateStateStream, type MarketState } from "./state.js"

// Indices: 0=bull, 1=sideways, 2=bear (matches state.ts / matrix.ts convention)
const BULL = 0
const SIDEWAYS = 1
const BEAR = 2

const HMM_SCRIPT = "scripts/py/markov_hmm.py"

// ── Types ────────────────────────────────────────────────────────────────────

export interface HmmResult {
  ticker: string
  /** Learned 3×3 transition matrix (rows: from-state, indexed bull/side/bear) */
  transitionMatrix: number[][]
  /** Mean daily return per regime [bull, sideways, bear] */
  stateMeans: number[]
  /** Daily-return volatility per regime [bull, sideways, bear] */
  stateVols: number[]
  /** Hidden state per return-day, 0=bull / 1=sideways / 2=bear */
  labeledStates: number[]
  /** Model fit quality (higher = better). Use to compare multi-start runs. */
  logLikelihood: number
  /** Whether Baum-Welch reported convergence */
  converged: boolean
}

export interface HmmFitOptions {
  /** Number of hidden states (default: 3 = bull/sideways/bear) */
  nStates?: number
  /** Max Baum-Welch iterations per start (default: 1000) */
  nIter?: number
  /** Number of random initializations; best log-likelihood kept (default: 5) */
  nStarts?: number
}

export interface HmmComparison {
  ticker: string
  /** Observable (threshold-labelled) regimes from the Phase 1 engine */
  observable: {
    distribution: { bull: number; sideways: number; bear: number }
    matrix: TransitionMatrix
    stateCount: number
  }
  /** Data-driven HMM regimes */
  hmm: HmmResult
  /**
   * Fraction of overlapping days where the HMM's labelled state matches the
   * observable engine's label. A low score is NOT a failure — the HMM and the
   * ±5% threshold see different things by design. (Article: "if regimes are
   * unclear, that's a finding not a bug".)
   */
  agreementPct: number
  /** Number of overlapping days the agreement was computed over */
  comparedDays: number
}

// ── Bridge helpers ───────────────────────────────────────────────────────────

/** Python bridge response shape (snake_case, before mapping to HmmResult). */
interface HmmBridgeResponse {
  ticker?: string
  transition_matrix?: number[][]
  state_means?: number[]
  state_vols?: number[]
  labeled_states?: number[]
  log_likelihood?: number
  converged?: boolean
  error?: string
}

/** Map the bridge's snake_case response to our HmmResult, or null on error. */
function mapBridgeResponse(ticker: string, r: HmmBridgeResponse | null): HmmResult | null {
  if (!r || r.error) return null
  if (
    !r.transition_matrix ||
    !r.state_means ||
    !r.state_vols ||
    !r.labeled_states ||
    r.log_likelihood == null
  ) {
    return null
  }
  return {
    ticker: r.ticker ?? ticker,
    transitionMatrix: r.transition_matrix,
    stateMeans: r.state_means,
    stateVols: r.state_vols,
    labeledStates: r.labeled_states,
    logLikelihood: r.log_likelihood,
    converged: r.converged ?? false,
  }
}

// ── Core: fit HMM from returns ───────────────────────────────────────────────

/**
 * Fit a Gaussian HMM to a series of daily returns via the Python bridge.
 *
 * @param ticker - symbol (for labelling only)
 * @param returns - daily returns as decimals (e.g. 0.01 = 1%)
 * @param opts - fitting options
 * @returns HmmResult, or null if the bridge / hmmlearn is unavailable
 */
export async function fitHmm(
  ticker: string,
  returns: number[],
  opts: HmmFitOptions = {},
): Promise<HmmResult | null> {
  const { nStates = 3, nIter = 1000, nStarts = 5 } = opts

  if (returns.length < nStates + 1) {
    throw new Error(`Insufficient returns for HMM: need ≥${nStates + 1}, got ${returns.length}`)
  }

  const scriptPath = `${projectRoot()}/${HMM_SCRIPT}`
  const response = await runPythonStdinJson<HmmBridgeResponse>(
    scriptPath,
    { ticker, returns, n_states: nStates, n_iter: nIter, n_starts: nStarts },
    { timeout: 60_000 },
  )

  return mapBridgeResponse(ticker, response)
}

/**
 * Fit an HMM from a price series. Computes daily returns, fits the model, and
 * attaches the date each hidden-state label corresponds to.
 *
 * returns[k] = (prices[k+1] - prices[k]) / prices[k], so labeledStates[k]
 * corresponds to date dates[k+1].
 */
export async function fitHmmFromPrices(
  ticker: string,
  prices: number[],
  dates: string[],
  opts: HmmFitOptions = {},
): Promise<{ result: HmmResult; labelDates: string[] } | null> {
  if (prices.length !== dates.length) {
    throw new Error(`Price/date length mismatch: ${prices.length} vs ${dates.length}`)
  }
  if (prices.length < 2) {
    throw new Error(`Insufficient prices for HMM: need ≥2, got ${prices.length}`)
  }

  const returns: number[] = []
  for (let i = 1; i < prices.length; i++) {
    returns.push((prices[i]! - prices[i - 1]!) / prices[i - 1]!)
  }

  const result = await fitHmm(ticker, returns, opts)
  if (!result) return null

  // labeledStates[k] aligns with returns[k] → date dates[k+1]
  const labelDates = dates.slice(1)
  return { result, labelDates }
}

// ── Derived signals ──────────────────────────────────────────────────────────

/** Convert an HMM state index (0/1/2) to a MarketState. */
export function hmmIndexToState(idx: number): MarketState {
  switch (idx) {
    case BULL:
      return "bull"
    case SIDEWAYS:
      return "sideways"
    case BEAR:
      return "bear"
    default:
      throw new Error(`Invalid HMM state index: ${idx}`)
  }
}

/** Convert the HMM's learned 3×3 array into the engine's TransitionMatrix. */
export function hmmMatrixToTransitionMatrix(m: number[][]): TransitionMatrix {
  if (m.length !== 3 || m.some((row) => row.length !== 3)) {
    throw new Error("HMM transition matrix must be 3×3")
  }
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

/**
 * Build a RegimeSignal from the HMM's learned transition matrix and the current
 * (most recent) hidden state. Lets the HMM drive the same signal machinery as
 * the observable engine.
 */
export function hmmSignalFromResult(
  ticker: string,
  result: HmmResult,
  currentDate: string,
): RegimeSignal {
  const matrix = hmmMatrixToTransitionMatrix(result.transitionMatrix)
  const currentState = hmmIndexToState(result.labeledStates[result.labeledStates.length - 1]!)
  return buildRegimeSignal(ticker, currentDate, currentState, matrix)
}

/**
 * Compare data-driven HMM regimes against the observable (threshold-labelled)
 * regimes over the same price history.
 */
export async function compareRegimes(
  ticker: string,
  prices: number[],
  dates: string[],
  opts: HmmFitOptions = {},
): Promise<HmmComparison | null> {
  const fit = await fitHmmFromPrices(ticker, prices, dates, opts)
  if (!fit) return null
  const { result: hmm, labelDates } = fit

  // Observable regimes (Phase 1 engine)
  const observableStream = generateStateStream(ticker, prices, dates)
  const observableByDate = new Map<string, MarketState>()
  for (const s of observableStream) observableByDate.set(s.date, s.state)

  const obsCounts = { bull: 0, sideways: 0, bear: 0 }
  for (const s of observableStream) obsCounts[s.state]++
  const obsTotal = observableStream.length

  // HMM regimes keyed by date
  const hmmByDate = new Map<string, MarketState>()
  for (let k = 0; k < hmm.labeledStates.length; k++) {
    hmmByDate.set(labelDates[k]!, hmmIndexToState(hmm.labeledStates[k]!))
  }

  // Agreement over the date intersection
  let agree = 0
  let compared = 0
  for (const [date, obsState] of observableByDate) {
    const hmmState = hmmByDate.get(date)
    if (hmmState === undefined) continue
    compared++
    if (hmmState === obsState) agree++
  }

  return {
    ticker,
    observable: {
      distribution:
        obsTotal > 0
          ? {
              bull: obsCounts.bull / obsTotal,
              sideways: obsCounts.sideways / obsTotal,
              bear: obsCounts.bear / obsTotal,
            }
          : { bull: 0, sideways: 0, bear: 0 },
      matrix: buildTransitionMatrix(observableStream.map((s) => s.state)),
      stateCount: obsTotal,
    },
    hmm,
    agreementPct: compared > 0 ? agree / compared : 0,
    comparedDays: compared,
  }
}

// ── Tests ────────────────────────────────────────────────────────────────────

/**
 * Run HMM unit tests against synthetic data via the Python bridge.
 * Returns true if all pass. Skips (returns true) if hmmlearn is unavailable —
 * the HMM layer is optional infrastructure.
 */
export async function testHmm(): Promise<boolean> {
  console.log("\n=== Hidden Markov Model Tests ===\n")

  // Synthetic price series with clear regime structure: bull run → crash → recovery.
  // Returns are drawn from three distinct distributions so a 3-state HMM should
  // separate them cleanly.
  const prices: number[] = [100]
  const regimes: ("bull" | "crash" | "calm")[] = []
  const seeded = mulberry32(42)
  for (let i = 1; i < 900; i++) {
    const phase = i < 300 ? "bull" : i < 500 ? "crash" : "calm"
    regimes.push(phase)
    let shock: number
    if (phase === "bull")
      shock = 0.004 + seeded() * 0.012 // +0.4% to +1.6%/day
    else if (phase === "crash")
      shock = -0.012 - seeded() * 0.02 // -1.2% to -3.2%/day
    else shock = (seeded() - 0.5) * 0.006 // ±0.3% calm
    prices.push(prices[i - 1]! * (1 + shock))
  }
  const dates: string[] = prices.map((_, i) => {
    const d = new Date("2022-01-01")
    d.setDate(d.getDate() + i)
    return d.toISOString().split("T")[0]!
  })

  let allPass = true
  const check = (name: string, cond: boolean) => {
    if (!cond) {
      console.error(`  ✗ ${name}`)
      allPass = false
    } else {
      console.log(`  ✓ ${name}`)
    }
  }
  const approx = (x: number, y: number, tol: number) => Math.abs(x - y) < tol

  // ── Bridge availability ──
  const fit = await fitHmmFromPrices("TEST", prices, dates)
  if (!fit) {
    console.log("  ⚠ HMM bridge unavailable (hmmlearn not installed?) — skipping")
    console.log("\n✓ HMM tests skipped (optional dependency)\n")
    return true
  }
  const { result } = fit

  check("Fit produced a result", result != null)
  check("3 hidden states", result.stateMeans.length === 3)
  check("Transition matrix is 3×3", result.transitionMatrix.length === 3)
  check(
    "Transition matrix rows are 3-wide",
    result.transitionMatrix.every((r) => r.length === 3),
  )
  check(
    "Labelled states align with returns (len = prices - 1)",
    result.labeledStates.length === prices.length - 1,
  )

  // ── State labelling: sorted by mean (bull highest, bear lowest) ──
  check(
    "State means sorted descending (bull > sideways > bear)",
    result.stateMeans[BULL]! > result.stateMeans[SIDEWAYS]! &&
      result.stateMeans[SIDEWAYS]! > result.stateMeans[BEAR]!,
  )
  check("Bull mean positive", result.stateMeans[BULL]! > 0)
  check("Bear mean negative", result.stateMeans[BEAR]! < 0)

  // ── Stylized fact: bear volatility > bull volatility ──
  check("Bear vol > bull vol (stylized fact)", result.stateVols[BEAR]! > result.stateVols[BULL]!)

  // ── Transition matrix rows sum to 1 ──
  const rowSums = result.transitionMatrix.map((row) => row.reduce((a, b) => a + b, 0))
  check(
    "Transition rows sum to 1.0",
    rowSums.every((s) => approx(s, 1.0, 1e-6)),
  )

  // ── Log-likelihood is finite (multi-start picked a real model) ──
  check("Log-likelihood is finite", Number.isFinite(result.logLikelihood))

  console.log(
    `\n  HMM summary:  means=[${result.stateMeans.map((m) => m.toFixed(4)).join(", ")}]  ` +
      `vols=[${result.stateVols.map((v) => v.toFixed(4)).join(", ")}]  ` +
      `logL=${result.logLikelihood.toFixed(2)}  converged=${result.converged}`,
  )

  // ── compareRegimes round-trip ──
  const cmp = await compareRegimes("TEST", prices, dates)
  check("compareRegimes returns a result", cmp != null)
  if (cmp) {
    check("Comparison agreement in [0,1]", cmp.agreementPct >= 0 && cmp.agreementPct <= 1)
    check("Comparison covers most days", cmp.comparedDays > prices.length * 0.7)
    check(
      "Observable matrix valid (rows sum to 1)",
      approx(
        cmp.observable.matrix.bull_to_bull +
          cmp.observable.matrix.bull_to_sideways +
          cmp.observable.matrix.bull_to_bear,
        1.0,
        1e-9,
      ),
    )
    console.log(
      `  Comparison:  agreement=${(cmp.agreementPct * 100).toFixed(1)}% over ${cmp.comparedDays} days  ` +
        `(obs bull/side/bear = ${(cmp.observable.distribution.bull * 100).toFixed(0)}/${(cmp.observable.distribution.sideways * 100).toFixed(0)}/${(cmp.observable.distribution.bear * 100).toFixed(0)}%)`,
    )
  }

  // ── Index mapping sanity ──
  check("hmmIndexToState(0)=bull", hmmIndexToState(0) === "bull")
  check("hmmIndexToState(2)=bear", hmmIndexToState(2) === "bear")
  const tm = hmmMatrixToTransitionMatrix(result.transitionMatrix)
  check(
    "hmmMatrixToTransitionMatrix maps [0][0]→bull_to_bull",
    tm.bull_to_bull === result.transitionMatrix[0]![0]!,
  )

  if (allPass) {
    console.log("\n✓ All HMM tests passed\n")
  } else {
    console.log("\n✗ Some tests failed\n")
  }
  return allPass
}

/** Small deterministic PRNG (mulberry32) for reproducible synthetic test data. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
