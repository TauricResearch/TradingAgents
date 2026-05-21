import { expect, test } from "bun:test"
import {
  adx,
  bollingerBands,
  computeSnapshot,
  detectMacdCross,
  ema,
  evaluateScan,
  GATE_DEFINITIONS,
  macd,
  rsi,
  sma,
  volumeConfirmation,
} from "./indicators.ts"

// ── SMA ─────────────────────────────────────────────────────────────────────

test("sma: computes correct mean", () => {
  expect(sma([10, 20, 30, 40, 50], 5)).toBe(30)
  expect(sma([10, 20, 30, 40, 50, 60], 5)).toBe(40) // uses last 5
})

test("sma: returns NaN when insufficient data", () => {
  expect(sma([10, 20], 5)).toBe(NaN)
})

test("sma: handles single-element period", () => {
  expect(sma([42], 1)).toBe(42)
})

// ── EMA ─────────────────────────────────────────────────────────────────────

test("ema: converges toward price in trending series", () => {
  // Rising prices should push EMA up
  const rising = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
  const e10 = ema(rising, 10)
  expect(e10).toBeGreaterThan(100)
  expect(e10).toBeLessThan(109)
})

test("ema: returns NaN when insufficient data", () => {
  expect(ema([100], 12)).toBe(NaN)
  expect(ema([100, 101, 102], 12)).toBe(NaN)
})

// ── Bollinger Bands ─────────────────────────────────────────────────────────

test("bollingerBands: middle band equals 20-period SMA", () => {
  const prices = Array.from({ length: 25 }, (_, i) => 100 + i)
  const bb = bollingerBands(prices)
  expect(bb.middle).toBeCloseTo(sma(prices, 20), 2)
})

test("bollingerBands: upper > middle > lower", () => {
  const prices = Array.from({ length: 30 }, (_, i) => 100 + Math.sin(i / 3) * 10 + i * 0.5)
  const bb = bollingerBands(prices)
  expect(bb.upper).toBeGreaterThan(bb.middle)
  expect(bb.middle).toBeGreaterThan(bb.lower)
})

test("bollingerBands: default is 20-period, 2 std dev", () => {
  const prices = Array.from({ length: 25 }, () => 100)
  const bb = bollingerBands(prices)
  // Flat series: sd = 0, so upper = lower = middle = 100
  expect(bb.upper).toBe(100)
  expect(bb.lower).toBe(100)
})

test("bollingerBands: returns NaN with insufficient data", () => {
  const bb = bollingerBands([100, 101, 102])
  expect(bb.upper).toBe(NaN)
})

// ── RSI ─────────────────────────────────────────────────────────────────────

test("rsi: returns 100 when all bars are up", () => {
  // 15 bars of consecutive up moves
  const prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115]
  expect(rsi(prices, 14)).toBe(100)
})

test("rsi: returns 0 when all bars are down", () => {
  const prices = [115, 114, 113, 112, 111, 110, 109, 108, 107, 106, 105, 104, 103, 102, 101, 100]
  expect(rsi(prices, 14)).toBe(0)
})

test("rsi: returns NaN with insufficient data", () => {
  const short = Array.from({ length: 10 }, (_, i) => 100 + i)
  expect(rsi(short, 14)).toBe(NaN)
})

test("rsi: 14-period RSI on flat series returns 50", () => {
  // Flat prices with small noise — RSI should be near 50
  const flat = Array.from({ length: 20 }, (_, i) => 100 + (i % 2 === 0 ? 0.1 : -0.1))
  const result = rsi(flat, 14)
  expect(result).toBeGreaterThan(40)
  expect(result).toBeLessThan(60)
})

test("rsi: oversold threshold (30) fires on sharp drop", () => {
  // Flat then sharp drop — RSI should go below 30
  const prices: number[] = []
  for (let i = 0; i < 14; i++) prices.push(100)
  // Drop 15 points over 5 bars
  for (let i = 0; i < 5; i++) prices.push(100 - (i + 1) * 3)
  const result = rsi(prices, 14)
  expect(result).toBeLessThan(30)
})

// ── ADX ─────────────────────────────────────────────────────────────────────

test("adx: trending series has higher ADX than ranging", () => {
  // Strong uptrend — 40 bars to ensure ADX smoothing has enough data
  const trendingHighs: number[] = []
  const trendingLows: number[] = []
  const trendingCloses: number[] = []
  let price = 100
  for (let i = 0; i < 40; i++) {
    price += 0.5
    trendingHighs.push(price + 0.5)
    trendingLows.push(price - 0.5)
    trendingCloses.push(price)
  }
  const trendAdx = adx(trendingHighs, trendingLows, trendingCloses, 14)
  expect(trendAdx.adx).not.toBe(NaN)
  expect(trendAdx.adx).toBeGreaterThan(15) // strong trend

  // Ranging / flat
  const rangingHighs: number[] = []
  const rangingLows: number[] = []
  const rangingCloses: number[] = []
  for (let i = 0; i < 40; i++) {
    rangingHighs.push(100 + Math.sin(i) * 2)
    rangingLows.push(100 + Math.sin(i) * 2 - 0.5)
    rangingCloses.push(100 + Math.sin(i) * 2)
  }
  const rangeAdx = adx(rangingHighs, rangingLows, rangingCloses, 14)
  expect(trendAdx.adx).toBeGreaterThan(rangeAdx.adx)
})

test("adx: returns NaN with insufficient data", () => {
  const h = [100, 101, 102, 103, 104, 105]
  const l = [99, 100, 101, 102, 103, 104]
  const c = [99.5, 100.5, 101.5, 102.5, 103.5, 104.5]
  expect(adx(h, l, c, 14).adx).toBe(NaN)
})

test("adx: plusDI and minusDI are positive in uptrend", () => {
  // Need 40+ bars for ADX to compute
  const h: number[] = []
  const l: number[] = []
  const c: number[] = []
  let price = 100
  for (let i = 0; i < 40; i++) {
    price += 0.3
    h.push(price + 0.2)
    l.push(price - 0.2)
    c.push(price)
  }
  const res = adx(h, l, c, 14)
  expect(res.plusDI).not.toBe(NaN)
  expect(res.plusDI).toBeGreaterThan(0)
  expect(res.minusDI).toBeGreaterThanOrEqual(0)
})

// ── MACD ────────────────────────────────────────────────────────────────────

test("macd: macd line positive in uptrend", () => {
  const rising = Array.from({ length: 40 }, (_, i) => 100 + i)
  const res = macd(rising)
  expect(res.macd).toBeGreaterThan(0)
})

test("macd: macd line negative in downtrend", () => {
  const falling = Array.from({ length: 40 }, (_, i) => 140 - i)
  const res = macd(falling)
  expect(res.macd).toBeLessThan(0)
})

test("macd: returns NaN with insufficient data", () => {
  const short = Array.from({ length: 20 }, (_, i) => 100 + i)
  const res = macd(short)
  expect(res.macd).toBe(NaN)
  expect(res.signal).toBe(NaN)
})

test("macd: histogram = macd - signal", () => {
  const prices = Array.from({ length: 50 }, (_, i) => 100 + Math.sin(i / 5) * 5 + i * 0.2)
  const res = macd(prices)
  if (!Number.isNaN(res.signal)) {
    expect(res.histogram).toBeCloseTo(res.macd - res.signal, 2)
  }
})

// ── MACD Cross Detection ────────────────────────────────────────────────────

test("detectMacdCross: gold cross (bullish)", () => {
  const prev = { macd: 1.0, signal: 2.0 } // macd below signal
  const curr = { macd: 2.5, signal: 2.0 } // macd crosses above signal
  expect(detectMacdCross(prev, curr)).toBe("gold")
})

test("detectMacdCross: death cross (bearish)", () => {
  const prev = { macd: 3.0, signal: 2.0 } // macd above signal
  const curr = { macd: 1.5, signal: 2.0 } // macd crosses below signal
  expect(detectMacdCross(prev, curr)).toBe("death")
})

test("detectMacdCross: no cross", () => {
  const prev = { macd: 2.0, signal: 2.0 }
  const curr = { macd: 2.2, signal: 2.1 }
  expect(detectMacdCross(prev, curr)).toBeNull()
})

// ── Volume Confirmation ─────────────────────────────────────────────────────

test("volumeConfirmation: confirms when today > avg", () => {
  // Normal volume, then spike
  const volumes: number[] = []
  for (let i = 0; i < 20; i++) volumes.push(1_000_000) // avg = 1M
  volumes.push(2_000_000) // spike
  const res = volumeConfirmation(volumes, 20)
  expect(res.todayVolume).toBe(2_000_000)
  expect(res.avgVolume).toBe(1_000_000)
  expect(res.confirmed).toBe(true)
  expect(res.ratio).toBeCloseTo(2.0, 1)
})

test("volumeConfirmation: fails when today < avg", () => {
  const volumes: number[] = []
  for (let i = 0; i < 20; i++) volumes.push(1_000_000)
  volumes.push(500_000) // below average
  const res = volumeConfirmation(volumes, 20)
  expect(res.confirmed).toBe(false)
  expect(res.ratio).toBeCloseTo(0.5, 1)
})

test("volumeConfirmation: returns NaN with insufficient data", () => {
  const volumes = Array.from({ length: 15 }, () => 1_000_000)
  const res = volumeConfirmation(volumes, 20)
  expect(res.confirmed).toBe(false)
})

// ── computeSnapshot ─────────────────────────────────────────────────────────

test("computeSnapshot: returns null with < 150 bars", () => {
  const bars = Array.from({ length: 149 }, (_, i) => ({
    date: `2026-01-${String(i + 1).padStart(2, "0")}`,
    open: 100,
    high: 101,
    low: 99,
    close: 100 + i * 0.1,
    volume: 1_000_000,
  }))
  expect(computeSnapshot("SPY", bars)).toBeNull()
})

test("computeSnapshot: returns full snapshot with 150+ bars", () => {
  const bars = Array.from({ length: 160 }, (_, i) => ({
    date: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
    open: 100,
    high: 101,
    low: 99,
    close: 100 + i * 0.1,
    volume: 1_000_000,
  }))
  const snap = computeSnapshot("SPY", bars)
  expect(snap).not.toBeNull()
  expect(snap!.ticker).toBe("SPY")
  expect(snap!.ma_150).not.toBeNaN()
  expect(snap!.rsi_14).not.toBeNaN()
})

// ── evaluateScan ─────────────────────────────────────────────────────────────

test("evaluateScan: all gates pass when conditions met", () => {
  // Build a snapshot where all 6 gates fire
  const bars = Array.from({ length: 160 }, (_, i) => {
    // Make RSI < 30: drop price significantly
    const base = i < 140 ? 100 + i * 0.05 : 100 - 20 + (i - 140) * 0.05
    return {
      date: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
      open: base,
      high: base + 1,
      low: base - 1,
      close: base,
      volume: 2_000_000,
    }
  })
  const snap = computeSnapshot("SPY", bars)!
  // Override for test: ensure price > MA20 and > MA150
  // Force price above MA20
  // Manually create a passing snapshot
  const passingSnap = {
    ...snap,
    rsi_14: 28, // oversold — passes gate; < 70 so no exit trigger
    bb_lower: 86, // price=85 ≤ 86 — bollinger gate passes
    bb_upper: 100, // ensure price < upper band — no exit trigger
    price: 85,
    ma_20: 80,
    ma_150: 60, // price > MA150 — structural filter passes
    adx_14: 25, // trending — passes gate
    macd_histogram: 0.5, // positive — passes gate; also prevents death cross exit
    macd_line: 1,
    macd_signal: 0.5,
    volume_confirmed: true,
    // Exit triggers all clear:
    //   RSI > 70?           No (28)
    //   price ≥ bb_upper?   No (85 < 100)
    //   MACD death cross?   No (histogram=0.5 not < 0)
  }

  const result = evaluateScan("SPY", passingSnap)
  expect(result.signal).toBe("buy")
  expect(result.gatesPassed).toBe(6)
  expect(result.ma150Passed).toBe(true)
})

test("evaluateScan: sell signal when exit trigger fires", () => {
  const bars = Array.from({ length: 160 }, (_, i) => ({
    date: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
    open: 100 + i * 0.5,
    high: 101 + i * 0.5,
    low: 99 + i * 0.5,
    close: 100 + i * 0.5,
    volume: 1_500_000,
  }))
  const snap = computeSnapshot("SPY", bars)!
  // Force RSI > 70 (overbought — exit trigger)
  const sellSnap = {
    ...snap,
    rsi_14: 85,
    bb_upper: 200,
    price: 250,
    macd_histogram: -1.5,
    macd_line: 1,
    macd_signal: 2.5, // death cross
  }
  const result = evaluateScan("SPY", sellSnap)
  expect(result.signal).toBe("sell")
  expect(result.exitTriggers.length).toBeGreaterThan(0)
})

test("evaluateScan: relaxed gate always passes", () => {
  const bars = Array.from({ length: 160 }, (_, i) => ({
    date: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
    open: 100,
    high: 101,
    low: 99,
    close: 100,
    volume: 1_000_000,
  }))
  const snap = computeSnapshot("SPY", bars)!

  // All gates fail by default (flat prices, neutral RSI)
  const result = evaluateScan(
    "SPY",
    snap,
    new Set(["rsi", "ma20", "adx", "macd", "volume", "bollinger"]),
  )
  expect(result.gatesPassed).toBe(6)
  expect(result.gates.every((g) => g.relaxed)).toBe(true)
})

test("evaluateScan: MA150 always enforced even when all gates pass", () => {
  // All gates pass but price below MA150
  const snap = {
    ticker: "TEST",
    date: "2026-01-01",
    price: 90,
    rsi_14: 28,
    bb_lower: 80,
    bb_middle: 100,
    bb_upper: 120,
    ma_20: 95,
    ma_150: 100, // price below MA150
    adx_14: 25,
    adx_plus_di: 20,
    adx_minus_di: 10,
    macd_line: 1,
    macd_signal: 0.5,
    macd_histogram: 0.5,
    volume: 2_000_000,
    volume_20avg: 1_000_000,
    volume_confirmed: true,
  }
  const result = evaluateScan("TEST", snap)
  expect(result.ma150Passed).toBe(false)
  expect(result.signal).toBe("no_buy")
})

// ── GATE_DEFINITIONS ─────────────────────────────────────────────────────────

test("GATE_DEFINITIONS: 6 gates defined in correct order", () => {
  expect(GATE_DEFINITIONS).toHaveLength(6)
  expect(GATE_DEFINITIONS.map((g) => g.name)).toEqual([
    "rsi",
    "bollinger",
    "ma20",
    "adx",
    "macd",
    "volume",
  ])
})

test("GATE_DEFINITIONS: each gate has evaluate and getValue", () => {
  for (const gate of GATE_DEFINITIONS) {
    expect(typeof gate.evaluate).toBe("function")
    expect(typeof gate.getValue).toBe("function")
    expect(typeof gate.label).toBe("string")
    expect(typeof gate.description).toBe("string")
  }
})
