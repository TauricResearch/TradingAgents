/**
 * Tests for cli/trading/lib/ig-instruments.ts
 *
 * Validates IG instrument config and trade plan validation.
 * All values cross-referenced against IG demo API (2026-05-07).
 */

import { describe, expect, test } from "bun:test"
import {
  getIGInstrument,
  IG_INSTRUMENTS,
  validateIGPlan,
} from "../cli/trading/lib/ig-instruments.ts"

describe("getIGInstrument", () => {
  test("returns config for known tickers", () => {
    expect(getIGInstrument("AAPL")?.epic).toBe("UA.D.AAPL.CASH.IP")
    expect(getIGInstrument("FTSE 100")?.epic).toBe("IX.D.FTSE.CFD.IP")
    expect(getIGInstrument("EUR/USD")?.epic).toBe("CS.D.EURUSD.CFD.IP")
  })

  test("is case-insensitive", () => {
    expect(getIGInstrument("aapl")?.epic).toBe("UA.D.AAPL.CASH.IP")
    expect(getIGInstrument("ftse 100")?.epic).toBe("IX.D.FTSE.CFD.IP")
  })

  test("returns null for unknown ticker", () => {
    expect(getIGInstrument("UNKNOWN")).toBeNull()
  })
})

describe("IG_INSTRUMENTS config", () => {
  test("FTSE 100 has correct IG parameters", () => {
    const ftse = IG_INSTRUMENTS["FTSE 100"]
    if (!ftse) throw new Error("FTSE 100 not found in IG_INSTRUMENTS")
    expect(ftse.marginFactor).toBe(0.05)
    expect(ftse.minStopDistance).toBe(8)
    expect(ftse.minDealSize).toBe(0.5)
    expect(ftse.lotSize).toBe(10)
    expect(ftse.currency).toBe("GBP")
    expect(ftse.unit).toBe("CONTRACTS")
  })

  test("AAPL has correct IG parameters", () => {
    const aapl = IG_INSTRUMENTS.AAPL
    if (!aapl) throw new Error("AAPL not found in IG_INSTRUMENTS")
    expect(aapl.marginFactor).toBe(0.2)
    expect(aapl.minStopDistance).toBe(1)
    expect(aapl.minDealSize).toBe(0.01)
    expect(aapl.lotSize).toBe(0.01)
    expect(aapl.currency).toBe("USD")
    expect(aapl.is24Hour).toBe(true)
  })

  test("every instrument has required fields", () => {
    for (const [ticker, config] of Object.entries(IG_INSTRUMENTS)) {
      expect(config.epic, `${ticker}: epic`).toBeTruthy()
      expect(config.name, `${ticker}: name`).toBeTruthy()
      expect(config.marginFactor, `${ticker}: marginFactor`).toBeGreaterThan(0)
      expect(config.marginFactor, `${ticker}: marginFactor`).toBeLessThan(1)
      expect(config.minStopDistance, `${ticker}: minStopDistance`).toBeGreaterThanOrEqual(0)
      expect(config.maxStopDistancePercent, `${ticker}: maxStopDistancePercent`).toBeGreaterThan(0)
      expect(config.slippageFactor, `${ticker}: slippageFactor`).toBeGreaterThan(0)
    }
  })
})

describe("validateIGPlan", () => {
  test("warns about unknown ticker", () => {
    const result = validateIGPlan(
      { ticker: "UNKNOWN", entry: 100, stopLoss: 95, positionSize: 10, target1: 110, target2: 120 },
      "spreadbet",
    )
    expect(result.ok).toBe(true)
    expect(result.warnings.length).toBe(1)
    expect(result.warnings[0]).toContain("No IG instrument config")
  })

  test("warns when stop distance < IG minimum (FTSE)", () => {
    // FTSE min stop = 8 points
    const result = validateIGPlan(
      {
        ticker: "FTSE 100",
        entry: 10400,
        stopLoss: 10399,
        positionSize: 1,
        target1: 10500,
        target2: 10600,
      },
      "spreadbet",
    )
    expect(result.ok).toBe(false)
    expect(result.warnings.some((w) => w.includes("Stop distance") && w.includes("8 pts"))).toBe(
      true,
    )
  })

  test("passes when stop distance >= IG minimum (FTSE)", () => {
    const result = validateIGPlan(
      {
        ticker: "FTSE 100",
        entry: 10400,
        stopLoss: 10390,
        positionSize: 1,
        target1: 10500,
        target2: 10600,
      },
      "spreadbet",
    )
    expect(result.ok).toBe(true)
    expect(result.warnings.some((w) => w.includes("Stop distance"))).toBe(false)
  })

  test("warns when position size < min deal size (shares)", () => {
    // AAPL min deal = 0.01
    const result = validateIGPlan(
      { ticker: "AAPL", entry: 280, stopLoss: 270, positionSize: 0, target1: 300, target2: 320 },
      "shares",
    )
    expect(result.ok).toBe(false)
    expect(result.warnings.some((w) => w.includes("Position size") && w.includes("0.01"))).toBe(
      true,
    )
  })

  test("warns about 24-hour shares (AAPL)", () => {
    const result = validateIGPlan(
      { ticker: "AAPL", entry: 280, stopLoss: 270, positionSize: 1, target1: 300, target2: 320 },
      "shares",
    )
    expect(result.warnings.some((w) => w.includes("24-hour"))).toBe(true)
  })

  test("warns when stop distance > max allowed", () => {
    // FTSE max stop = 75% of price
    const result = validateIGPlan(
      { ticker: "FTSE 100", entry: 100, stopLoss: 10, positionSize: 1, target1: 110, target2: 120 },
      "spreadbet",
    )
    expect(result.ok).toBe(false)
    expect(result.warnings.some((w) => w.includes("maximum"))).toBe(true)
  })

  test("includes margin estimate note for known instrument", () => {
    const result = validateIGPlan(
      {
        ticker: "FTSE 100",
        entry: 10400,
        stopLoss: 10390,
        positionSize: 1,
        target1: 10500,
        target2: 10600,
      },
      "spreadbet",
    )
    expect(result.warnings.some((w) => w.includes("Margin factor") && w.includes("5%"))).toBe(true)
  })

  test("does not flag position size for spreadbet mode", () => {
    // Spread bet mode doesn't check positionSize (it checks stake instead)
    const result = validateIGPlan(
      { ticker: "AAPL", entry: 280, stopLoss: 270, positionSize: 0, target1: 300, target2: 320 },
      "spreadbet",
    )
    expect(result.warnings.some((w) => w.includes("Position size"))).toBe(false)
  })
})
