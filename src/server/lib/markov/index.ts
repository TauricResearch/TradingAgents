/**
 * Markov Regime Detection — Public API
 */

import {
  testWalkForward,
  type WalkForwardConfig,
  type WalkForwardResult,
  walkForwardBacktest,
} from "./backtest.js"
import {
  type BayesianMatrixResult,
  type BayesianSignal,
  bayesianSignal,
  bayesianTransitionMatrix,
  countsFromStates,
  testBayesian,
} from "./bayesian.js"
import {
  compareRegimes,
  fitHmm,
  fitHmmFromPrices,
  type HmmComparison,
  type HmmFitOptions,
  type HmmResult,
  hmmIndexToState,
  hmmMatrixToTransitionMatrix,
  hmmSignalFromResult,
  testHmm,
} from "./hmm.js"
import {
  buildTransitionMatrix,
  getNextStateProbabilities,
  getPersistence,
  nDayMatrix,
  nDayProbabilities,
  type TransitionMatrix,
  validateMatrix,
} from "./matrix.js"
import {
  type DailyState,
  getLatestRegimeMatrix,
  getLatestRegimeState,
  getRegimeStates,
  insertRegimeBacktest,
  insertRegimeHmmModel,
  insertRegimeMatrix,
  insertRegimeStates,
  updateRegimeData,
  upsertRegimeState,
} from "./regime-data.js"
import {
  buildNDaySignal,
  buildRegimeSignal,
  computeSignal,
  type NDaySignal,
  type RegimeSignal,
  signalToPositionSize,
} from "./signal.js"
import {
  classifyState,
  computeCumulativeReturns,
  generateStateStream,
  getCurrentState,
  type MarketState,
  type StateConfig,
} from "./state.js"
import {
  findStationaryDistribution,
  type StationaryDistribution,
  stationaryFromCounts,
  testStationary,
} from "./stationary.js"

// Re-export all public API
export {
  type BayesianMatrixResult,
  type BayesianSignal,
  bayesianSignal,
  bayesianTransitionMatrix,
  buildNDaySignal,
  buildRegimeSignal,
  buildTransitionMatrix,
  classifyState,
  compareRegimes,
  computeCumulativeReturns,
  computeSignal,
  countsFromStates,
  type DailyState,
  findStationaryDistribution,
  fitHmm,
  fitHmmFromPrices,
  generateStateStream,
  getCurrentState,
  getLatestRegimeMatrix,
  getLatestRegimeState,
  getNextStateProbabilities,
  getPersistence,
  getRegimeStates,
  type HmmComparison,
  type HmmFitOptions,
  type HmmResult,
  hmmIndexToState,
  hmmMatrixToTransitionMatrix,
  hmmSignalFromResult,
  insertRegimeBacktest,
  insertRegimeHmmModel,
  insertRegimeMatrix,
  insertRegimeStates,
  type MarketState,
  type NDaySignal,
  nDayMatrix,
  nDayProbabilities,
  type RegimeSignal,
  runAllTests,
  type StateConfig,
  type StationaryDistribution,
  signalToPositionSize,
  smokeTest,
  stationaryFromCounts,
  type TransitionMatrix,
  testBayesian,
  testHmm,
  testStationary,
  updateRegimeData,
  upsertRegimeState,
  validateMatrix,
  type WalkForwardConfig,
  type WalkForwardResult,
  walkForwardBacktest,
}

/**
 * Run unit tests for all pure-TypeScript modules (state, matrix, signal,
 * stationary, walk-forward, bayesian). Returns true iff every module passes.
 *
 * The HMM test (testHmm) is async and depends on the Python bridge + hmmlearn,
 * so it is NOT invoked here — run it separately via `testHmm()`.
 */
function runAllTests(): boolean {
  console.log("\n=== Markov Regime Detection Tests ===\n")

  let allPass = true

  // State tests
  const stateTests = [
    ["Bull: 20 days of 1% gains", classifyState(Array(20).fill(0.01)) === "bull"],
    ["Bear: 20 days of -1% losses", classifyState(Array(20).fill(-0.01)) === "bear"],
    [
      "Sideways: flat with noise",
      (() => {
        const returns = Array(20)
          .fill(0)
          .map(() => (Math.random() - 0.5) * 0.02)
        return classifyState(returns) === "sideways"
      })(),
    ],
    [
      "Bull threshold: exactly +5%",
      classifyState(Array(19).fill(0).concat([0.05]), { bullThreshold: 0.05 }) === "bull",
    ],
    [
      "Bear threshold: exactly -5%",
      classifyState(Array(19).fill(0).concat([-0.05]), { bearThreshold: -0.05 }) === "bear",
    ],
  ]
  for (const [name, passed] of stateTests) console.log(`  ${passed ? "✓" : "✗"} ${name}`)

  // Matrix tests
  const allBull = Array(100).fill("bull" as MarketState)
  const mAllBull = buildTransitionMatrix(allBull)
  const matrixTests = [
    ["All bull→bull = 1.0", Math.abs(mAllBull.bull_to_bull - 1.0) < 1e-10],
    ["Matrix rows sum to 1.0", validateMatrix(mAllBull)],
    [
      "N=0 identity matrix",
      (() => {
        const m0 = nDayMatrix(mAllBull, 0)
        return m0.bull_to_bull === 1 && m0.sideways_to_sideways === 1 && m0.bear_to_bear === 1
      })(),
    ],
    ["7-day matrix valid", validateMatrix(nDayMatrix(mAllBull, 7))],
  ]
  for (const [name, passed] of matrixTests) console.log(`  ${passed ? "✓" : "✗"} ${name}`)

  // Signal tests
  const mTest: TransitionMatrix = {
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
  const bullSignal = computeSignal(mTest, "bull")
  const bearSignal = computeSignal(mTest, "bear")
  const signalTests = [
    ["Bull signal = 0.70", Math.abs(bullSignal.signal - 0.7) < 1e-9],
    ["Bull direction = long", bullSignal.signalDirection === "long"],
    ["Bear signal negative", bearSignal.signal < 0],
    ["Signal range [-1, 1]", Math.abs(bullSignal.signal) <= 1],
  ]
  for (const [name, passed] of signalTests) console.log(`  ${passed ? "✓" : "✗"} ${name}`)

  if (!stateTests.every(([, p]) => p)) allPass = false
  if (!matrixTests.every(([, p]) => p)) allPass = false
  if (!signalTests.every(([, p]) => p)) allPass = false

  // Module-level test suites (each prints its own header and ✓/✗ lines)
  if (!testStationary()) allPass = false
  if (!testWalkForward()) allPass = false
  if (!testBayesian()) allPass = false

  if (allPass) {
    console.log("\n✓ All markov tests passed\n")
  } else {
    console.log("\n✗ Some markov tests failed\n")
  }
  return allPass
}

/**
 * Quick smoke test using synthetic data.
 */
function smokeTest(): void {
  // Synthetic 100-day price history
  const prices: number[] = [100]
  for (let i = 1; i < 100; i++) {
    const ret = (Math.random() - 0.48) * 0.04 // Slight bull bias
    prices.push(prices[i - 1]! * (1 + ret))
  }

  const dates: string[] = prices.map((_, i) => {
    const d = new Date("2026-01-01")
    d.setDate(d.getDate() + i)
    return d.toISOString().split("T")[0]!
  })

  console.log("\n=== Markov Smoke Test ===")
  console.log(`Prices: ${prices.length} bars`)

  // Classify states
  const states = generateStateStream("SMOKE", prices, dates)
  console.log(`States generated: ${states.length}`)

  const stateCounts = { bull: 0, bear: 0, sideways: 0 }
  for (const s of states) stateCounts[s.state]++
  console.log("State distribution:", stateCounts)

  // Build transition matrix
  const stateSequence = states.map((s) => s.state)
  const matrix = buildTransitionMatrix(stateSequence)
  console.log("Transition matrix:", matrix)

  // Persistence
  const pers = getPersistence(matrix)
  console.log("Persistence (stickiness):", pers)

  // Current signal
  const current = states[states.length - 1]!
  const signal = buildRegimeSignal("SMOKE", current.date, current.state, matrix)
  console.log(`Current state: ${current.state} (${current.date})`)
  console.log(`Signal: ${signal.signal.toFixed(4)} (${signal.signalDirection})`)
  console.log(`Signal magnitude: ${signal.signalMagnitude.toFixed(4)}`)

  // 2-day forecast
  const nDay = buildNDaySignal("SMOKE", current.date, current.state, matrix, 2)
  console.log(
    `2-day forecast: P(bull)=${nDay.forecastPbull.toFixed(4)}, P(bear)=${nDay.forecastPBear.toFixed(4)}`,
  )
  console.log(`2-day signal: ${nDay.forecastSignal.toFixed(4)}`)

  console.log("\n✓ Smoke test complete\n")
}
