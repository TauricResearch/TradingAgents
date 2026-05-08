/**
 * Tests for src/lib/trade-calculator.ts
 *
 * Strategy: example-based tests with hand-verified expectations.
 * We test against known inputs where we can compute the expected
 * output manually or cross-reference with TradingView/Yahoo Finance.
 */

import { describe, expect, test } from "bun:test"
import {
  calculateATR,
  calculateTradePlan,
  estimateATR,
  fibonacciExtension,
  findSwingHighLow,
  type PriceBar,
} from "../src/lib/trade-calculator.ts"

// ── Helpers ─────────────────────────────────────────────────────────────────

function makeBar(date: string, open: number, high: number, low: number, close: number): PriceBar {
  return { date, open, high, low, close, volume: 1000 }
}

// ── ATR Tests ───────────────────────────────────────────────────────────────

describe("calculateATR", () => {
  test("calculates 14-day ATR for a simple series", () => {
    // 15 bars: close = high = low = (index+1)*10
    // Bar 0 has no prior → TR not computed
    // Bar 1: high=20, low=20, prev_close=10
    //   TR = max(20-20=0, |20-10|=10, |20-10|=10) = 10
    // Bars 1-14 all have TR = 10
    // ATR = mean of 14 TR values = 10
    const bars: PriceBar[] = []
    for (let i = 0; i < 15; i++) {
      const price = (i + 1) * 10
      bars.push(makeBar(`2026-01-${String(i + 1).padStart(2, "0")}`, price, price, price, price))
    }

    const atr = calculateATR(bars, 14)
    expect(atr).toBeCloseTo(10, 4) // 14 TR values of 10 each → mean = 10
  })

  test("handles high volatility correctly", () => {
    // Bar with wide range
    const bars: PriceBar[] = [
      makeBar("2026-01-01", 100, 105, 95, 100),
      makeBar("2026-01-02", 102, 110, 98, 102),
    ]

    // Bar 0: no prior, TR = high-low = 10
    // Bar 1: high-low=12, |high-prev_close|=|110-100|=10, |low-prev_close|=|98-100|=2
    // TR = max(12, 10, 2) = 12
    // With only 2 bars, ATR uses last 1 TR values (n=1 of the available)
    // Actually: for 2 bars, we have 1 TR value (bar 1), ATR should be ~12
    // But the function needs n+1 bars. With 2 bars and n=1, it works.
    const atr = calculateATR(bars, 1)
    expect(atr).toBeCloseTo(12, 4)
  })

  test("falls back to estimateATR when insufficient history", () => {
    const bars: PriceBar[] = [makeBar("2026-01-01", 100, 110, 90, 100)]

    const atr = calculateATR(bars, 14) // needs 15 bars, has 1
    // Fallback: estimateATR uses avg(high-low)
    // high-low = 20, avg = 20
    expect(atr).toBeCloseTo(20, 4)
  })
})

describe("estimateATR", () => {
  test("averages daily ranges", () => {
    const bars: PriceBar[] = [
      makeBar("2026-01-01", 100, 110, 95, 100), // range = 15
      makeBar("2026-01-02", 102, 108, 98, 102), // range = 10
      makeBar("2026-01-03", 105, 115, 100, 105), // range = 15
    ]

    const atr = estimateATR(bars)
    expect(atr).toBeCloseTo((15 + 10 + 15) / 3, 4) // 13.3333
  })

  test("returns 0 for empty array", () => {
    expect(estimateATR([])).toBe(0)
  })
})

// ── Swing Detection Tests ───────────────────────────────────────────────────

describe("findSwingHighLow", () => {
  test("finds clear swing low and high", () => {
    // Clear AB move: drop to 50, rise to 100
    const bars: PriceBar[] = [
      makeBar("2026-01-01", 80, 85, 75, 80),
      makeBar("2026-01-02", 70, 75, 65, 70),
      makeBar("2026-01-03", 60, 65, 50, 60), // swing low = 50
      makeBar("2026-01-04", 75, 85, 70, 75),
      makeBar("2026-01-05", 90, 100, 85, 90), // swing high = 100
      makeBar("2026-01-06", 85, 90, 80, 85),
    ]

    const { swingLow, swingHigh } = findSwingHighLow(bars)
    expect(swingLow).toBe(50)
    expect(swingHigh).toBe(100)
  })

  test("uses highest high after lowest low", () => {
    // Clear trend: drops to 50, rises to 100, drops to 75
    const bars: PriceBar[] = [
      makeBar("2026-01-01", 80, 85, 75, 80),
      makeBar("2026-01-02", 65, 70, 50, 65), // swing low = 50
      makeBar("2026-01-03", 95, 100, 90, 95), // swing high = 100
      makeBar("2026-01-04", 80, 85, 75, 80),
    ]

    const { swingLow, swingHigh } = findSwingHighLow(bars)
    expect(swingLow).toBe(50) // lowest low
    expect(swingHigh).toBe(100) // highest high after that low
  })

  test("handles single bar", () => {
    const bars: PriceBar[] = [makeBar("2026-01-01", 100, 110, 90, 100)]
    const { swingLow, swingHigh } = findSwingHighLow(bars)
    expect(swingLow).toBe(90)
    expect(swingHigh).toBe(110)
  })
})

// ── Fibonacci Extension Tests ───────────────────────────────────────────────

describe("fibonacciExtension", () => {
  test("calculates 138.2% and 161.8% correctly", () => {
    // AB move: 50 → 100, move = 50
    // 138.2% = 100 + 50 * 1.382 = 169.1
    // 161.8% = 100 + 50 * 1.618 = 180.9
    const result = fibonacciExtension(50, 100, [1.382, 1.618])
    expect(result[0]).toBeCloseTo(169.1, 4)
    expect(result[1]).toBeCloseTo(180.9, 4)
  })

  test("handles reverse AB (decreasing)", () => {
    // A=100, B=50, move = -50
    // 138.2% = 50 + (-50) * 1.382 = -19.1
    const result = fibonacciExtension(100, 50, [1.382])
    expect(result[0]).toBeCloseTo(-19.1, 4)
  })
})

describe("calculateTradePlan", () => {
  test("produces valid plan for normal input", () => {
    // Generate 30 bars with clear trend
    const bars: PriceBar[] = []
    for (let i = 0; i < 30; i++) {
      const price = 100 + i * 2
      bars.push(
        makeBar(
          `2026-01-${String((i % 30) + 1).padStart(2, "0")}`,
          price,
          price + 5,
          price - 3,
          price,
        ),
      )
    }

    const plan = calculateTradePlan({
      ticker: "TEST",
      priceHistory: bars,
      accountBalance: 50000,
      riskPerTrade: 0.02,
    })

    expect(plan.ticker).toBe("TEST")
    expect(plan.entry).toBeGreaterThan(0)
    expect(plan.stopLoss).toBeLessThan(plan.entry)
    expect(plan.target1).toBeGreaterThan(plan.entry)
    expect(plan.target2).toBeGreaterThan(plan.target1)
    expect(plan.positionSize).toBeGreaterThan(0)
    expect(plan.riskAmount).toBeGreaterThan(0)
    expect(plan.riskPercent).toBeCloseTo(0.02, 2)
    expect(plan.atr14).toBeGreaterThan(0)
    expect(plan.insufficientHistory).toBe(false)
  })

  test("respects manual entry price override", () => {
    const bars: PriceBar[] = []
    for (let i = 0; i < 30; i++) {
      const price = 100 + i
      bars.push(
        makeBar(`2026-01-${String(i + 1).padStart(2, "0")}`, price, price + 5, price - 3, price),
      )
    }

    const plan = calculateTradePlan({
      ticker: "TEST",
      priceHistory: bars,
      accountBalance: 50000,
      riskPerTrade: 0.02,
      entryPrice: 150,
    })

    expect(plan.entry).toBe(150)
  })

  test("flags insufficient history", () => {
    // Only 5 bars — way below 22 needed for swing detection
    const bars: PriceBar[] = []
    for (let i = 0; i < 5; i++) {
      const price = 100 + i
      bars.push(makeBar(`2026-01-0${i + 1}`, price, price + 5, price - 3, price))
    }

    const plan = calculateTradePlan({
      ticker: "TEST",
      priceHistory: bars,
      accountBalance: 50000,
      riskPerTrade: 0.02,
    })

    expect(plan.insufficientHistory).toBe(true)
    // Should still produce values (fallback)
    expect(plan.entry).toBeGreaterThan(0)
    expect(plan.atr14).toBeGreaterThan(0)
  })

  test("throws on empty price history", () => {
    expect(() =>
      calculateTradePlan({
        ticker: "TEST",
        priceHistory: [],
        accountBalance: 50000,
        riskPerTrade: 0.02,
      }),
    ).toThrow("Price history is empty")
  })

  test("position sizing does not exceed risk limit", () => {
    // Flat price: 100, ATR ≈ 6 (from high-low ranges)
    const bars: PriceBar[] = []
    for (let i = 0; i < 30; i++) {
      bars.push(makeBar(`2026-01-${String((i % 30) + 1).padStart(2, "0")}`, 100, 106, 94, 100))
    }

    const plan = calculateTradePlan({
      ticker: "FLAT",
      priceHistory: bars,
      accountBalance: 100000,
      riskPerTrade: 0.01, // 1% = £1,000 target
    })

    // Position sizing uses integer shares (floor), so actual risk is
    // ≤ target risk, never above. Verify it's in the right ballpark.
    expect(plan.riskAmount).toBeGreaterThan(0)
    expect(plan.riskAmount).toBeLessThanOrEqual(1000)
    expect(plan.riskPercent).toBeLessThanOrEqual(0.01)
  })

  test("concentration flag triggers correctly", () => {
    // High price stock with small account → position > 5%
    const bars: PriceBar[] = []
    for (let i = 0; i < 30; i++) {
      const price = 500 + i
      bars.push(
        makeBar(`2026-01-${String(i + 1).padStart(2, "0")}`, price, price + 20, price - 15, price),
      )
    }

    const plan = calculateTradePlan({
      ticker: "EXPENSIVE",
      priceHistory: bars,
      accountBalance: 10000, // small account
      riskPerTrade: 0.02,
    })

    expect(plan.concentrationFlag).toBe(true)
  })

  test("concentration flag stays off for small positions", () => {
    const bars: PriceBar[] = []
    for (let i = 0; i < 30; i++) {
      const price = 10 + i * 0.1
      bars.push(
        makeBar(`2026-01-${String(i + 1).padStart(2, "0")}`, price, price + 1, price - 0.5, price),
      )
    }

    const plan = calculateTradePlan({
      ticker: "CHEAP",
      priceHistory: bars,
      accountBalance: 100000,
      riskPerTrade: 0.01,
    })

    expect(plan.concentrationFlag).toBe(false)
  })

  test("zero risk per trade produces zero position", () => {
    const bars: PriceBar[] = []
    for (let i = 0; i < 30; i++) {
      const price = 100 + i
      bars.push(
        makeBar(`2026-01-${String(i + 1).padStart(2, "0")}`, price, price + 5, price - 3, price),
      )
    }

    const plan = calculateTradePlan({
      ticker: "TEST",
      priceHistory: bars,
      accountBalance: 50000,
      riskPerTrade: 0,
    })

    expect(plan.positionSize).toBe(0)
    expect(plan.riskAmount).toBe(0)
  })
})

// ── Cross-Reference Tests ───────────────────────────────────────────────────
// These verify against manually computed or externally verified values.

describe("cross-reference: ATR calculation", () => {
  test("matches manual calculation for known series", () => {
    // From Investopedia example:
    // https://www.investopedia.com/terms/a/atr.asp
    // Day 1: High=1.2500, Low=1.2450, Close=1.2480
    // Day 2: High=1.2550, Low=1.2470, Close=1.2530
    // TR Day 2 = max(0.0080, |1.2550-1.2480|, |1.2470-1.2480|) = 0.0080
    // With 2 days and n=1, ATR = 0.0080

    const bars: PriceBar[] = [
      { date: "2026-01-01", open: 1.248, high: 1.25, low: 1.245, close: 1.248, volume: 1000 },
      { date: "2026-01-02", open: 1.253, high: 1.255, low: 1.247, close: 1.253, volume: 1000 },
    ]

    const atr = calculateATR(bars, 1)
    expect(atr).toBeCloseTo(0.008, 4) // max(0.0080, 0.0070, 0.0010) = 0.0080
  })
})
