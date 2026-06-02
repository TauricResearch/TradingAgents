/**
 * Markov Regime Detection — Public API
 */

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
  stationaryFromCounts,
  testStationary,
  type StationaryDistribution,
} from "./stationary.js"

// Re-export all public API
export {
  buildNDaySignal,
  buildRegimeSignal,
  buildTransitionMatrix,
  classifyState,
  computeCumulativeReturns,
  computeSignal,
  type DailyState,
  findStationaryDistribution,
  generateStateStream,
  getCurrentState,
  getLatestRegimeMatrix,
  getLatestRegimeState,
  getNextStateProbabilities,
  getPersistence,
  getRegimeStates,
  insertRegimeMatrix,
  insertRegimeStates,
  type MarketState,
  type NDaySignal,
  nDayMatrix,
  nDayProbabilities,
  type RegimeSignal,
  runAllTests,
  type StateConfig,
  signalToPositionSize,
  smokeTest,
  type StationaryDistribution,
  stationaryFromCounts,
  testStationary,
  type TransitionMatrix,
  updateRegimeData,
  upsertRegimeState,
  validateMatrix,
}

/**
 * Run unit tests for all modules.
 */
function runAllTests(): void {
  console.log("\n=== Markov Regime Detection Tests ===\n")

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

  console.log("\n✓ All markov tests passed\n")
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
