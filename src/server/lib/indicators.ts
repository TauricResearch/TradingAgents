/**
 * Technical indicator library — pure TypeScript, no I/O, no side effects.
 *
 * All functions take arrays of OHLCV data and return computed values.
 * Designed to be imported by CLI commands, server routes, and test files.
 *
 * Naming convention:
 *   prices[n]  → closes (most indicators)
 *   highs[n]   → high prices  (ADX)
 *   lows[n]    → low prices   (ADX)
 *   volumes[n] → volume array (Volume confirmation)
 */

// ── SMA ─────────────────────────────────────────────────────────────────────

/**
 * Simple Moving Average.
 * @param prices  Array of close prices (newest last)
 * @param period  Number of periods
 */
export function sma(prices: number[], period: number): number {
  if (prices.length < period) return NaN
  const slice = prices.slice(-period)
  return slice.reduce((a, b) => a + b, 0) / period
}

// ── EMA ─────────────────────────────────────────────────────────────────────

/**
 * Exponential Moving Average.
 * @param prices  Array of close prices (newest last)
 * @param period  Number of periods (e.g. 12, 26)
 */
export function ema(prices: number[], period: number): number {
  if (prices.length < period) return NaN
  const k = 2 / (period + 1)
  // Seed with SMA of first `period` values
  let emaVal = sma(prices.slice(0, period), period)
  for (let i = period; i < prices.length; i++) {
    emaVal = prices[i]! * k + emaVal * (1 - k)
  }
  return emaVal
}

// ── Bollinger Bands ─────────────────────────────────────────────────────────

export interface BollingerBands {
  lower: number
  middle: number
  upper: number
}

/**
 * Bollinger Bands (20-period, 2 standard deviations by default).
 */
export function bollingerBands(
  prices: number[],
  period: number = 20,
  stdDev: number = 2,
): BollingerBands {
  if (prices.length < period) return { lower: NaN, middle: NaN, upper: NaN }
  const middle = sma(prices, period)
  const slice = prices.slice(-period)
  const variance = slice.reduce((sum, p) => sum + (p - middle) ** 2, 0) / period
  const sd = Math.sqrt(variance)
  return {
    lower: middle - stdDev * sd,
    middle,
    upper: middle + stdDev * sd,
  }
}

// ── RSI ─────────────────────────────────────────────────────────────────────

/**
 * Relative Strength Index (Wilder's smoothed RSI, 14-period by default).
 *
 * Algorithm:
 *   1. Compute price changes (delta = price[i] - price[i-1])
 *   2. Separate into gains (+) and losses (-)
 *   3. First average = simple mean over `period`
 *   4. Subsequent averages = Wilder smoothing: (prev_avg * (period-1) + current) / period
 *   5. RS = avg_gain / avg_loss
 *   6. RSI = 100 - (100 / (1 + RS))
 *
 * @param prices  Array of close prices (newest last)
 * @param period  Lookback period (default 14)
 */
export function rsi(prices: number[], period: number = 14): number {
  if (prices.length < period + 1) return NaN

  // Compute deltas
  const deltas: number[] = []
  for (let i = 1; i < prices.length; i++) {
    deltas.push(prices[i]! - prices[i - 1]!)
  }

  // Separate gains and losses
  let avgGain = 0
  let avgLoss = 0
  for (let i = 0; i < period; i++) {
    const d = deltas[i]!
    if (d > 0) avgGain += d
    else avgLoss -= d
  }
  avgGain /= period
  avgLoss /= period

  // Wilder smoothing for remaining bars
  for (let i = period; i < deltas.length; i++) {
    const d = deltas[i]!
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period
  }

  if (avgLoss === 0) return 100
  const rs = avgGain / avgLoss
  return 100 - 100 / (1 + rs)
}

// ── ADX ─────────────────────────────────────────────────────────────────────

export interface ADXResult {
  adx: number
  plusDI: number
  minusDI: number
}

/**
 * Average Directional Index (Wilder's method, 14-period by default).
 *
 * Components:
 *   True Range: max(H-L, |H-Pclose|, |L-Pclose|)
 *   +DM: max(H-Hprev, 0) if directional, else 0
 *   -DM: max(Lprev-L, 0) if directional, else 0
 *   Smoothed using Wilder: (prev * 13 + current) / 14
 *
 * @param highs   Array of high prices (newest last)
 * @param lows    Array of low prices (newest last)
 * @param closes  Array of close prices (newest last)
 * @param period  ADX period (default 14)
 */
export function adx(
  highs: number[],
  lows: number[],
  closes: number[],
  period: number = 14,
): ADXResult {
  const n = highs.length
  if (n < period + 1) return { adx: NaN, plusDI: NaN, minusDI: NaN }

  // Compute per-bar: tr, plusDM, minusDM
  const tr: number[] = []
  const plusDM: number[] = []
  const minusDM: number[] = []

  for (let i = 1; i < n; i++) {
    const h = highs[i]!
    const l = lows[i]!
    const pc = closes[i - 1]!
    const trVal = Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc))
    tr.push(trVal)

    const hDiff = h - highs[i - 1]!
    const lDiff = lows[i - 1]! - l

    let pDM = 0
    let mDM = 0
    if (hDiff > lDiff && hDiff > 0) pDM = hDiff
    if (lDiff > hDiff && lDiff > 0) mDM = lDiff

    plusDM.push(pDM)
    minusDM.push(mDM)
  }

  // Seed smoothed values with first-period simple averages
  let sumTR = 0
  let sumPlusDM = 0
  let sumMinusDM = 0
  for (let i = 0; i < period; i++) {
    sumTR += tr[i]!
    sumPlusDM += plusDM[i]!
    sumMinusDM += minusDM[i]!
  }
  let smoothTR = sumTR
  let smoothPlusDM = sumPlusDM
  let smoothMinusDM = sumMinusDM

  // Wilder smoothing loop
  const diVals: Array<{ plus: number; minus: number }> = []
  for (let i = period; i < tr.length; i++) {
    smoothTR = (smoothTR * (period - 1) + tr[i]!) / period
    smoothPlusDM = (smoothPlusDM * (period - 1) + plusDM[i]!) / period
    smoothMinusDM = (smoothMinusDM * (period - 1) + minusDM[i]!) / period

    const plusDI = smoothTR > 0 ? (smoothPlusDM / smoothTR) * 100 : 0
    const minusDI = smoothTR > 0 ? (smoothMinusDM / smoothTR) * 100 : 0
    diVals.push({ plus: plusDI, minus: minusDI })
  }

  if (diVals.length < period) return { adx: NaN, plusDI: NaN, minusDI: NaN }

  // Seed DX accumulator
  const dxVals: number[] = []
  for (let i = 0; i < period; i++) {
    const d = diVals[i]!
    const dx = d.plus + d.minus > 0 ? (Math.abs(d.plus - d.minus) / (d.plus + d.minus)) * 100 : 0
    dxVals.push(dx)
  }

  // Wilder smooth DX to get ADX
  let adxVal = dxVals.slice(0, period).reduce((a, b) => a + b, 0) / period
  for (let i = period; i < dxVals.length; i++) {
    adxVal = (adxVal * (period - 1) + dxVals[i]!) / period
  }

  // Current DI values
  const last = diVals[diVals.length - 1]!
  return { adx: adxVal, plusDI: last?.plus ?? NaN, minusDI: last?.minus ?? NaN }
}

// ── MACD ────────────────────────────────────────────────────────────────────

export interface MACDResult {
  macd: number // MACD line (12-EMA - 26-EMA)
  signal: number // Signal line (9-EMA of MACD)
  histogram: number // MACD - Signal
}

/**
 * MACD (12/26/9 by default).
 *
 * @param prices        Array of close prices (newest last)
 * @param fastPeriod    Fast EMA period (default 12)
 * @param slowPeriod    Slow EMA period (default 26)
 * @param signalPeriod  Signal EMA period (default 9)
 */
export function macd(
  prices: number[],
  fastPeriod: number = 12,
  slowPeriod: number = 26,
  signalPeriod: number = 9,
): MACDResult {
  if (prices.length < slowPeriod + signalPeriod) {
    return { macd: NaN, signal: NaN, histogram: NaN }
  }

  const fastEma = ema(prices, fastPeriod)
  const slowEma = ema(prices, slowPeriod)

  if (Number.isNaN(fastEma) || Number.isNaN(slowEma)) {
    return { macd: NaN, signal: NaN, histogram: NaN }
  }

  const macdLine = fastEma - slowEma

  // Compute signal line from MACD values (need at least signalPeriod MACD bars)
  // We compute MACD at each bar, then EMA over signalPeriod
  if (prices.length < slowPeriod + signalPeriod) {
    return { macd: macdLine, signal: NaN, histogram: NaN }
  }

  // Build MACD series: for each bar >= slowPeriod, compute 12-EMA - 26-EMA
  const macdSeries: number[] = []
  for (let i = slowPeriod; i < prices.length; i++) {
    const slice = prices.slice(0, i + 1)
    const f = ema(slice, fastPeriod)
    const s = ema(slice, slowPeriod)
    if (!Number.isNaN(f) && !Number.isNaN(s)) macdSeries.push(f - s)
  }

  if (macdSeries.length < signalPeriod) {
    return { macd: macdLine, signal: NaN, histogram: NaN }
  }

  const signalLine = ema(macdSeries, signalPeriod)
  return {
    macd: macdLine,
    signal: signalLine,
    histogram: Number.isNaN(signalLine) ? NaN : macdLine - signalLine,
  }
}

/**
 * MACD cross detection — compare current and previous bar to detect crosses.
 * Returns 'gold' (bullish cross), 'death' (bearish cross), or null.
 */
export type MACDCross = "gold" | "death" | null

export interface MACDCrossInput {
  macd: number
  signal: number
}

export function detectMacdCross(prev: MACDCrossInput, curr: MACDCrossInput): MACDCross {
  const prevBelow = prev.macd < prev.signal
  const currAbove = curr.macd > curr.signal
  const prevAbove = prev.macd > prev.signal
  const currBelow = curr.macd < curr.signal

  if (prevBelow && currAbove) return "gold"
  if (prevAbove && currBelow) return "death"
  return null
}

// ── Volume Confirmation ─────────────────────────────────────────────────────

export interface VolumeConfirmation {
  todayVolume: number
  avgVolume: number
  confirmed: boolean
  ratio: number // today / avg
}

/**
 * Volume confirmation — checks if today's volume exceeds the 20-day average.
 *
 * @param volumes   Array of volumes (newest last)
 * @param lookback  Period for average (default 20)
 */
export function volumeConfirmation(volumes: number[], lookback: number = 20): VolumeConfirmation {
  if (volumes.length < lookback + 1) {
    return { todayVolume: NaN, avgVolume: NaN, confirmed: false, ratio: NaN }
  }

  const todayVolume = volumes[volumes.length - 1]!
  const priorVolumes = volumes.slice(-lookback - 1, -1)
  const avgVolume = priorVolumes.reduce((a, b) => a + b, 0) / lookback
  const ratio = todayVolume / avgVolume
  return {
    todayVolume,
    avgVolume,
    confirmed: todayVolume > avgVolume,
    ratio,
  }
}

// ── Batch: compute all indicators for a ticker ──────────────────────────────

export interface OHLCVBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface IndicatorSnapshot {
  ticker: string
  date: string
  price: number
  rsi_14: number
  bb_lower: number
  bb_middle: number
  bb_upper: number
  ma_20: number
  ma_150: number
  adx_14: number
  adx_plus_di: number
  adx_minus_di: number
  macd_line: number
  macd_signal: number
  macd_histogram: number
  volume: number
  volume_20avg: number
  volume_confirmed: boolean
}

/**
 * Compute all indicators for a single ticker from OHLCV data.
 * Returns null if insufficient data (< 150 bars for MA150).
 */
export function computeSnapshot(ticker: string, bars: OHLCVBar[]): IndicatorSnapshot | null {
  if (bars.length < 150) return null

  const closes = bars.map((b) => b.close)
  const highs = bars.map((b) => b.high)
  const lows = bars.map((b) => b.low)
  const volumes = bars.map((b) => b.volume)

  const lastBar = bars[bars.length - 1]!
  const bb = bollingerBands(closes, 20, 2)
  const macdRes = macd(closes)
  const volConf = volumeConfirmation(volumes, 20)
  const adxRes = adx(highs, lows, closes, 14)

  return {
    ticker,
    date: lastBar.date,
    price: lastBar.close,
    rsi_14: rsi(closes, 14),
    bb_lower: bb.lower,
    bb_middle: bb.middle,
    bb_upper: bb.upper,
    ma_20: sma(closes, 20),
    ma_150: sma(closes, 150),
    adx_14: adxRes.adx,
    adx_plus_di: adxRes.plusDI,
    adx_minus_di: adxRes.minusDI,
    macd_line: macdRes.macd,
    macd_signal: macdRes.signal,
    macd_histogram: macdRes.histogram,
    volume: volConf.todayVolume,
    volume_20avg: volConf.avgVolume,
    volume_confirmed: volConf.confirmed,
  }
}

// ── Scan Gate Evaluator ─────────────────────────────────────────────────────

export interface GateResult {
  name: string
  pass: boolean
  value: number | null
  threshold: string
  relaxed: boolean
}

export interface ScanResult {
  ticker: string
  date: string
  price: number
  gates: GateResult[]
  gatesPassed: number
  gatesTotal: number
  ma150Passed: boolean
  signal: "buy" | "no_buy" | "sell"
  exitTriggers: string[]
  snapshot: IndicatorSnapshot | null
}

/**
 * Gate definitions — each gate can be independently relaxed.
 */
export type GateName = "rsi" | "bollinger" | "ma20" | "adx" | "macd" | "volume"

/** All gates — order must match the brief */
export const GATE_DEFINITIONS: Array<{
  name: GateName
  label: string
  description: string
  evaluate: (snap: IndicatorSnapshot) => boolean
  getValue: (snap: IndicatorSnapshot) => number | null
}> = [
  {
    name: "rsi",
    label: "RSI < 30",
    description: "Oversold bounce",
    evaluate: (s) => !Number.isNaN(s.rsi_14) && s.rsi_14 < 30,
    getValue: (s) => s.rsi_14,
  },
  {
    name: "bollinger",
    label: "Price ≤ Bollinger lower",
    description: "At support level",
    evaluate: (s) => !Number.isNaN(s.bb_lower) && s.price <= s.bb_lower,
    getValue: (s) => s.bb_lower,
  },
  {
    name: "ma20",
    label: "Price > MA20",
    description: "Short-term uptrend",
    evaluate: (s) => !Number.isNaN(s.ma_20) && s.price > s.ma_20,
    getValue: (s) => s.ma_20,
  },
  {
    name: "adx",
    label: "ADX > 20",
    description: "Trending, not ranging",
    evaluate: (s) => !Number.isNaN(s.adx_14) && s.adx_14 > 20,
    getValue: (s) => s.adx_14,
  },
  {
    name: "macd",
    label: "MACD histogram > 0",
    description: "Momentum shift",
    evaluate: (s) => !Number.isNaN(s.macd_histogram) && s.macd_histogram > 0,
    getValue: (s) => s.macd_histogram,
  },
  {
    name: "volume",
    label: "Volume confirmed",
    description: "Real interest",
    evaluate: (s) => s.volume_confirmed,
    getValue: (s) => s.volume,
  },
]

/**
 * Evaluate scan gates and exit triggers against an indicator snapshot.
 *
 * @param ticker  Ticker symbol
 * @param snapshot  Indicator snapshot (from computeSnapshot)
 * @param relaxedGates  Set of gate names to relax (skip evaluation, treat as pass)
 */
export function evaluateScan(
  ticker: string,
  snapshot: IndicatorSnapshot,
  relaxedGates: Set<GateName> = new Set(),
): ScanResult {
  const gates: GateResult[] = []

  for (const def of GATE_DEFINITIONS) {
    if (relaxedGates.has(def.name)) {
      gates.push({
        name: def.name,
        pass: true,
        value: def.getValue(snapshot),
        threshold: def.label,
        relaxed: true,
      })
    } else {
      gates.push({
        name: def.name,
        pass: def.evaluate(snapshot),
        value: def.getValue(snapshot),
        threshold: def.label,
        relaxed: false,
      })
    }
  }

  const gatesPassed = gates.filter((g) => g.pass).length
  const gatesTotal = gates.length

  // MA150 filter (always enforced)
  const ma150Passed = !Number.isNaN(snapshot.ma_150) && snapshot.price > snapshot.ma_150

  // Determine signal
  let signal: ScanResult["signal"] = "no_buy"
  if (gatesPassed === gatesTotal && ma150Passed) {
    signal = "buy"
  }

  // Exit triggers (any one fires = sell)
  const exitTriggers: string[] = []
  if (!Number.isNaN(snapshot.rsi_14) && snapshot.rsi_14 > 70) {
    exitTriggers.push(`RSI overbought (${snapshot.rsi_14.toFixed(1)})`)
  }
  if (!Number.isNaN(snapshot.bb_upper) && snapshot.price >= snapshot.bb_upper) {
    exitTriggers.push(`Upper Bollinger hit (${snapshot.bb_upper.toFixed(2)})`)
  }
  if (
    !Number.isNaN(snapshot.macd_line) &&
    !Number.isNaN(snapshot.macd_signal) &&
    snapshot.macd_histogram < 0 &&
    snapshot.macd_line < snapshot.macd_signal
  ) {
    exitTriggers.push("MACD death cross")
  }

  if (exitTriggers.length > 0) {
    signal = "sell"
  }

  return {
    ticker,
    date: snapshot.date,
    price: snapshot.price,
    gates,
    gatesPassed,
    gatesTotal,
    ma150Passed,
    signal,
    exitTriggers,
    snapshot,
  }
}
