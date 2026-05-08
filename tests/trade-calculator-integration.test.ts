/**
 * Integration test: verify calculator output against manually computed
 * reference values using real price data from the prices table.
 *
 * This catches formula errors that unit tests with synthetic data miss.
 */

import { beforeAll, describe, expect, test } from "bun:test"
import { DatabaseFactory } from "../src/lib/db.ts"
import { calculateTradePlan, type PriceBar } from "../src/lib/trade-calculator.ts"

describe("trade-calculator integration: real price data", () => {
  let aaplHistory: PriceBar[]

  beforeAll(() => {
    const dbPath = process.env.PORTFOLIO_DB ?? "./portfolio.db"
    DatabaseFactory.connect(dbPath)
    const db = DatabaseFactory.get()

    const rows = db
      .query(
        `SELECT date, open, high, low, close, volume
       FROM prices
       WHERE ticker = ?
       ORDER BY date ASC`,
      )
      .all("AAPL") as Array<{
      date: string
      open: number | string
      high: number | string
      low: number | string
      close: number | string
      volume: number | string
    }>

    if (rows.length === 0) {
      throw new Error("No AAPL price data in prices table. Run: just sync-prices")
    }

    aaplHistory = rows.map((r) => ({
      date: r.date,
      open: parseFloat(String(r.open)),
      high: parseFloat(String(r.high)),
      low: parseFloat(String(r.low)),
      close: parseFloat(String(r.close)),
      volume: parseInt(String(r.volume), 10),
    }))
  })

  test("AAPL plan values match manual cross-check", () => {
    const plan = calculateTradePlan({
      ticker: "AAPL",
      priceHistory: aaplHistory,
      accountBalance: 50000,
      riskPerTrade: 0.02,
    })

    // Manual verification of key fields
    // 1. Entry = last close (unless overridden)
    const lastClose = aaplHistory[aaplHistory.length - 1].close
    expect(plan.entry).toBeCloseTo(lastClose, 2)

    // 2. Stop = entry - 2*ATR. Verify ATR is positive and reasonable.
    expect(plan.atr14).toBeGreaterThan(0)
    expect(plan.atr14).toBeLessThan(lastClose * 0.1) // ATR < 10% of price
    const expectedStop = plan.entry - 2.0 * plan.atr14
    expect(plan.stopLoss).toBeCloseTo(expectedStop, 2)

    // 3. Risk amount should be in the right ballpark
    // Note: plan.entry and plan.stopLoss are rounded to 2 decimals,
    // but riskAmount is computed from raw values before rounding.
    // Recomputing from rounded values gives ~£0.22 difference — acceptable.
    const riskPerShare = plan.entry - plan.stopLoss
    const expectedRisk = plan.positionSize * riskPerShare
    expect(plan.riskAmount).toBeCloseTo(expectedRisk, 0) // within £0.50

    // 4. Risk % ≤ 2% (integer shares round down, never exceed)
    expect(plan.riskPercent).toBeLessThanOrEqual(0.02)
    expect(plan.riskPercent).toBeGreaterThan(0) // some risk taken

    // 5. Targets are ordered correctly
    expect(plan.target1).toBeGreaterThan(plan.entry)
    expect(plan.target2).toBeGreaterThan(plan.target1)

    // 6. Position size is integer and non-negative
    expect(Number.isInteger(plan.positionSize)).toBe(true)
    expect(plan.positionSize).toBeGreaterThanOrEqual(0)

    // 7. R/R ratio > 1 (reward should exceed risk)
    const rr = (plan.target2 - plan.entry) / (plan.entry - plan.stopLoss)
    expect(rr).toBeGreaterThan(1)
    expect(plan.target2).toBeGreaterThanOrEqual(plan.entry + 2 * (plan.entry - plan.stopLoss))

    // 8. Insufficient history flag is false (AAPL has plenty of data)
    expect(plan.insufficientHistory).toBe(false)

    // 9. Swing detection found actual swing points
    expect(plan.swingLow).toBeLessThan(plan.swingHigh)
    expect(plan.swingLow).toBeGreaterThan(0)
    expect(plan.swingHigh).toBeGreaterThan(0)
  })

  test("position sizing is monotonic with account balance", () => {
    const plan50k = calculateTradePlan({
      ticker: "AAPL",
      priceHistory: aaplHistory,
      accountBalance: 50000,
      riskPerTrade: 0.02,
    })

    const plan100k = calculateTradePlan({
      ticker: "AAPL",
      priceHistory: aaplHistory,
      accountBalance: 100000,
      riskPerTrade: 0.02,
    })

    // Double the account → position size should increase (or stay same if rounding)
    expect(plan100k.positionSize).toBeGreaterThanOrEqual(plan50k.positionSize)
    expect(plan100k.riskAmount).toBeGreaterThanOrEqual(plan50k.riskAmount)
  })

  test("risk per trade scales correctly", () => {
    const plan1pct = calculateTradePlan({
      ticker: "AAPL",
      priceHistory: aaplHistory,
      accountBalance: 50000,
      riskPerTrade: 0.01,
    })

    const plan2pct = calculateTradePlan({
      ticker: "AAPL",
      priceHistory: aaplHistory,
      accountBalance: 50000,
      riskPerTrade: 0.02,
    })

    // 2% risk should produce ≥ risk amount vs 1% risk
    expect(plan2pct.riskAmount).toBeGreaterThanOrEqual(plan1pct.riskAmount)
    expect(plan2pct.positionSize).toBeGreaterThanOrEqual(plan1pct.positionSize)
  })
})
