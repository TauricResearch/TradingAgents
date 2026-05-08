/**
 * IG instrument-specific configuration.
 *
 * Values validated against IG demo API (2026-05-07).
 * See docs/ig-connectivity-config.md for source data.
 *
 * NOTE: All margin factors are estimates based on demo API data.
 * IG may change margin requirements without notice. Always verify
 * actual margin via GET /markets/{epic} before placing a trade.
 */

export interface IGInstrumentConfig {
  epic: string
  name: string
  type: "INDICES" | "SHARES" | "CURRENCIES" | "COMMODITIES"
  currency: "GBP" | "USD" | "EUR"
  lotSize: number // contract size or share multiplier
  unit: string // "CONTRACTS" | "SHARES" | "POINTS"
  marginFactor: number // decimal, e.g. 0.05 = 5%
  marginFactorUnit: "PERCENTAGE" | "POINTS"
  minDealSize: number // minimum order size
  minStopDistance: number // minimum stop distance in points
  maxStopDistancePercent: number // max stop as % of price
  slippageFactor: number // slippage multiplier (%)
  pipValue?: number // value per pip (for forex)
  is24Hour: boolean // US 24-hour shares have null bid/offer in demo
  notes: string[]
}

export const IG_INSTRUMENTS: Record<string, IGInstrumentConfig> = {
  // ── Indices ──────────────────────────────────────────────────────────────
  "FTSE 100": {
    epic: "IX.D.FTSE.CFD.IP",
    name: "FTSE 100 Cash",
    type: "INDICES",
    currency: "GBP",
    lotSize: 10, // £10 per point
    unit: "CONTRACTS",
    marginFactor: 0.05, // 5%
    marginFactorUnit: "PERCENTAGE",
    minDealSize: 0.5, // £5 min exposure
    minStopDistance: 8, // 8 points minimum
    maxStopDistancePercent: 75,
    slippageFactor: 50,
    is24Hour: false,
    notes: [
      "£10 per point. Stake of 0.5 = £5/point exposure.",
      "Margin is 5% for positions up to £33/point.",
      "Min stop: 8 points. Max stop: 75% of price.",
    ],
  },

  // ── Shares ───────────────────────────────────────────────────────────────
  AAPL: {
    epic: "UA.D.AAPL.CASH.IP",
    name: "Apple Inc (24 Hours)",
    type: "SHARES",
    currency: "USD",
    lotSize: 0.01, // 0.01 shares minimum
    unit: "SHARES",
    marginFactor: 0.2, // 20% tiered
    marginFactorUnit: "PERCENTAGE",
    minDealSize: 0.01, // 0.01 shares
    minStopDistance: 1, // 1 point ($0.01)
    maxStopDistancePercent: 90,
    slippageFactor: 100,
    is24Hour: true,
    notes: [
      "24-hour trading. Closes early Friday 22:00 UK.",
      "Margin tiered: 20% up to ~$7,500, 40% up to $37,500, 75% above.",
      "Demo account may reject orders (null bid/offer). Use UK shares for testing.",
    ],
  },

  // ── Forex ────────────────────────────────────────────────────────────────
  "EUR/USD": {
    epic: "CS.D.EURUSD.CFD.IP",
    name: "EUR/USD",
    type: "CURRENCIES",
    currency: "USD",
    lotSize: 1,
    unit: "CONTRACTS",
    marginFactor: 0.01, // ~1% (typical for forex)
    marginFactorUnit: "PERCENTAGE",
    minDealSize: 0.5,
    minStopDistance: 5, // typical forex spread
    maxStopDistancePercent: 90,
    slippageFactor: 50,
    pipValue: 10, // $10 per pip on standard lot
    is24Hour: false,
    notes: [
      "Margin factor estimated — verify via API before trading.",
      "Standard lot = 100,000 units. Pip value = $10.",
    ],
  },

  // ── Commodities ──────────────────────────────────────────────────────────
  Gold: {
    epic: "CS.D.CFPGOLD.CFP.IP",
    name: "Spot Gold",
    type: "CURRENCIES", // IG classifies gold as currency
    currency: "GBP",
    lotSize: 1,
    unit: "CONTRACTS",
    marginFactor: 0.05, // estimated
    marginFactorUnit: "PERCENTAGE",
    minDealSize: 0.5,
    minStopDistance: 10,
    maxStopDistancePercent: 75,
    slippageFactor: 50,
    is24Hour: false,
    notes: ["Margin factor estimated — verify via API before trading."],
  },
}

/**
 * Look up instrument config by ticker or name.
 * Returns null if not found.
 */
export function getIGInstrument(ticker: string): IGInstrumentConfig | null {
  const key = ticker.toUpperCase()
  return IG_INSTRUMENTS[key] ?? null
}

/**
 * Validate a trade plan against IG instrument constraints.
 *
 * Returns warnings and suggested adjustments. Does NOT modify the plan —
 * caller decides whether to enforce, warn, or abort.
 */
export interface IGValidationResult {
  ok: boolean
  warnings: string[]
  adjusted?: {
    stopLoss?: number
    positionSize?: number
    stake?: number
  }
}

export function validateIGPlan(
  plan: {
    ticker: string
    entry: number
    stopLoss: number
    positionSize: number
    target1: number
    target2: number
  },
  mode: "shares" | "spreadbet",
): IGValidationResult {
  const instrument = getIGInstrument(plan.ticker)
  if (!instrument) {
    return {
      ok: true,
      warnings: [
        `⚠️  No IG instrument config for ${plan.ticker}. Using generic estimates. Verify margin via IG API.`,
      ],
    }
  }

  const warnings: string[] = []

  // 1. Margin estimate warning
  warnings.push(
    `ℹ️  Margin factor for ${instrument.name}: ${(instrument.marginFactor * 100).toFixed(0)}% (estimate — verify via IG)`,
  )

  // 2. Min stop distance
  const stopDistance = Math.abs(plan.entry - plan.stopLoss)
  if (stopDistance < instrument.minStopDistance) {
    warnings.push(
      `⚠️  Stop distance (${stopDistance.toFixed(2)} pts) < IG minimum (${instrument.minStopDistance} pts). IG may reject order.`,
    )
  }

  // 3. Min deal size (shares)
  if (mode === "shares" && plan.positionSize < instrument.minDealSize) {
    warnings.push(
      `⚠️  Position size (${plan.positionSize}) < IG minimum (${instrument.minDealSize} ${instrument.unit.toLowerCase()}).`,
    )
  }

  // 4. 24-hour share warning
  if (instrument.is24Hour) {
    warnings.push(
      `⚠️  ${instrument.name} is 24-hour. Demo account may reject orders (null bid/offer). Test with UK shares or indices.`,
    )
  }

  // 5. Max stop distance
  const maxStopDistance = plan.entry * (instrument.maxStopDistancePercent / 100)
  if (stopDistance > maxStopDistance) {
    warnings.push(
      `⚠️  Stop distance (${stopDistance.toFixed(2)} pts) > IG maximum (${instrument.maxStopDistancePercent}% of price = ${maxStopDistance.toFixed(2)}).`,
    )
  }

  return { ok: warnings.every((w) => !w.startsWith("⚠️")), warnings }
}
